"""Van ruwe forecast naar een oordeel: is dit het waard om voor te vliegen?

De keten is: uur -> dag -> aaneengesloten blok -> trip.
Een uur krijgt een score van 0-100. Een score van 0 betekent dat het uur
op minstens een harde eis is afgevallen (te klein, te kort van periode,
te veel wind, verkeerde deiningsrichting).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from geo import ang_diff, in_window, is_offshore, window_center, window_span

M_TO_FT = 3.28084


def surf_height_ft(swell_m: float, period_s: float, size_factor: float) -> float:
    """Schat de brekende golf (face height, ft) uit deining op open zee.

    Open-Meteo geeft de deining zoals die op zee staat. Wat je op de spot
    ziet hangt af van de bodem (size_factor) en van de periode: een lange
    periode draagt meer energie mee naar beneden en bouwt daardoor hoger op.
    """
    swell_ft = swell_m * M_TO_FT
    period_boost = max(0.75, min(period_s / 12.0, 1.35))
    return swell_ft * size_factor * period_boost


def _size_score(surf_ft: float, lo: float, hi: float) -> float:
    """0 buiten de band. Piekt op ~55% van de band en blijft daarboven hoog
    (gevorderd niveau: groot is geen probleem, tot de bovengrens)."""
    if surf_ft < lo or surf_ft > hi:
        return 0.0
    rel = (surf_ft - lo) / (hi - lo) if hi > lo else 1.0
    if rel <= 0.55:
        return 0.55 + 0.45 * (rel / 0.55)
    return 1.0 - 0.25 * ((rel - 0.55) / 0.45)


def _period_score(period_s: float, lo: float, ideal: float) -> float:
    """0 onder de ondergrens. 8s scoort mager, 14s+ vol.

    Dit is bewust de zwaarst wegende component: periode scheidt echte
    grondzwelling van windrommel.
    """
    if period_s < lo:
        return 0.0
    if ideal <= lo:
        return 1.0
    rel = (period_s - lo) / (ideal - lo)
    return 0.25 + 0.75 * max(0.0, min(rel, 1.0))


def _wind_score(wind_kt: float, wind_from: float, faces: float, c) -> float:
    """Offshore verslaat spiegelglad, spiegelglad verslaat lichte onshore."""
    off = is_offshore(wind_from, faces, c["offshore_tolerance_deg"])
    if off:
        if wind_kt <= 12.0:
            return 1.0
        if wind_kt <= c["max_wind_kt_offshore"]:
            return 0.80
        return 0.0
    if wind_kt <= 5.0:
        return 0.85
    if wind_kt <= c["max_wind_kt"]:
        return 0.60
    return 0.0


def _direction_score(swell_from: float, window) -> float:
    """1.0 recht in het venster, aflopend naar 0.6 aan de randen."""
    if not in_window(swell_from, window):
        return 0.0
    half = window_span(window) / 2.0
    if half <= 0:
        return 1.0
    off_center = ang_diff(swell_from, window_center(window))
    return 1.0 - 0.4 * min(off_center / half, 1.0)


@dataclass
class HourScore:
    time: str           # lokale ISO-tijd, bv "2026-09-14T07:00"
    hour: int
    surf_ft: float
    period_s: float
    swell_from: float
    wind_kt: float
    wind_from: float
    offshore: bool
    score: float
    qualifies: bool
    fail: Optional[str] = None


def score_hour(row: dict, spot: dict, criteria: dict) -> HourScore:
    c = criteria
    surf = surf_height_ft(row["swell_m"], row["period_s"], spot["size_factor"])

    s_size = _size_score(surf, c["min_surf_ft"], c["max_surf_ft"])
    s_per = _period_score(row["period_s"], c["min_period_s"], c["ideal_period_s"])
    s_wind = _wind_score(row["wind_kt"], row["wind_from"], spot["faces"], c)
    s_dir = _direction_score(row["swell_from"], spot["swell_window"])

    fail = None
    if s_size == 0.0:
        fail = "te klein" if surf < c["min_surf_ft"] else "te groot"
    elif s_per == 0.0:
        fail = "periode te kort"
    elif s_wind == 0.0:
        fail = "te veel wind"
    elif s_dir == 0.0:
        fail = "deining buiten venster"

    w = c["weights"]
    total = 100.0 * (
        w["size"] * s_size
        + w["period"] * s_per
        + w["wind"] * s_wind
        + w["direction"] * s_dir
    )
    if fail:
        total = 0.0

    return HourScore(
        time=row["time"],
        hour=int(row["time"][11:13]),
        surf_ft=round(surf, 1),
        period_s=row["period_s"],
        swell_from=row["swell_from"],
        wind_kt=row["wind_kt"],
        wind_from=row["wind_from"],
        offshore=is_offshore(row["wind_from"], spot["faces"], c["offshore_tolerance_deg"]),
        score=round(total, 1),
        qualifies=fail is None,
        fail=fail,
    )


@dataclass
class DayScore:
    day: date
    qualifies: bool
    score: float
    good_hours: int
    window: str = ""          # bv "07:00-10:00"
    surf_ft: float = 0.0
    period_s: float = 0.0
    wind_kt: float = 0.0
    offshore: bool = False
    fail: Optional[str] = None


def _longest_run(hours: List[HourScore]) -> List[HourScore]:
    """Langste aaneengesloten reeks kwalificerende uren."""
    best: List[HourScore] = []
    run: List[HourScore] = []
    prev = None
    for h in hours:
        if not h.qualifies:
            run = []
            prev = None
            continue
        if prev is not None and h.hour != prev + 1:
            run = []
        run.append(h)
        prev = h.hour
        if len(run) > len(best):
            best = list(run)
    return best


def score_day(day: date, hours: List[HourScore], criteria: dict) -> DayScore:
    """Een dag telt alleen als er binnen het ochtendvenster genoeg
    aaneengesloten goede uren zitten. De middagwind mag de dag dus niet
    verpesten -- daar surf je toch niet."""
    c = criteria
    morning = [h for h in hours if c["morning_start_h"] <= h.hour <= c["morning_end_h"]]
    if not morning:
        return DayScore(day, False, 0.0, 0, fail="geen ochtenddata")

    run = _longest_run(morning)
    if len(run) < c["min_good_hours"]:
        reasons = [h.fail for h in morning if h.fail]
        common = max(set(reasons), key=reasons.count) if reasons else "te kort venster"
        return DayScore(day, False, 0.0, len(run), fail=common)

    avg = sum(h.score for h in run) / len(run)
    peak = max(run, key=lambda h: h.score)
    return DayScore(
        day=day,
        qualifies=avg >= c["min_day_score"],
        score=round(avg, 1),
        good_hours=len(run),
        window=f"{run[0].hour:02d}:00-{run[-1].hour + 1:02d}:00",
        surf_ft=peak.surf_ft,
        period_s=peak.period_s,
        wind_kt=peak.wind_kt,
        offshore=peak.offshore,
        fail=None if avg >= c["min_day_score"] else f"score {avg:.0f} onder drempel",
    )


@dataclass
class Block:
    spot: dict
    days: List[DayScore]
    score: float = 0.0        # weergave, 0-100
    rank_score: float = 0.0   # voor het rangschikken, mag boven 100 uitkomen
    peak_surf_ft: float = 0.0
    peak_period_s: float = 0.0

    @property
    def start(self) -> date:
        return self.days[0].day

    @property
    def end(self) -> date:
        return self.days[-1].day

    @property
    def n_days(self) -> int:
        return len(self.days)

    def key(self) -> str:
        """Identiteit van deze swell, voor het onthouden wat al gemeld is."""
        return f"{self.spot['name']}|{self.start.isoformat()}"


def find_blocks(spot: dict, days: List[DayScore], min_days: int) -> List[Block]:
    """Aaneengesloten reeksen goede dagen van minimaal min_days lang."""
    blocks: List[Block] = []
    run: List[DayScore] = []

    def flush():
        if len(run) >= min_days:
            b = Block(spot=spot, days=list(run))
            # Blokscore: gemiddelde dagscore, met een kleine bonus per extra
            # dag boven het minimum -- vijf dagen goed is meer waard dan twee.
            avg = sum(d.score for d in run) / len(run)
            b.rank_score = round(avg * (1.0 + 0.06 * (len(run) - min_days)), 1)
            b.score = round(min(b.rank_score, 100.0), 1)
            b.peak_surf_ft = max(d.surf_ft for d in run)
            b.peak_period_s = max(d.period_s for d in run)
            blocks.append(b)

    prev = None
    for d in days:
        if not d.qualifies:
            flush()
            run = []
            prev = None
            continue
        if prev is not None and (d.day - prev).days != 1:
            flush()
            run = []
        run.append(d)
        prev = d.day
    flush()
    return blocks
