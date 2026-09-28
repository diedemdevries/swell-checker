"""Verificatie van de beslislogica, zonder internet.

Elke test hier beantwoordt de vraag: gaat dit ding af wanneer het moet,
en houdt het zijn mond wanneer dat hoort?
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from forecast import group_by_day                    # noqa: E402
from scoring import (find_blocks, score_day,          # noqa: E402
                               score_hour, surf_height_ft)
from state import State                               # noqa: E402
from fixtures import make_rows, spot                      # noqa: E402

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
# 10. Dedupe: één swell per regio één bericht, ook als hij schuift.
# ---------------------------------------------------------------
import tempfile  # noqa: E402
tmp = Path(tempfile.mkdtemp()) / "state.json"
REG = {"La Graviere (Hossegor)": "baskenland", "La Piste (Capbreton)": "baskenland",
       "Coxos (Ericeira)": "portugal-midden"}
st = State(tmp, REG)
S0, E0 = date(2026, 9, 20), date(2026, 9, 23)
check("eerste keer melden we", st.should_announce("baskenland", S0, E0, "early", 76) == "new")
st.record("baskenland", S0, E0, "early", 76)
check("tweede keer zelfde niveau: stil",
      st.should_announce("baskenland", S0, E0, "early", 78) is None)
check("forecast schuift een dag op: nog steeds dezelfde swell",
      st.should_announce("baskenland", S0 + timedelta(days=1), E0 + timedelta(days=1),
                         "early", 78) is None)
check("early -> confirm: wel melden",
      st.should_announce("baskenland", S0, E0, "confirm", 76) == "confirm")
st.record("baskenland", S0, E0, "confirm", 76)
check("na de bevestiging niet nog eens bevestigen",
      st.should_announce("baskenland", S0, E0, "confirm", 80) is None)
check("flink beter geworden: opnieuw melden",
      st.should_announce("baskenland", S0, E0, "confirm", 90) == "upgrade")
check("andere regio, zelfde dagen: wel melden",
      st.should_announce("portugal-midden", S0, E0, "confirm", 76) == "new")
check("zelfde regio, week later: nieuwe swell",
      st.should_announce("baskenland", E0 + timedelta(days=6), E0 + timedelta(days=8),
                         "confirm", 76) == "new")
st.save()
check("state overleeft opnieuw inlezen",
      State(tmp, REG).should_announce("baskenland", S0, E0, "confirm", 77) is None)

# Oude sleutels (spot|datum) van voor deze versie worden nog begrepen.
oud = State(Path(tempfile.mkdtemp()) / "s.json", REG)
oud.data["announced"]["La Piste (Capbreton)|2026-10-01"] = {"tier": "confirm", "score": 73}
check("oude melding per spot telt mee voor de hele regio",
      oud.should_announce("baskenland", date(2026, 10, 2), date(2026, 10, 4),
                          "confirm", 75) is None)

st2 = State(tmp, REG)
st2.record("baskenland", date(2024, 1, 1), date(2024, 1, 3), "early", 60)
st2.prune(TODAY)
check("oude swells worden opgeruimd",
      not any(k.startswith("baskenland|2024") for k in st2.data["announced"]))

# ---------------------------------------------------------------
# 11. Hoogteschatting: klopt de orde van grootte?
# ---------------------------------------------------------------
anchor = surf_height_ft(2.0, 14.0, 1.5)   # Anchor Point, stevige swell
beach = surf_height_ft(1.2, 9.0, 1.0)     # flauw strand, kleine korte swell
check("2m @ 14s op een point = ruim dubbel manshoog", 9 <= anchor <= 13, f"{anchor:.1f}ft")
check("1.2m @ 9s op een strand = te klein voor deze trip", beach < 5, f"{beach:.1f}ft")

# ---------------------------------------------------------------
# 12. Vluchten: vaste routes per regio, beste eerst.
# ---------------------------------------------------------------
import booking, flights, notify  # noqa: E402

ORIG = {o["code"]: o["name"] for o in CFG["origins"]}
spots_by_name = {sp["name"]: sp for sp in CFG["spots"]}


def opts(name, out_d=date(2026, 10, 13), back_d=date(2026, 10, 17)):
    sp = spots_by_name[name]
    return flights.options_for(sp, CFG["regions"][sp["region"]], ORIG, out_d, back_d,
                               2, CFG["links"]["flight"], CFG["trip"]["max_drive_min"])


check("elke regio heeft vaste vluchten",
      all(r.get("flights") for r in CFG["regions"].values()))
check("elke spot heeft minstens één bruikbare route",
      all(opts(n) for n in spots_by_name), [n for n in spots_by_name if not opts(n)])
rod = opts("Rodiles (Asturias)")
check("Rodiles: Santander wint van dure Oviedo-vlucht", rod[0].dest == "SDR", rod[0].dest)
ll = opts("Lahinch")
check("Lahinch: via Dublin", ll[0].dest == "DUB")
check("route verder dan de max rijtijd valt af",
      all(o.drive_min <= CFG["trip"]["max_drive_min"] for n in spots_by_name for o in opts(n)))
link = opts("La Graviere (Hossegor)")[0].link
check("zoeklink heeft vliegvelden en datums", "/crl/biq/261013/261017/" in link, link)
check("heen dag ervoor, terug op de laatste dag",
      flights.trip_dates(date(2026, 10, 14), date(2026, 10, 17))
      == (date(2026, 10, 13), date(2026, 10, 17)))
alt = notify.pick_alternative(opts("Anchor Point"))
check("alternatief gaat bij voorkeur naar een ander vliegveld",
      alt is not None and alt.dest != opts("Anchor Point")[0].dest)

# ---------------------------------------------------------------
# 13. Einde-tot-eind: scan met verzonnen data levert een bericht op.
# ---------------------------------------------------------------
from main import build_trip, scan  # noqa: E402

fake_cfg = dict(CFG)
fake_cfg["spots"] = [spot(name="Hossegor Test", region="baskenland", tier="near",
                          drive_min={"BIQ": 40, "BOD": 105, "BIO": 145})]


def fake_fetch(sp, days=7):
    return make_rows(TODAY + timedelta(days=3), 4, 2.0, 15.0, GOOD_SWELL_DIR,
                     6, OFFSHORE_FROM, afternoon_wind_kt=20, afternoon_from=ONSHORE_FROM)


blocks = scan(fake_cfg, TODAY, fetch=fake_fetch)
check("scan vindt het blok", len(blocks) == 1, f"{len(blocks)}")

if blocks:
    b = blocks[0]
    options, c, g, st, out_d, back_d = build_trip(b, fake_cfg, {})
    check("trip heeft een vlucht naar Biarritz", options and options[0].dest == "BIQ")
    msg = notify.build_message(b, options, c, g, st, out_d, back_d, "new", "confirm",
                               2, "Baskenland", ["La Piste"])
    plain = msg.replace("<b>", "").replace("</b>", "")
    check("bovenaan: spot, dagen en totaalprijs",
          "HOSSEGOR TEST" in msg.split("\n")[0] and "p.p." in "\n".join(msg.split("\n")[:4]))
    check("vlucht met maatschappij en richtprijs", "Ryanair" in msg and "~€185" in msg)
    check("buurspots worden genoemd in plaats van apart gemeld", "La Piste" in msg)
    check("geen score-jargon meer", "/100" not in msg)
    check("geen links in de tekst", "<a " not in msg)
    check("bericht is niet absurd lang voor Telegram", len(msg) < 4096, f"{len(msg)} tekens")
    check("HTML is gebalanceerd",
          msg.count("<b>") == msg.count("</b>") and msg.count("<i>") == msg.count("</i>")
          and msg.count("<pre>") == msg.count("</pre>"))
    kb = notify.buttons(options, c, st)
    flat = [x for row in kb for x in row]
    check("knoppen voor vlucht, auto en bed",
          any("✈️" in x["text"] for x in flat) and any("Auto" in x["text"] for x in flat)
          and any("Bed" in x["text"] for x in flat))
    check("alle knoppen hebben een https-link", all(x["url"].startswith("https://") for x in flat))
    vroeg = notify.build_message(b, options, c, g, st, out_d, back_d, "new", "early",
                                 2, "Baskenland")
    check("vroeg signaal zegt: nog niet boeken", "Nog niet boeken" in vroeg)
    DEMO_MSG = msg
else:
    DEMO_MSG = ""

# ---------------------------------------------------------------
# 14. Meldgrens en poll.
# ---------------------------------------------------------------
check("meldgrens staat op 75", CFG["alerts"]["min_score"] == 75)
check("poll alleen bij echt goede swells", CFG["alerts"]["poll_min_score"] > CFG["alerts"]["min_score"])
check("geen betaalde vluchtzoeker meer in de config", "apify" not in CFG)

# ---------------------------------------------------------------
# 18. Eigen slaapplekken uit stays.yaml.
# ---------------------------------------------------------------
spot_bio = spot(name="La Graviere (Hossegor)", lat=43.665, lon=-1.44)
leeg = booking.stay_for(spot_bio, date(2026, 10, 14), date(2026, 10, 18), 50, 2,
                        CFG["links"]["stay"], {})
check("zonder eigen adres rekent hij met het plafond", leeg.total == 200)
check("zoeklink gebruikt de coordinaten van de spot",
      "43.665" in leeg.link and "-1.44" in leeg.link, leeg.link[:80])
check("zoeklink filtert op gratis annuleren", "fc%3D2" in leeg.link)

bekend = booking.stay_for(
    spot_bio, date(2026, 10, 14), date(2026, 10, 18), 50, 2, CFG["links"]["stay"],
    {"La Graviere (Hossegor)": [{"naam": "Camping La Civelle", "eur_night": 22}]})
check("eigen adres verslaat het plafond", bekend.total == 88, f"{bekend.total}")

gear = booking.gear_for(30, date(2026, 10, 14), date(2026, 10, 18))
check("board en pak worden per dag gerekend", gear.total == 120)

# ---------------------------------------------------------------
# 19. Bericht bouwen, met en zonder vluchtprijs.
# ---------------------------------------------------------------
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
