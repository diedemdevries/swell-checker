"""Verificatie van de beslislogica, zonder internet.

Elke test hier beantwoordt de vraag: gaat dit ding af wanneer het moet,
en houdt het zijn mond wanneer dat hoort?
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from surfcheck.forecast import group_by_day                    # noqa: E402
from surfcheck.scoring import (find_blocks, score_day,          # noqa: E402
                               score_hour, surf_height_ft)
from surfcheck.state import State                               # noqa: E402
from tests.fixtures import make_rows, spot                      # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
C = CFG["criteria"]
TODAY = date(2026, 9, 15)
OFFSHORE_FROM = (285 + 180) % 360          # 105 -> offshore voor faces=285
ONSHORE_FROM = 285                          # recht op het strand
GOOD_SWELL_DIR = 300                        # midden in [260, 340]

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def days_for(rows, sp):
    by_day = group_by_day(rows)
    return [score_day(d, [score_hour(r, sp, C) for r in by_day[d]], C)
            for d in sorted(by_day)]


# ---------------------------------------------------------------
# 1. Kwaliteit: lange periode offshore moet fors hoger scoren dan
#    korte periode met dezelfde hoogte.
# ---------------------------------------------------------------
sp = spot()
long_p = days_for(make_rows(TODAY, 3, 1.8, 15.0, GOOD_SWELL_DIR, 6, OFFSHORE_FROM), sp)
short_p = days_for(make_rows(TODAY, 3, 2.4, 8.0, GOOD_SWELL_DIR, 6, OFFSHORE_FROM), sp)
check("15s scoort hoger dan 8s bij vergelijkbare hoogte",
      long_p[0].score > short_p[0].score + 15,
      f"15s={long_p[0].score} vs 8s={short_p[0].score}")
check("8s haalt de drempel wel (jouw keuze), maar mager",
      short_p[0].qualifies and short_p[0].score < 70,
      f"8s score={short_p[0].score}")

# ---------------------------------------------------------------
# 2. DE belangrijke correctie: middagwind mag de dag niet slopen.
# ---------------------------------------------------------------
therm = days_for(make_rows(TODAY, 3, 1.8, 14.0, GOOD_SWELL_DIR,
                           wind_kt=5, wind_from=OFFSHORE_FROM,
                           afternoon_wind_kt=22, afternoon_from=ONSHORE_FROM), sp)
check("ochtend glad + middag 22kt onshore = dag telt gewoon mee",
      therm[0].qualifies, f"score={therm[0].score} venster={therm[0].window}")

allday = days_for(make_rows(TODAY, 3, 1.8, 14.0, GOOD_SWELL_DIR, 22, ONSHORE_FROM), sp)
check("de hele dag 22kt onshore = dag valt af",
      not allday[0].qualifies, allday[0].fail or "")

# ---------------------------------------------------------------
# 3. Windregels: offshore mag harder waaien dan onshore.
# ---------------------------------------------------------------
off13 = days_for(make_rows(TODAY, 2, 1.8, 13.0, GOOD_SWELL_DIR, 13, OFFSHORE_FROM), sp)
on13 = days_for(make_rows(TODAY, 2, 1.8, 13.0, GOOD_SWELL_DIR, 13, ONSHORE_FROM), sp)
check("13kt offshore is goed", off13[0].qualifies, f"score={off13[0].score}")
check("13kt onshore valt af", not on13[0].qualifies, on13[0].fail or "")

# ---------------------------------------------------------------
# 4. Grenzen: te klein en te groot vallen allebei af.
# ---------------------------------------------------------------
tiny = days_for(make_rows(TODAY, 2, 0.6, 12.0, GOOD_SWELL_DIR, 5, OFFSHORE_FROM), sp)
huge = days_for(make_rows(TODAY, 2, 5.0, 16.0, GOOD_SWELL_DIR, 5, OFFSHORE_FROM), sp)
check("te klein valt af", not tiny[0].qualifies, tiny[0].fail or "")
check("te groot valt ook af (geen bovengrens = Nazare in je inbox)",
      not huge[0].qualifies, huge[0].fail or "")

# ---------------------------------------------------------------
# 5. Deining uit de verkeerde hoek komt de baai niet in.
# ---------------------------------------------------------------
wrong = days_for(make_rows(TODAY, 2, 2.0, 14.0, 180, 5, OFFSHORE_FROM), sp)
check("deining buiten het venster valt af", not wrong[0].qualifies, wrong[0].fail or "")

# ---------------------------------------------------------------
# 6. Periode onder 8s is een harde nee.
# ---------------------------------------------------------------
slop = days_for(make_rows(TODAY, 2, 2.5, 6.5, GOOD_SWELL_DIR, 4, OFFSHORE_FROM), sp)
check("6.5s windrommel valt af", not slop[0].qualifies, slop[0].fail or "")

# ---------------------------------------------------------------
# 7. Blokken: 2 dagen mag dichtbij, niet ver weg.
# ---------------------------------------------------------------
two = days_for(make_rows(TODAY, 2, 1.9, 14.0, GOOD_SWELL_DIR, 6, OFFSHORE_FROM), spot())
check("2 goede dagen = blok voor een nabije bestemming",
      len(find_blocks(spot(tier="near"), two, CFG["tiers"]["near"]["min_days"])) == 1)
check("2 goede dagen = geen blok voor Marokko/Ierland",
      len(find_blocks(spot(tier="far"), two, CFG["tiers"]["far"]["min_days"])) == 0)

four = days_for(make_rows(TODAY, 4, 1.9, 14.0, GOOD_SWELL_DIR, 6, OFFSHORE_FROM), spot())
fb = find_blocks(spot(tier="far"), four, 3)
check("4 goede dagen = wel een blok voor de verre bestemmingen", len(fb) == 1)
check("langer blok krijgt een bonus t.o.v. het minimum",
      fb[0].rank_score > four[0].score, f"blok={fb[0].rank_score} dag={four[0].score}")
check("weergavescore blijft binnen 0-100", fb[0].score <= 100.0, f"{fb[0].score}")

# ---------------------------------------------------------------
# 8. Onderbroken reeks telt niet als één blok.
# ---------------------------------------------------------------
mixed = (days_for(make_rows(TODAY, 2, 1.9, 14.0, GOOD_SWELL_DIR, 6, OFFSHORE_FROM), sp)
         + days_for(make_rows(TODAY + timedelta(days=2), 1, 1.9, 14.0,
                              GOOD_SWELL_DIR, 25, ONSHORE_FROM), sp)
         + days_for(make_rows(TODAY + timedelta(days=3), 2, 1.9, 14.0,
                              GOOD_SWELL_DIR, 6, OFFSHORE_FROM), sp))
mb = find_blocks(spot(tier="near"), mixed, 2)
check("een slechte dag ertussen splitst het in twee blokken", len(mb) == 2,
      f"{[(b.start.isoformat(), b.n_days) for b in mb]}")

# ---------------------------------------------------------------
# 9. Alarmvensters.
# ---------------------------------------------------------------
sys.path.insert(0, str(ROOT))
from main import tier_for  # noqa: E402

check("swell over 3 dagen = bevestiging", tier_for(TODAY + timedelta(days=3), TODAY, CFG) == "confirm")
check("swell over 7 dagen = vroege waarschuwing", tier_for(TODAY + timedelta(days=7), TODAY, CFG) == "early")
check("swell over 20 dagen = nog niks melden", tier_for(TODAY + timedelta(days=20), TODAY, CFG) is None)

# ---------------------------------------------------------------
# 10. Dedupe: niet blijven herhalen, wel bevestigen.
# ---------------------------------------------------------------
import tempfile  # noqa: E402
tmp = Path(tempfile.mkdtemp()) / "state.json"
st = State(tmp)
key = "Testspot|2026-09-20"
check("eerste keer melden we", st.should_announce(key, "early", 70) == "new")
st.record(key, "early", 70)
check("tweede keer zelfde niveau: stil", st.should_announce(key, "early", 72) is None)
check("early -> confirm: wel melden", st.should_announce(key, "confirm", 70) == "confirm")
check("flink beter geworden: opnieuw melden", st.should_announce(key, "early", 90) == "upgrade")
st.save()
check("state overleeft opnieuw inlezen",
      State(tmp).should_announce(key, "early", 71) is None)
st2 = State(tmp)
st2.record("Oudspot|2024-01-01", "early", 60)
st2.prune(TODAY)
check("oude swells worden opgeruimd", "Oudspot|2024-01-01" not in st2.data["announced"])

# ---------------------------------------------------------------
# 11. Hoogteschatting: klopt de orde van grootte?
# ---------------------------------------------------------------
anchor = surf_height_ft(2.0, 14.0, 1.5)   # Anchor Point, stevige swell
beach = surf_height_ft(1.2, 9.0, 1.0)     # flauw strand, kleine korte swell
check("2m @ 14s op een point = ruim dubbel manshoog", 9 <= anchor <= 13, f"{anchor:.1f}ft")
check("1.2m @ 9s op een strand = te klein voor deze trip", beach < 5, f"{beach:.1f}ft")

# ---------------------------------------------------------------
# 12. Einde-tot-eind: scan met verzonnen data levert een bericht op.
# ---------------------------------------------------------------
from main import scan  # noqa: E402
from surfcheck import booking, flights, notify  # noqa: E402

fake_cfg = dict(CFG)
fake_cfg["spots"] = [spot(name="Hossegor Test", airport="BIQ", tier="near")]


def fake_fetch(sp, days=7):
    return make_rows(TODAY + timedelta(days=3), 4, 2.0, 15.0, GOOD_SWELL_DIR,
                     6, OFFSHORE_FROM, afternoon_wind_kt=20, afternoon_from=ONSHORE_FROM)


blocks = scan(fake_cfg, TODAY, fetch=fake_fetch)
check("scan vindt het blok", len(blocks) == 1, f"{len(blocks)}")

if blocks:
    b = blocks[0]
    out_d, back_d = b.start - timedelta(days=1), b.end + timedelta(days=1)
    f = flights.Flight("EIN", "Eindhoven", "BIQ", out_d.isoformat(),
                       back_d.isoformat(), 118.0, "Ryanair", "https://x")
    c = booking.car_for("BIQ", "Biarritz", out_d, back_d, CFG["car_eur_day"], CFG["links"]["car"])
    s = booking.stay_for("Biarritz", out_d, back_d, 50, 2, CFG["links"]["stay"])
    msg = notify.build_message(b, f, c, s, "new", "confirm", 2)
    check("bericht bevat de spot, de dagen en een totaalbedrag",
          "Hossegor Test" in msg and "Totaal" in msg and "ft" in msg)
    check("bericht is niet absurd lang voor Telegram", len(msg) < 4096, f"{len(msg)} tekens")
    check("HTML is gebalanceerd", msg.count("<b>") == msg.count("</b>"))
    DEMO_MSG = msg
else:
    DEMO_MSG = ""

# ---------------------------------------------------------------
print()
ok = sum(1 for _, c_, _ in results if c_)
for name, cond, detail in results:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"   ({detail})" if detail else ""))
print(f"\n{ok}/{len(results)} geslaagd")

if DEMO_MSG:
    print("\n" + "=" * 60 + "\nVOORBEELDBERICHT\n" + "=" * 60)
    import re
    print(re.sub(r"<[^>]+>", "", DEMO_MSG))

sys.exit(0 if ok == len(results) else 1)
