"""Vluchten zoeken via de Apify Google Flights-scraper.

Waarom Apify en niet een luchtvaartmaatschappij-API: de bestemmingen die
er voor ons toe doen worden gevlogen door Transavia, KLM, easyJet en
Ryanair door elkaar heen. Vragen we er maar een, dan missen we het meeste.
Google Flights heeft ze allemaal, en Apify verkoopt dat als een aanroep
die je vanaf GitHub Actions kunt doen.

Bewuste keuze: geen terugval op een tweede bron. Valt Apify om, dan zegt
het bericht dat gewoon. Twee half werkende bronnen naast elkaar is meer
onderhoud dan een duidelijke storingsmelding.

Kosten: de scraper rekent ongeveer een cent per duizend resultaten, en we
roepen hem alleen aan als er al een swell door de filters is. Daarnaast
gaat er een harde uitgavenlimiet mee in de aanroep zelf, zodat een fout
nooit kan uitlopen.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

import requests

API = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


class FlightError(RuntimeError):
    """Bron onbereikbaar of onbruikbaar. Wordt doorgegeven aan het bericht."""


@dataclass
class Flight:
    origin: str
    dest: str
    dest_name: str
    out_date: str
    back_date: str
    price_eur: Optional[float]
    carrier: str
    stops: int
    drive_min: int
    link: str
    out_arrive: Optional[str] = None    # ISO datum-tijd, als de bron die geeft
    back_depart: Optional[str] = None
    sessions_kept: int = 0
    total_sessions: int = 0

    @property
    def misses_sessions(self) -> int:
        return max(self.total_sessions - self.sessions_kept, 0)


# ------------------------------------------------------------------
#  Sessies tellen: wat houdt deze vlucht van de swell over?
# ------------------------------------------------------------------
def _dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "").strip()[:19])
    except ValueError:
        return None


def sessions_kept(days: List[date], out_arrive, back_depart,
                  morning_end_h: int = 11) -> int:
    """Hoeveel ochtendsessies blijven er over met deze vlucht?

    Je kunt een dag surfen als je voor het einde van het ochtendvenster
    aan de grond staat, en als je die dag niet al voor de middag weer
    naar het vliegveld moet.
    """
    arr, dep = _dt(out_arrive), _dt(back_depart)
    kept = 0
    for d in days:
        if arr:
            if arr.date() > d:
                continue                                  # nog niet aangekomen
            if arr.date() == d and arr.hour >= morning_end_h:
                continue                                  # te laat voor de sessie
        if dep:
            if dep.date() < d:
                continue                                  # al vertrokken
            if dep.date() == d and dep.hour < morning_end_h + 2:
                continue                                  # moet naar het vliegveld
        kept += 1
    return kept


def _sessions_by_date(days: List[date], out_d: date, back_d: date) -> int:
    """Terugval als de bron geen tijden geeft: alleen op datum rekenen."""
    return sum(1 for d in days if out_d <= d <= back_d)


# ------------------------------------------------------------------
#  Apify aanroepen
# ------------------------------------------------------------------
def _first_number(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            cleaned = v.replace("EUR", "").replace("€", "").replace(",", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _first_text(d: dict, *keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v[:2])
    return "?"


def _rows(payload) -> List[dict]:
    """Haal de losse vluchten uit wat Apify teruggaf.

    De vorm kan per versie van de scraper verschillen, dus we proberen de
    plekken waar hij redelijkerwijs kan zitten in plaats van er een aan te
    nemen.
    """
    items = payload if isinstance(payload, list) else [payload]
    out: List[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("all_flights", "flights", "best_flights", "other_flights", "results"):
            block = item.get(key)
            if isinstance(block, list):
                out.extend(x for x in block if isinstance(x, dict))
        if not out and ("price" in item or "total_price" in item):
            out.append(item)
    return out


def search(cfg: dict, origins: List[dict], airports: List[str],
           out_d: date, back_d: date, people: int, token: str) -> List[dict]:
    """Een aanroep voor alle vertrekvliegvelden en alle bestemmingen tegelijk."""
    if not token:
        raise FlightError("APIFY_TOKEN ontbreekt")

    ap = cfg["apify"]
    body = {
        "departure_id": ",".join(o["code"] for o in origins),
        "arrival_id": ",".join(airports),
        "outbound_date": out_d.isoformat(),
        "return_date": back_d.isoformat(),
        "adults": people,
        "currency": "EUR",
        "gl": "nl",
        "hl": "nl",
        "max_pages": 1,
        "fetch_booking_options": False,
    }
    if cfg["trip"].get("direct_only"):
        body["stops"] = 1          # Google-conventie: 1 = alleen non-stop

    url = API.format(actor=ap["actor"])
    try:
        r = requests.post(
            url,
            params={"token": token,
                    "maxTotalChargeUsd": ap["max_charge_usd"],
                    "timeout": ap["timeout_s"]},
            json=body,
            timeout=ap["timeout_s"] + 20,
        )
    except requests.RequestException as exc:
        raise FlightError(f"Apify onbereikbaar: {exc}") from exc

    if r.status_code == 402:
        raise FlightError("Apify-tegoed op of uitgavenlimiet bereikt")
    if r.status_code in (401, 403):
        raise FlightError("Apify-token afgekeurd")
    if r.status_code != 200:
        raise FlightError(f"Apify gaf {r.status_code}: {r.text[:200]}")

    try:
        payload = r.json()
    except ValueError as exc:
        raise FlightError(f"Apify gaf geen JSON: {r.text[:200]}") from exc

    rows = _rows(payload)
    if not rows:
        # Geen vluchten is een geldige uitkomst; een onbekende vorm niet.
        sample = payload[0] if isinstance(payload, list) and payload else payload
        keys = sorted(sample.keys())[:12] if isinstance(sample, dict) else type(sample).__name__
        print(f"    geen vluchten in het antwoord (velden gezien: {keys})")
    return rows


def to_flights(rows: List[dict], airports: dict, drive_min: dict,
               out_d: date, back_d: date, days: List[date],
               link_tpl: str, people: int, direct_only: bool) -> List[Flight]:
    """Zet ruwe rijen om in Flight-objecten en gooi weg wat we niet willen."""
    out: List[Flight] = []
    for row in rows:
        price = _first_number(row, "price", "total_price", "fare", "amount")
        if price is None:
            continue
        stops = row.get("stops")
        try:
            stops = int(stops)
        except (TypeError, ValueError):
            stops = 0
        if direct_only and stops > 0:
            continue

        dest = (_first_text(row, "arrival_id", "arrival_airport", "destination_id",
                            "to", "arrivalAirport") or "?")[:3].upper()
        origin = (_first_text(row, "departure_id", "departure_airport", "origin_id",
                              "from", "departureAirport") or "?")[:3].upper()
        if dest not in drive_min:
            continue                       # bestemming hoort niet bij deze spot

        arrive = row.get("arrival_time") or row.get("outbound_arrival_time")
        depart = row.get("return_departure_time") or row.get("inbound_departure_time")
        kept = (sessions_kept(days, arrive, depart)
                if (_dt(arrive) or _dt(depart))
                else _sessions_by_date(days, out_d, back_d))

        out.append(Flight(
            origin=origin, dest=dest, dest_name=airports.get(dest, dest),
            out_date=out_d.isoformat(), back_date=back_d.isoformat(),
            price_eur=price, carrier=_first_text(row, "airlines", "airline", "carrier"),
            stops=stops, drive_min=drive_min.get(dest, 0),
            link=search_link(link_tpl, origin, dest, out_d, back_d, people),
            out_arrive=str(arrive) if arrive else None,
            back_depart=str(depart) if depart else None,
            sessions_kept=kept, total_sessions=len(days),
        ))
    return out


def trip_cost_pp(f: "Flight", car_eur_day: float, rental_eur_day: float,
                 stay_eur_night: float, people: int) -> float:
    """Wat kost deze trip per persoon, alles bij elkaar?

    De vlucht alleen zegt te weinig: elke extra nacht kost ook auto, bed en
    materiaal. Zonder dat erbij zou een vlucht die je een dag langer laat
    blijven er onterecht gunstig uitzien.
    """
    nights = max((date.fromisoformat(f.back_date)
                  - date.fromisoformat(f.out_date)).days, 1)
    return ((f.price_eur or 0.0)
            + (car_eur_day * nights) / max(people, 1)
            + rental_eur_day * nights
            + stay_eur_night * nights)


def best(flights: List[Flight], car_eur_day: float, rental_eur_day: float,
         stay_eur_night: float, people: int) -> Optional[Flight]:
    """Beste = laagste totale kosten per behouden surfsessie.

    Zo wint een duurdere vlucht die je een extra ochtend oplevert vanzelf
    van een goedkope die je die ochtend kost, terwijl een onnodig lange
    trip afvalt op de nachten die hij extra kost. Rijtijd telt licht mee,
    want twee uur rijden is ook een halve ochtend.
    """
    usable = [f for f in flights if f.sessions_kept > 0 and f.price_eur is not None]
    if not usable:
        return None

    def score(f: Flight) -> tuple:
        total = trip_cost_pp(f, car_eur_day, rental_eur_day, stay_eur_night, people)
        drive_penalty = (f.drive_min / 60.0) * 12.0     # 12 euro per uur rijden
        return ((total + drive_penalty) / f.sessions_kept, f.price_eur)

    return min(usable, key=score)


def search_link(tpl: str, origin: str, dest: str, out_d: date, back_d: date,
                people: int) -> str:
    return (tpl.replace("{origin}", origin.lower())
               .replace("{ORIGIN}", origin)
               .replace("{dest}", dest.lower())
               .replace("{DEST}", dest)
               .replace("{out}", out_d.isoformat())
               .replace("{back}", back_d.isoformat())
               .replace("{out_short}", out_d.strftime("%y%m%d"))
               .replace("{back_short}", back_d.strftime("%y%m%d"))
               .replace("{people}", str(people)))


def date_pairs(start: date, end: date, today: date, flex_before: int,
               flex_after: int, max_nights: int) -> List[tuple]:
    """Welke heen/terug-combinaties zijn de moeite van het zoeken waard?

    Niet alle combinaties binnen het venster -- dat zijn er te veel en de
    meeste zijn zinloos. Aankomen doe je de dag ervoor of op dag een;
    terug ga je op de laatste dag of de dag erna.
    """
    outs, backs = [], []
    for i in range(flex_before, -1, -1):
        d = start - timedelta(days=i)
        if d >= today:
            outs.append(d)
    if not outs:
        outs = [max(start, today)]
    for i in range(0, flex_after + 1):
        backs.append(end + timedelta(days=i))

    pairs = []
    for o in outs:
        for b in backs:
            nights = (b - o).days
            if 1 <= nights <= max_nights:
                pairs.append((o, b))
    return pairs
