"""Huurauto, materiaal en slaapplek.

Bewuste keuze: hier wordt niets gescrapet. Voor auto's en bedden bestaat
geen gratis, betrouwbare bron, en een scraper die stukgaat op een
siteweziging is erger dan geen scraper. Wat het voorstel geeft is een
realistische schatting voor de begroting plus een kant-en-klare zoeklink
met de datums, de coordinaten van de spot en het prijsplafond er al in.

De zoeklink filtert op gratis annuleren. Dat is geen detail: jullie boeken
op een verwachting die nog kan draaien, en dan is annuleerbaar meer waard
dan tien euro korting.

Voor bedden waar jullie al geweest zijn is er stays.yaml -- een eigen
lijstje dat na elke trip aangevuld wordt. Dat is op termijn beter dan
welke scraper ook, want het bevat wat jullie er zelf van vonden.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class Car:
    airport: str
    eur_day: float
    days: int
    link: str

    @property
    def total(self) -> float:
        return self.eur_day * self.days


@dataclass
class Gear:
    """Board plus pak huren -- jullie nemen geen bagage mee."""
    eur_day: float
    days: int

    @property
    def total(self) -> float:
        return self.eur_day * self.days


@dataclass
class Stay:
    spot: str
    max_eur_night: float
    nights: int
    link: str
    known: List[dict]          # uit stays.yaml, als jullie er al sliepen

    @property
    def total(self) -> float:
        if self.known:
            cheapest = min(k.get("eur_night", self.max_eur_night) for k in self.known)
            return float(cheapest) * self.nights
        return self.max_eur_night * self.nights


def _fill(tpl: str, **kw) -> str:
    out = tpl
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def car_for(airport: str, eur_day: float, out_d: date, back_d: date,
            link_tpl: str) -> Car:
    days = max((back_d - out_d).days, 1)
    return Car(airport=airport, eur_day=float(eur_day), days=days,
               link=_fill(link_tpl, AIRPORT=airport, airport=airport.lower(),
                          out=out_d.isoformat(), back=back_d.isoformat()))


def gear_for(eur_day: float, out_d: date, back_d: date) -> Gear:
    return Gear(eur_day=float(eur_day), days=max((back_d - out_d).days, 1))


def load_stays(path: Path) -> dict:
    """Eigen adressenlijst. Ontbreekt hij, dan werkt alles gewoon door."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return {}


def stay_for(spot: dict, out_d: date, back_d: date, max_eur_night: float,
             people: int, link_tpl: str, stays: Optional[dict] = None) -> Stay:
    nights = max((back_d - out_d).days, 1)
    known = ((stays or {}).get(spot["name"]) or []) if stays else []
    return Stay(
        spot=spot["name"],
        max_eur_night=float(max_eur_night),
        nights=nights,
        known=known,
        link=_fill(link_tpl, lat=spot["lat"], lon=spot["lon"],
                   out=out_d.isoformat(), back=back_d.isoformat(),
                   people=people, maxprice=int(max_eur_night)),
    )
