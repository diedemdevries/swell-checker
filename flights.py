"""Goedkoopste vlucht zoeken.

Er bestaat geen gratis, betrouwbare API die alle prijsvechters afdekt.
Wat we wel kunnen: Ryanair's eigen fare finder is publiek en gratis, en
Ryanair vliegt vanaf precies de vliegvelden die voor ons interessant zijn
(Eindhoven, Weeze, Charleroi, Brussel). Dat vangt het grootste deel.

Lukt het niet -- endpoint dicht, route niet gevlogen, Transavia is
goedkoper -- dan valt het voorstel terug op een zoeklink. Beter een
eerlijke link dan een verzonnen prijs.
"""

import time
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import requests

RYANAIR_HOSTS = [
    "https://services-api.ryanair.com/farfnd/v4/roundTripFares",
    "https://www.ryanair.com/api/farfnd/v4/roundTripFares",
]


@dataclass
class Flight:
    origin: str
    origin_name: str
    dest: str
    out_date: str
    back_date: str
    price_eur: Optional[float]
    carrier: str
    link: str
    estimated: bool = False       # True = geen echte prijs gevonden

    def label(self) -> str:
        if self.price_eur is None:
            return f"{self.origin}->{self.dest} (prijs niet opgehaald)"
        return f"{self.origin}->{self.dest} EUR {self.price_eur:.0f} retour ({self.carrier})"


def _ryanair_roundtrip(origin: str, dest: str, out_d: date, back_d: date) -> Optional[dict]:
    params = {
        "departureAirportIataCode": origin,
        "arrivalAirportIataCode": dest,
        "outboundDepartureDateFrom": out_d.isoformat(),
        "outboundDepartureDateTo": out_d.isoformat(),
        "inboundDepartureDateFrom": back_d.isoformat(),
        "inboundDepartureDateTo": back_d.isoformat(),
        "currency": "EUR",
        "market": "nl-nl",
        "adultPaxCount": 1,
    }
    for host in RYANAIR_HOSTS:
        try:
            r = requests.get(host, params=params, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            if r.status_code != 200:
                continue
            fares = (r.json() or {}).get("fares") or []
            if not fares:
                continue
            best = min(fares, key=lambda f: (f.get("summary") or {}).get("price", {}).get("value", 9e9))
            val = (best.get("summary") or {}).get("price", {}).get("value")
            if val:
                return {"price": float(val)}
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
            continue
    return None


def search_link(tpl: str, origin: str, dest: str, out_d: date, back_d: date, people: int) -> str:
    return (tpl.replace("{origin}", origin.lower())
               .replace("{ORIGIN}", origin)
               .replace("{dest}", dest.lower())
               .replace("{DEST}", dest)
               .replace("{out}", out_d.isoformat())
               .replace("{back}", back_d.isoformat())
               .replace("{out_short}", out_d.strftime("%y%m%d"))
               .replace("{back_short}", back_d.strftime("%y%m%d"))
               .replace("{people}", str(people)))


def cheapest(origins: List[dict], dest: str, out_d: date, back_d: date,
             link_tpl: str, people: int = 1) -> Flight:
    """Loop de vertrekvliegvelden af en geef de goedkoopste terug.

    De volgorde in de config is de tiebreak: staat Eindhoven bovenaan en
    is de prijs gelijk, dan wint Eindhoven.
    """
    found: List[Flight] = []
    for o in origins:
        res = _ryanair_roundtrip(o["code"], dest, out_d, back_d)
        if res:
            found.append(Flight(
                origin=o["code"], origin_name=o["name"], dest=dest,
                out_date=out_d.isoformat(), back_date=back_d.isoformat(),
                price_eur=res["price"] * 1.0, carrier="Ryanair",
                link=search_link(link_tpl, o["code"], dest, out_d, back_d, people),
            ))
    if found:
        return min(found, key=lambda f: f.price_eur)

    # Niets gevonden: geef de eerste origin met alleen een zoeklink terug.
    o = origins[0]
    return Flight(
        origin=o["code"], origin_name=o["name"], dest=dest,
        out_date=out_d.isoformat(), back_date=back_d.isoformat(),
        price_eur=None, carrier="?",
        link=search_link(link_tpl, o["code"], dest, out_d, back_d, people),
        estimated=True,
    )
