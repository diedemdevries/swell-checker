"""Forecast ophalen bij Open-Meteo.

Twee endpoints: het marine-model voor de deining, het gewone weermodel
voor de wind. Allebei gratis, geen sleutel, geen registratie. We vragen
timezone=auto op zodat de tijden die terugkomen al lokale tijd zijn --
dat is precies wat we nodig hebben voor het ochtendvenster.

Surfline gebruiken we bewust NIET voor de brede scan: dat werkt per
spotId en zou tientallen calls per run kosten op een endpoint dat niet
voor ons bedoeld is. Zie confirm_with_surfline() voor de check achteraf.
"""

import time
from datetime import date, datetime
from typing import Dict, List

import requests

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_VARS = "swell_wave_height,swell_wave_period,swell_wave_direction,wave_height"
WIND_VARS = "wind_speed_10m,wind_direction_10m"


class ForecastError(RuntimeError):
    pass


def _get(url: str, params: dict, tries: int = 3) -> dict:
    last = None
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 + attempt * 3)
                last = ForecastError("rate limited (429)")
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1 + attempt * 2)
    raise ForecastError(f"{url} faalde na {tries} pogingen: {last}")


def fetch_spot(spot: dict, days: int = 7) -> List[dict]:
    """Haal de forecast voor een spot op en geef genormaliseerde uurrijen terug.

    Elke rij: {time, swell_m, period_s, swell_from, wind_kt, wind_from}
    """
    common = {"latitude": spot["lat"], "longitude": spot["lon"],
              "timezone": "auto", "forecast_days": days}

    marine = _get(MARINE_URL, {**common, "hourly": MARINE_VARS})
    wind = _get(WEATHER_URL, {**common, "hourly": WIND_VARS, "wind_speed_unit": "kn"})

    return merge_hourly(marine, wind)


def merge_hourly(marine: dict, wind: dict) -> List[dict]:
    """Voeg de twee modellen samen op tijdstempel. Rijen met gaten vallen af."""
    mh = marine.get("hourly") or {}
    wh = wind.get("hourly") or {}
    if not mh.get("time"):
        raise ForecastError("marine-response bevat geen uurdata")

    windmap = {
        t: (s, d)
        for t, s, d in zip(
            wh.get("time", []),
            wh.get("wind_speed_10m", []),
            wh.get("wind_direction_10m", []),
        )
    }

    rows: List[dict] = []
    for i, t in enumerate(mh["time"]):
        h = mh["swell_wave_height"][i]
        p = mh["swell_wave_period"][i]
        d = mh["swell_wave_direction"][i]
        w = windmap.get(t)
        if None in (h, p, d) or w is None or None in w:
            continue
        rows.append({
            "time": t,
            "swell_m": float(h),
            "period_s": float(p),
            "swell_from": float(d),
            "wind_kt": float(w[0]),
            "wind_from": float(w[1]),
        })
    return rows


def group_by_day(rows: List[dict]) -> Dict[date, List[dict]]:
    out: Dict[date, List[dict]] = {}
    for r in rows:
        d = datetime.fromisoformat(r["time"]).date()
        out.setdefault(d, []).append(r)
    return out


# --------------------------------------------------------------------
#  Surfline-bevestiging: alleen voor de handvol spots die er doorheen
#  komen. Dit is hetzelfde publieke kbyg-endpoint dat de Swell Event
#  workflow gebruikt. Valt het om, dan gaat het voorstel gewoon door
#  op basis van Open-Meteo -- dit is een extraatje, geen afhankelijkheid.
# --------------------------------------------------------------------
SURFLINE_WAVE = "https://services.surfline.com/kbyg/spots/forecasts/wave"


def confirm_with_surfline(surfline_spot_id: str, days: int = 5):
    """Geeft (min_ft, max_ft) volgens Surfline terug, of None bij een fout."""
    if not surfline_spot_id:
        return None
    try:
        r = requests.get(
            SURFLINE_WAVE,
            params={"spotId": surfline_spot_id, "days": days, "intervalHours": 3},
            timeout=20,
            headers={"User-Agent": "surf-check/1.0"},
        )
        r.raise_for_status()
        data = r.json()["data"]["wave"]
        peak = max(data, key=lambda w: w["surf"]["max"])
        return (peak["surf"]["min"], peak["surf"]["max"])
    except Exception:  # noqa: BLE001
        return None
