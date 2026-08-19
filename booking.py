"""Huurauto en slaapplek.

Bewuste keuze: hier wordt niets gescrapet. Voor auto's en hostels bestaat
geen gratis API, en een scraper die stukgaat op een siteweziging is erger
dan geen scraper. Wat het voorstel geeft is een realistische schatting
voor de begroting plus een kant-en-klare zoeklink met de datums en het
prijsplafond er al in.

Waarom geen vaste lijst met hostelnamen: die veroudert en gaat over de
kop, en een verkeerde naam in het voorstel is erger dan een filterlink
die altijd klopt.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


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
class Stay:
    city: str
    max_eur_night: float
    nights: int
    link: str

    @property
    def total(self) -> float:
        return self.max_eur_night * self.nights


def _fill(tpl: str, **kw) -> str:
    out = tpl
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def car_for(airport: str, city: str, out_d: date, back_d: date,
            eur_day_table: dict, link_tpl: str) -> Car:
    days = max((back_d - out_d).days, 1)
    return Car(
        airport=airport,
        eur_day=float(eur_day_table.get(airport, 35)),
        days=days,
        link=_fill(link_tpl, AIRPORT=airport, airport=airport.lower(), city=city,
                   out=out_d.isoformat(), back=back_d.isoformat()),
    )


def stay_for(city: str, out_d: date, back_d: date,
             max_eur_night: float, people: int, link_tpl: str) -> Stay:
    nights = max((back_d - out_d).days, 1)
    return Stay(
        city=city,
        max_eur_night=max_eur_night,
        nights=nights,
        link=_fill(link_tpl, city=city, out=out_d.isoformat(), back=back_d.isoformat(),
                   people=people, maxprice=int(max_eur_night)),
    )
