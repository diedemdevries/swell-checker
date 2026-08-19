"""Het voorstel bouwen en naar Telegram sturen."""

import html
import os
from datetime import date
from typing import List, Optional

import requests

API = "https://api.telegram.org/bot{token}/{method}"

DUTCH_DAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]
DUTCH_MONTHS = ["", "jan", "feb", "mrt", "apr", "mei", "jun",
                "jul", "aug", "sep", "okt", "nov", "dec"]


def nl_date(d: date) -> str:
    return f"{DUTCH_DAYS[d.weekday()]} {d.day} {DUTCH_MONTHS[d.month]}"


def _e(s) -> str:
    return html.escape(str(s))


def period_verdict(p: float) -> str:
    """Zegt in gewone taal wat de periode betekent -- de belangrijkste knop."""
    if p >= 14:
        return "lange grondzwelling, dit is het echte werk"
    if p >= 11:
        return "nette grondzwelling"
    if p >= 9:
        return "korte zwelling, prima maar niet bijzonder"
    return "windzwelling, verwacht er niet te veel van"


def build_message(block, flight, car, stay, reason: str, tier: str,
                  people: int, runner_up=None, reference_eur: float = None) -> str:
    spot = block.spot
    head = {
        "new": "SWELL IN BEELD",
        "confirm": "BEVESTIGD",
        "upgrade": "OPGEWAARDEERD",
    }.get(reason, "SWELL IN BEELD")

    sub = ("vroege waarschuwing, forecast kan nog draaien"
           if tier == "early" else "binnen bereik, dit staat er echt")

    out_d = date.fromisoformat(flight.out_date)
    back_d = date.fromisoformat(flight.back_date)
    nights = max((back_d - out_d).days, 1)

    lines = [
        f"<b>{_e(head)} — {_e(spot['name'])}</b>",
        f"<i>{_e(spot['region'])} · {_e(sub)}</i>",
        "",
        f"<b>{block.n_days} goede dagen</b> · {_e(nl_date(block.start))} t/m {_e(nl_date(block.end))}",
        f"Tot <b>{block.peak_surf_ft:.0f}ft</b> op <b>{block.peak_period_s:.0f}s</b>"
        f" — {_e(period_verdict(block.peak_period_s))}",
        f"Score <b>{block.score:.0f}</b>/100",
        "",
        "<b>Per dag</b>",
    ]
    for d in block.days:
        wind = f"{d.wind_kt:.0f}kt{' offshore' if d.offshore else ''}"
        lines.append(
            f"· {_e(nl_date(d.day))}  {d.surf_ft:.0f}ft @ {d.period_s:.0f}s"
            f"  ·  {_e(wind)}  ·  {_e(d.window)}"
        )

    # --- begroting ---
    car_pp = car.total / max(people, 1)
    stay_pp = stay.total
    flight_pp = flight.price_eur

    lines += ["", "<b>Wat het kost (per persoon)</b>"]
    if flight_pp is None:
        lines.append(f"✈️ Vlucht — <a href=\"{_e(flight.link)}\">prijs zelf checken</a>")
    else:
        duur = "" if reference_eur is None or flight_pp <= reference_eur else "  ⚠️ prijzig"
        lines.append(
            f"✈️ Vlucht  EUR {flight_pp:.0f}  ({_e(flight.origin)}→{_e(flight.dest)},"
            f" {_e(flight.carrier)}){_e(duur)}  <a href=\"{_e(flight.link)}\">check</a>"
        )
    lines.append(
        f"🚗 Auto  ~EUR {car_pp:.0f}  ({car.days}d à EUR {car.eur_day:.0f}, gedeeld)"
        f"  <a href=\"{_e(car.link)}\">zoek</a>"
    )
    lines.append(
        f"🛏️ Bed  tot EUR {stay_pp:.0f}  ({nights} nachten, plafond EUR"
        f" {stay.max_eur_night:.0f}/nacht)  <a href=\"{_e(stay.link)}\">zoek</a>"
    )
    if flight_pp is not None:
        ceiling = flight_pp + car_pp + stay_pp
        floor = flight_pp + car_pp + stay_pp * 0.6
        lines.append(
            f"<b>Totaal ~EUR {floor:.0f}-{ceiling:.0f} p.p.</b> voor {nights} nachten"
        )
        lines.append("<i>Bed is een plafond, geen offerte — de onderkant is wat een "
                     "dorm meestal doet.</i>")
    else:
        lines.append("<i>Totaal onbekend zolang de vluchtprijs mist</i>")

    lines += [
        "",
        f"🛫 Heen {_e(nl_date(out_d))} · terug {_e(nl_date(back_d))}",
        f"📍 {_e(car.airport)} → {_e(spot['name'])}, {spot['drive_min']} min rijden",
    ]

    # De goedkoopste vlucht valt niet altijd precies om het blok heen.
    gemist = []
    if out_d > block.start:
        gemist.append(f"de eerste {(out_d - block.start).days} dag(en)")
    if back_d < block.end:
        gemist.append(f"de laatste {(block.end - back_d).days} dag(en)")
    if gemist:
        lines.append(f"<i>Let op: met deze vlucht mis je {_e(' en '.join(gemist))} "
                     f"van de swell — dit was wel de goedkoopste.</i>")

    if runner_up is not None:
        lines += ["", f"<i>Ook in beeld: {_e(runner_up.spot['name'])}"
                      f" ({runner_up.n_days} dagen, score {runner_up.score:.0f})</i>"]

    if tier == "early":
        lines += ["", "<i>Nog niet boeken op dit bericht alleen — er volgt een "
                      "bevestiging zodra de swell binnen vijf dagen zit.</i>"]

    return "\n".join(lines)


class Telegram:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None,
                 dry_run: bool = False):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.dry_run = dry_run or not (self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if self.dry_run:
            print("--- [dry run] Telegram-bericht ---")
            print(text)
            print("--- einde bericht ---")
            return True
        r = requests.post(
            API.format(token=self.token, method="sendMessage"),
            json={"chat_id": self.chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        if not r.ok:
            print(f"Telegram sendMessage faalde: {r.status_code} {r.text[:300]}")
        return r.ok

    def poll(self, question: str, options: List[str]) -> bool:
        if self.dry_run:
            print(f"--- [dry run] poll: {question} {options}")
            return True
        r = requests.post(
            API.format(token=self.token, method="sendPoll"),
            json={"chat_id": self.chat_id, "question": question[:300],
                  "options": options, "is_anonymous": False},
            timeout=20,
        )
        if not r.ok:
            print(f"Telegram sendPoll faalde: {r.status_code} {r.text[:300]}")
        return r.ok
