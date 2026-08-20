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
import booking, flights, notify  # noqa: E402

fake_cfg = dict(CFG)
fake_cfg["spots"] = [spot(name="Hossegor Test", region="baskenland", tier="near")]


def fake_fetch(sp, days=7):
    return make_rows(TODAY + timedelta(days=3), 4, 2.0, 15.0, GOOD_SWELL_DIR,
                     6, OFFSHORE_FROM, afternoon_wind_kt=20, afternoon_from=ONSHORE_FROM)


blocks = scan(fake_cfg, TODAY, fetch=fake_fetch)
check("scan vindt het blok", len(blocks) == 1, f"{len(blocks)}")

if blocks:
    b = blocks[0]
    out_d, back_d = b.start - timedelta(days=1), b.end + timedelta(days=1)
    c = booking.car_for("BIQ", 42, out_d, back_d, CFG["links"]["car"])
    g = booking.gear_for(35, out_d, back_d)
    st = booking.stay_for(b.spot, out_d, back_d, 50, 2, CFG["links"]["stay"], {})

    f = flights.Flight("EIN", "BIQ", "Biarritz", out_d.isoformat(),
                       back_d.isoformat(), 118.0, "Transavia", 0, 40, "https://x",
                       sessions_kept=b.n_days, total_sessions=b.n_days)
    msg = notify.build_message(b, f, c, g, st, "new", "confirm", 2,
                               "Baskenland", None, 200)
    check("bericht bevat de spot, de dagen en een totaalbedrag",
          "Hossegor Test" in msg and "Totaal" in msg and "ft" in msg)
    check("bericht meldt dat alle surfdagen overeind blijven", "Alle" in msg)
    check("bericht is niet absurd lang voor Telegram", len(msg) < 4096, f"{len(msg)} tekens")
    check("HTML is gebalanceerd", msg.count("<b>") == msg.count("</b>"))
    check("board en pak staan in de begroting", "Board + pak" in msg)

    f2 = flights.Flight("EIN", "BIQ", "Biarritz", out_d.isoformat(),
                        back_d.isoformat(), 118.0, "Transavia", 0, 40, "https://x",
                        sessions_kept=b.n_days - 1, total_sessions=b.n_days)
    check("bericht waarschuwt als de vlucht surfdagen kost",
          "mist" in notify.build_message(b, f2, c, g, st, "new", "confirm", 2,
                                         "Baskenland", None, 200))

    kapot = notify.build_message(b, f, c, g, st, "new", "confirm", 2, "Baskenland",
                                 None, 200, "Apify-token afgekeurd")
    check("storing wordt gemeld ook als er tóch een prijs was",
          "Apify-token afgekeurd" in kapot, "")

    geenprijs = flights.Flight("EIN", "BIQ", "Biarritz", out_d.isoformat(),
                               back_d.isoformat(), None, "?", 0, 40, "https://x",
                               total_sessions=b.n_days)
    zonder = notify.build_message(b, geenprijs, c, g, st, "new", "confirm", 2,
                                  "Baskenland", None, 200, "geen directe vlucht gevonden")
    check("zonder prijs komt er toch een bericht met reden",
          "Geen vluchtprijs" in zonder and "geen directe vlucht" in zonder)
    check("dure vlucht wordt gemarkeerd maar niet geblokkeerd",
          "prijzig" in notify.build_message(
              b, flights.Flight("EIN", "BIQ", "Biarritz", out_d.isoformat(),
                                back_d.isoformat(), 450.0, "KLM", 0, 40, "https://x",
                                sessions_kept=b.n_days, total_sessions=b.n_days),
              c, g, st, "new", "confirm", 2, "Baskenland", None, 200))
    DEMO_MSG = msg
else:
    DEMO_MSG = ""

# ---------------------------------------------------------------
# 13. Datumcombinaties: zinnige heen/terug-paren, niet alles.
# ---------------------------------------------------------------
B_START, B_END = date(2026, 10, 15), date(2026, 10, 18)
pairs = flights.date_pairs(B_START, B_END, date(2026, 10, 1), 2, 2, 6)
check("heenvluchten liggen op of voor de eerste goede dag",
      all(o <= B_START for o, _ in pairs), f"{pairs[:3]}")
check("terugvluchten liggen op of na de laatste goede dag",
      all(b >= B_END for _, b in pairs), f"{pairs[:3]}")
check("geen trip langer dan het maximum",
      all((b - o).days <= 6 for o, b in pairs))
laat = flights.date_pairs(B_START, B_END, B_START, 2, 2, 6)
check("geen vertrekdatum in het verleden",
      all(o >= B_START for o, _ in laat), f"{laat[:3]}")

# ---------------------------------------------------------------
# 14. Sessies tellen: wat houdt een vlucht van de swell over?
# ---------------------------------------------------------------
DAYS = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17)]
check("aankomst de avond ervoor laat alles staan",
      flights.sessions_kept(DAYS, "2026-10-14T21:00:00", "2026-10-18T10:00:00") == 3)
check("aankomst 's middags op dag 1 kost die dag",
      flights.sessions_kept(DAYS, "2026-10-15T14:00:00", "2026-10-18T10:00:00") == 2)
check("aankomst 's ochtends vroeg op dag 1 telt wel mee",
      flights.sessions_kept(DAYS, "2026-10-15T07:00:00", "2026-10-18T10:00:00") == 3)
check("vroege terugvlucht op de laatste dag kost die ochtend",
      flights.sessions_kept(DAYS, "2026-10-14T20:00:00", "2026-10-17T08:00:00") == 2)
check("late terugvlucht op de laatste dag laat hem staan",
      flights.sessions_kept(DAYS, "2026-10-14T20:00:00", "2026-10-17T19:00:00") == 3)
check("zonder tijden valt hij terug op datums",
      flights.sessions_kept(DAYS, None, None) == 3)

# ---------------------------------------------------------------
# 15. Beste vlucht = laagste prijs per behouden sessie.
# ---------------------------------------------------------------
def mkf(price, kept, drive=30, dest="BIO", origin="AMS"):
    return flights.Flight(origin=origin, dest=dest, dest_name=dest,
                          out_date="2026-10-14", back_date="2026-10-18",
                          price_eur=price, carrier="X", stops=0, drive_min=drive,
                          link="https://x", sessions_kept=kept, total_sessions=3)

goedkoop_kort = mkf(150, 1)      # 150 per sessie
duur_lang = mkf(300, 3)          # 100 per sessie
check("duurdere vlucht wint als hij meer surfdagen oplevert",
      flights.best([goedkoop_kort, duur_lang], 40, 30, 50, 2) is duur_lang)
check("bij gelijke sessies wint de goedkoopste",
      flights.best([mkf(200, 3), mkf(140, 3)], 40, 30, 50, 2).price_eur == 140)
check("bij gelijke prijs en sessies wint de korte rit",
      flights.best([mkf(200, 3, drive=200), mkf(200, 3, drive=20)], 40, 30, 50, 2).drive_min == 20)
check("vluchten zonder bruikbare sessie vallen af",
      flights.best([mkf(50, 0)], 40, 30, 50, 2) is None)
check("lege lijst geeft niets terug", flights.best([], 40, 30, 50, 2) is None)

def mkf2(price, kept, out, back):
    return flights.Flight(origin="AMS", dest="AGA", dest_name="Agadir",
                          out_date=out, back_date=back, price_eur=price,
                          carrier="X", stops=0, drive_min=45, link="https://x",
                          sessions_kept=kept, total_sessions=4)

kort = mkf2(274, 4, "2026-08-22", "2026-08-27")   # 5 nachten
lang = mkf2(274, 4, "2026-08-21", "2026-08-27")   # 6 nachten, zelfde vlucht
check("onnodig lange trip verliest van de korte bij gelijke sessies",
      flights.best([lang, kort], 15, 20, 50, 2) is kort)

# ---------------------------------------------------------------
# 16. Apify-antwoorden uitpakken en filteren.
# ---------------------------------------------------------------
PAYLOAD = [{"all_flights": [
    {"price": 274, "airlines": "Transavia", "stops": 0,
     "departure_id": "AMS", "arrival_id": "AGA"},
    {"price": 99, "airlines": "Ryanair", "stops": 1,
     "departure_id": "EIN", "arrival_id": "AGA"},
    {"price": 180, "airlines": "KLM", "stops": 0,
     "departure_id": "AMS", "arrival_id": "XXX"},
    {"airlines": "Kapot", "stops": 0},
]}]
rows = flights._rows(PAYLOAD)
check("alle vluchtrijen worden gevonden", len(rows) == 4, f"{len(rows)}")
fl = flights.to_flights(rows, {"AGA": "Agadir"}, {"AGA": 45},
                        date(2026, 10, 14), date(2026, 10, 18), DAYS,
                        "https://x/{origin}/{dest}", 2, True)
check("tussenstop valt af bij direct-only", all(f.stops == 0 for f in fl))
check("onbekende bestemming valt af", all(f.dest == "AGA" for f in fl))
check("rij zonder prijs valt af", len(fl) == 1, f"{[(f.dest, f.price_eur) for f in fl]}")
check("prijs komt goed door", fl[0].price_eur == 274.0)

fl_stops = flights.to_flights(rows, {"AGA": "Agadir"}, {"AGA": 45},
                              date(2026, 10, 14), date(2026, 10, 18), DAYS,
                              "https://x/{origin}/{dest}", 2, False)
check("met overstap toegestaan komt de tussenstop er wel door", len(fl_stops) == 2)

# ---------------------------------------------------------------
# 17. Bron kapot -> duidelijke fout, geen stille stilte.
# ---------------------------------------------------------------
try:
    flights.search(CFG, [{"code": "AMS"}], ["AGA"], date(2026, 10, 14),
                   date(2026, 10, 18), 2, "")
    check("ontbrekend token geeft een fout", False)
except flights.FlightError as exc:
    check("ontbrekend token geeft een fout", "APIFY_TOKEN" in str(exc), str(exc))

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
