"""Verzonnen forecasts, zodat de logica te testen is zonder internet."""

from datetime import date, timedelta


def make_rows(start: date, days: int, swell_m: float, period_s: float,
              swell_from: float, wind_kt: float, wind_from: float,
              afternoon_wind_kt: float = None, afternoon_from: float = None):
    """Bouw uurrijen zoals forecast.merge_hourly ze zou opleveren.

    afternoon_wind_kt laat je de thermische zeewind nabootsen die 's middags
    aantrekt -- dat mag een dag niet diskwalificeren.
    """
    rows = []
    for d in range(days):
        day = start + timedelta(days=d)
        for h in range(24):
            if afternoon_wind_kt is not None and h >= 12:
                wk, wf = afternoon_wind_kt, (afternoon_from
                                             if afternoon_from is not None else wind_from)
            else:
                wk, wf = wind_kt, wind_from
            rows.append({
                "time": f"{day.isoformat()}T{h:02d}:00",
                "swell_m": swell_m,
                "period_s": period_s,
                "swell_from": swell_from,
                "wind_kt": wk,
                "wind_from": wf,
            })
    return rows


def spot(**over):
    base = {
        "name": "Testspot", "region": "baskenland",
        "lat": 43.0, "lon": -1.5,
        "faces": 285, "swell_window": [260, 340],
        "size_factor": 1.2,
        "drive_min": {"BIQ": 40, "BOD": 105, "BIO": 145},
        "tier": "near", "season": list(range(1, 13)),
    }
    base.update(over)
    return base


def demo_block(cfg):
    """Een fraai blok, puur om het Telegram-bericht te kunnen bekijken."""
    from datetime import date as _date
    from forecast import group_by_day
    from scoring import find_blocks, score_day, score_hour

    s = cfg["spots"][0]
    c = cfg["criteria"]
    start = _date.today() + timedelta(days=3)

    # Mik het midden van de toegestane band, wat de size_factor van deze
    # spot ook is -- anders valt de demo om op "te groot".
    period = 15.0
    target_ft = (c["min_surf_ft"] + c["max_surf_ft"]) / 2.0
    boost = max(0.75, min(period / 12.0, 1.35))
    swell_m = target_ft / (3.28084 * s["size_factor"] * boost)

    rows = make_rows(start, 4, swell_m=swell_m, period_s=period,
                     swell_from=s["swell_window"][0] + 25,
                     wind_kt=7, wind_from=(s["faces"] + 180) % 360,
                     afternoon_wind_kt=18)
    by_day = group_by_day(rows)
    days = [score_day(d, [score_hour(r, s, c) for r in by_day[d]], c)
            for d in sorted(by_day)]
    blocks = find_blocks(s, days, cfg["tiers"][s["tier"]]["min_days"])
    if not blocks:
        raise RuntimeError("demo kon geen blok bouwen -- criteria te streng?")
    return blocks[0]
