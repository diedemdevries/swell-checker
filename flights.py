"""Vluchten: vaste opties per regio, geen live zoektocht.

Waarom geen live prijzen meer: de bot ging vaak af, en elke melding kostte
een betaalde zoekopdracht. Voor jullie maakt het weinig uit. Per regio zijn
er maar een paar directe routes vanuit de Benelux, en die veranderen niet
van week tot week. Die staan in config.yaml met een richtprijs. Het bericht
noemt de beste optie plus een alternatief, en de knop opent Skyscanner met
de datums al ingevuld. De echte prijs zie je daar met een tik.

Richtprijzen zijn per persoon, retour, alleen een rugzak, geboekt op korte
termijn (3 tot 9 dagen vooruit). Gemeten in oktober 2026. Verder vooruit
boeken is vaak de helft goedkoper.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Tuple

# Een uur extra rijden telt als zoveel euro p.p. bij het kiezen van de
# beste optie. Voorkomt dat een vlucht die 3 uur verderop landt wint op een
# paar tientjes.
DRIVE_EUR_PER_HOUR = 20.0


@dataclass
class Option:
    origin: str
    origin_name: str
    dest: str
    dest_name: str
    airline: str
    typical_eur: float
    drive_min: int
    link: str
    note: str = ""

    @property
    def weight(self) -> float:
        return self.typical_eur + DRIVE_EUR_PER_HOUR * self.drive_min / 60.0


def trip_dates(start: date, end: date) -> Tuple[date, date]:
    """Heen de dag voor de eerste goede dag, terug op de laatste dag.

    Zo surf je elke goede ochtend, ook de laatste, en vlieg je die avond
    terug. Aankomst- en vertrektijden maken jullie niet uit.
    """
    return start - timedelta(days=1), end


def search_link(tpl: str, origin: str, dest: str, out_d: date, back_d: date,
                people: int) -> str:
    return (tpl.replace("{origin}", origin.lower())
               .replace("{dest}", dest.lower())
               .replace("{out_short}", out_d.strftime("%y%m%d"))
               .replace("{back_short}", back_d.strftime("%y%m%d"))
               .replace("{people}", str(people)))


def options_for(spot: dict, region: dict, origin_names: dict,
                out_d: date, back_d: date, people: int, link_tpl: str,
                max_drive_min: int) -> List[Option]:
    """Alle vaste routes die bij deze spot passen, beste eerst."""
    drive = spot.get("drive_min") or {}
    airports = {a["code"]: a["name"] for a in region.get("airports", [])}
    out: List[Option] = []
    for r in region.get("flights") or []:
        dest = r["to"]
        if dest not in drive or drive[dest] > max_drive_min:
            continue
        out.append(Option(
            origin=r["from"],
            origin_name=origin_names.get(r["from"], r["from"]),
            dest=dest,
            dest_name=airports.get(dest, dest),
            airline=r.get("airline", ""),
            typical_eur=float(r["eur"]),
            drive_min=int(drive[dest]),
            link=search_link(link_tpl, r["from"], dest, out_d, back_d, people),
            note=r.get("note", ""),
        ))
    out.sort(key=lambda o: o.weight)
    return out
