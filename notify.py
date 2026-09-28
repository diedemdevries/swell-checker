"""Het voorstel bouwen en naar Telegram sturen.

Opbouw van het bericht: eerst waar, wanneer en wat het kost. Daarna de
vlucht, dan de golven per dag. Links staan niet in de tekst maar als
knoppen eronder.
"""

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


def nl_range(a: date, b: date) -> str:
    if a.month == b.month:
        return f"{DUTCH_DAYS[a.weekday()]} {a.day} – {nl_date(b)}"
    return f"{nl_date(a)} – {nl_date(b)}"


def _e(s) -> str:
    return html.escape(str(s), quote=False)


def period_verdict(p: float) -> str:
    """Wat de periode betekent, in gewone taal."""
    if p >= 14:
        return "lange grondzwelling"
    if p >= 11:
        return "nette grondzwelling"
    if p >= 9:
        return "korte zwelling"
    return "windzwelling"


def _drive(mins: int) -> str:
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h}u{m:02d}" if m else f"{h}u"


def pick_alternative(options):
    """Tweede keus, bij voorkeur naar een ander vliegveld dan de eerste."""
    if len(options) < 2:
        return None
    first = options[0]
    for o in options[1:]:
        if o.dest != first.dest:
            return o
    return options[1]


def total_pp(options, car, gear, stay, people: int) -> float:
    flight = options[0].typical_eur if options else 0.0
    return flight + car.total / max(people, 1) + gear.total + stay.total


def build_message(block, options, car, gear, stay, out_d: date, back_d: date,
                  reason: str, tier: str,
                  people: int, region_name: str, also: Optional[List[str]] = None,
                  hot_score: float = 85.0) -> str:
    spot = block.spot
    # ---------------- kop ----------------
    if tier == "early":
        icon, label = "👀", "VROEG SIGNAAL · "
    elif reason == "confirm":
        icon, label = "✅", "BEVESTIGD · "
    elif reason == "upgrade":
        icon, label = "⬆️", "BETER GEWORDEN · "
    else:
        icon, label = ("🔥" if block.score >= hot_score else "🌊"), ""

    nights = stay.nights
    all_off = all(d.offshore for d in block.days)
    wind = "'s ochtends offshore" if all_off else "'s ochtends weinig wind"

    lines = [
        f"{icon} <b>{_e(label)}{_e(spot['name'].upper())}</b>",
        f"{block.n_days} goede dagen · {_e(nl_range(block.start, block.end))}"
        f" · {_e(region_name)}",
        f"<b>{block.peak_surf_ft:.0f}ft @ {block.peak_period_s:.0f}s</b>"
        f" · {_e(period_verdict(block.peak_period_s))} · {_e(wind)}",
        f"≈ <b>€{total_pp(options, car, gear, stay, people):.0f} p.p.</b>"
        f" alles-in · {nights} nachten",
    ]

    # ---------------- vlucht ----------------
    lines.append("")
    if options:
        best = options[0]
        lines.append(f"✈️ <b>{_e(best.origin_name)} → {_e(best.dest_name)}</b>"
                     f" · {_e(best.airline)} · ~€{best.typical_eur:.0f}")
        lines.append(f"   heen {_e(nl_date(out_d))} · terug {_e(nl_date(back_d))}"
                     f" · {_e(_drive(best.drive_min))} naar de spot")
        alt = pick_alternative(options)
        if alt is not None:
            lines.append(f"   of {_e(alt.origin_name)} → {_e(alt.dest_name)}"
                         f" · {_e(alt.airline)} · ~€{alt.typical_eur:.0f}"
                         f" · {_e(_drive(alt.drive_min))} rijden")
    else:
        lines.append("✈️ Geen vaste directe route bekend voor deze spot")

    # ---------------- golven per dag ----------------
    rows = []
    for d in block.days:
        off = " off" if d.offshore else ""
        rows.append(f"{DUTCH_DAYS[d.day.weekday()]} {d.day.day:<2} "
                    f"{d.surf_ft:>2.0f}ft {d.period_s:>2.0f}s "
                    f"{d.wind_kt:>2.0f}kt{off}")
    lines += ["", "<pre>" + _e("\n".join(rows)) + "</pre>"]

    if also:
        lines.append(f"Ook goed in de buurt: {_e(', '.join(also))}")

    # ---------------- kosten ----------------
    flight_part = f"vlucht ~{options[0].typical_eur:.0f} · " if options else ""
    if stay.known:
        k = min(stay.known, key=lambda x: x.get("eur_night", 999))
        bed = f"{k.get('naam', 'bekend adres')} ~{stay.total:.0f}"
    else:
        bed = f"bed ≤{stay.total:.0f}"
    lines += ["", f"<i>{flight_part}auto ~{car.total / max(people, 1):.0f}"
                  f" · board+pak ~{gear.total:.0f} · {_e(bed)}",
              "Richtprijzen p.p. — de echte prijs zie je via de knoppen.</i>"]

    if tier == "early":
        lines += ["", "<i>Forecast kan nog draaien. Nog niet boeken, er volgt een"
                      " bevestiging als de swell binnen vijf dagen zit.</i>"]

    return "\n".join(lines)


def buttons(options, car, stay) -> List[List[dict]]:
    """Knoppen onder het bericht: vluchten, auto, bed."""
    rows: List[List[dict]] = []
    if options:
        row = [{"text": f"✈️ {options[0].origin}→{options[0].dest}",
                "url": options[0].link}]
        alt = pick_alternative(options)
        if alt is not None:
            row.append({"text": f"✈️ {alt.origin}→{alt.dest}", "url": alt.link})
        rows.append(row)
    rows.append([{"text": "🚗 Auto", "url": car.link},
                 {"text": "🛏️ Bed", "url": stay.link}])
    return rows


class Telegram:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None,
                 dry_run: bool = False):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.dry_run = dry_run or not (self.token and self.chat_id)

    def send(self, text: str, keyboard: Optional[List[List[dict]]] = None) -> bool:
        if self.dry_run:
            print("--- [dry run] Telegram-bericht ---")
            print(text)
            if keyboard:
                print("knoppen: " + " | ".join(b["text"] for row in keyboard for b in row))
            print("--- einde bericht ---")
            return True
        body = {"chat_id": self.chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True}
        if keyboard:
            body["reply_markup"] = {"inline_keyboard": keyboard}
        r = requests.post(API.format(token=self.token, method="sendMessage"),
                          json=body, timeout=20)
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
