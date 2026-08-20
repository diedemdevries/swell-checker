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
    """Wat de periode betekent, in gewone taal."""
    if p >= 14:
        return "lange grondzwelling, dit is het echte werk"
    if p >= 11:
        return "nette grondzwelling"
    if p >= 9:
        return "korte zwelling, prima maar niet bijzonder"
    return "windzwelling, verwacht er niet te veel van"


def build_message(block, flight, car, gear, stay, reason: str, tier: str,
                  people: int, region_name: str, runner_up=None,
                  reference_eur: Optional[float] = None,
                  flight_error: Optional[str] = None) -> str:
    spot = block.spot
    head = {"new": "SWELL IN BEELD", "confirm": "BEVESTIGD",
            "upgrade": "OPGEWAARDEERD"}.get(reason, "SWELL IN BEELD")
    sub = ("vroege waarschuwing, forecast kan nog draaien"
           if tier == "early" else "binnen bereik, dit staat er echt")

    lines = [
        f"<b>{_e(head)} — {_e(spot['name'])}</b>",
        f"<i>{_e(region_name)} · {_e(sub)}</i>",
        "",
        f"<b>{block.n_days} goede dagen</b> · {_e(nl_date(block.start))}"
        f" t/m {_e(nl_date(block.end))}",
        f"Tot <b>{block.peak_surf_ft:.0f}ft</b> op <b>{block.peak_period_s:.0f}s</b>"
        f" — {_e(period_verdict(block.peak_period_s))}",
        f"Score <b>{block.score:.0f}</b>/100",
        "",
        "<b>Per dag</b>",
    ]
    for d in block.days:
        wind = f"{d.wind_kt:.0f}kt{' offshore' if d.offshore else ''}"
        lines.append(f"· {_e(nl_date(d.day))}  {d.surf_ft:.0f}ft @ {d.period_s:.0f}s"
                     f"  ·  {_e(wind)}  ·  {_e(d.window)}")

    # ---------------- begroting ----------------
    lines += ["", "<b>Wat het kost (per persoon)</b>"]

    if flight is None or flight.price_eur is None:
        why = f" — {_e(flight_error)}" if flight_error else ""
        lines.append(f"✈️ <b>Geen vluchtprijs</b>{why}")
        if flight is not None and flight.link:
            lines.append(f"   <a href=\"{_e(flight.link)}\">zelf zoeken</a>")
    else:
        duur = ("" if reference_eur is None or flight.price_eur <= reference_eur
                else "  ⚠️ prijzig")
        lines.append(
            f"✈️ {_e(flight.origin)}→{_e(flight.dest)}  EUR {flight.price_eur:.0f}"
            f"  ({_e(flight.carrier)}, direct){_e(duur)}"
            f"  <a href=\"{_e(flight.link)}\">check</a>"
        )

    car_pp = car.total / max(people, 1)
    lines.append(f"🚗 Auto  ~EUR {car_pp:.0f}  ({car.days}d à EUR {car.eur_day:.0f},"
                 f" gedeeld)  <a href=\"{_e(car.link)}\">zoek</a>")
    lines.append(f"🏄 Board + pak  ~EUR {gear.total:.0f}"
                 f"  ({gear.days}d à EUR {gear.eur_day:.0f})")

    if stay.known:
        k = min(stay.known, key=lambda x: x.get("eur_night", 999))
        note = f" — {k['note']}" if k.get("note") else ""
        lines.append(f"🛏️ {_e(k.get('naam', 'bekend adres'))}"
                     f"  ~EUR {stay.total:.0f}  ({stay.nights} nachten"
                     f" à EUR {k.get('eur_night', '?')}){_e(note)}")
    else:
        lines.append(f"🛏️ Bed  tot EUR {stay.total:.0f}  ({stay.nights} nachten,"
                     f" gratis annuleren)  <a href=\"{_e(stay.link)}\">zoek</a>")

    if flight is not None and flight.price_eur is not None:
        ceiling = flight.price_eur + car_pp + gear.total + stay.total
        floor = ceiling - stay.total * 0.4
        lines.append(f"<b>Totaal ~EUR {floor:.0f}-{ceiling:.0f} p.p.</b>"
                     f" voor {stay.nights} nachten")

    # ---------------- reis ----------------
    if flight is not None:
        out_d = date.fromisoformat(flight.out_date)
        back_d = date.fromisoformat(flight.back_date)
        lines += ["", f"🛫 Heen {_e(nl_date(out_d))} · terug {_e(nl_date(back_d))}"]
        lines.append(f"📍 {_e(flight.dest_name)} → {_e(spot['name'])},"
                     f" {flight.drive_min} min rijden")
        if flight.total_sessions and flight.price_eur is not None:
            if flight.misses_sessions:
                lines.append(f"⚠️ Je mist {flight.misses_sessions} van de"
                             f" {flight.total_sessions} surfdagen met deze vlucht"
                             f" — dit was wel de beste combinatie van prijs en tijd.")
            else:
                lines.append(f"✅ Alle {flight.total_sessions} surfdagen blijven overeind")

    if runner_up is not None:
        lines += ["", f"<i>Ook in beeld: {_e(runner_up.spot['name'])}"
                      f" ({runner_up.n_days} dagen, score {runner_up.score:.0f})</i>"]

    if flight_error and flight is not None and flight.price_eur is not None:
        # Prijs gevonden, maar er ging onderweg iets mis. Niet verzwijgen.
        lines += ["", f"<i>Let op: de vluchtzoeker gaf ook een fout"
                      f" ({_e(flight_error)}) — mogelijk zijn niet alle datums"
                      f" bekeken.</i>"]

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
