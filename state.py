"""Onthouden wat we al gemeld hebben.

Een swell wordt onthouden per regio en per periode, niet per spot. Anders
krijg je bij een swell in de Landes vijf berichten achter elkaar: eerst
La Graviere, dan La Piste, dan Les Bourdaines... Ook een forecast die een
dag opschuift telt als dezelfde swell.

Het bestand wordt door de GitHub Action teruggecommit naar de repo, dus
het overleeft tussen runs.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

KEEP_DAYS = 45
SCORE_BUMP = 12.0     # zoveel moet een swell verbeteren voor een herhaalbericht
SAME_SWELL_DAYS = 4   # periodes die zo dicht bij elkaar liggen zijn dezelfde swell


def _parse(key: str, spot_region: Dict[str, str]):
    """Sleutel -> (regio, start, eind). Snapt ook het oude formaat spot|datum."""
    parts = key.split("|")
    try:
        if len(parts) == 3:
            return parts[0], date.fromisoformat(parts[1]), date.fromisoformat(parts[2])
        if len(parts) == 2:
            d = date.fromisoformat(parts[1])
            return spot_region.get(parts[0], parts[0]), d, d
    except ValueError:
        pass
    return None


def make_key(region: str, start: date, end: date) -> str:
    return f"{region}|{start.isoformat()}|{end.isoformat()}"


class State:
    def __init__(self, path: Path, spot_region: Optional[Dict[str, str]] = None):
        self.path = Path(path)
        self.spot_region = spot_region or {}
        self.data = {"announced": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
                self.data.setdefault("announced", {})
            except (json.JSONDecodeError, OSError):
                pass  # corrupt bestand: begin schoon, liever dubbel dan stil

    def _same_swell(self, region: str, start: date, end: date) -> List[dict]:
        hits = []
        gap = timedelta(days=SAME_SWELL_DAYS)
        for key, val in self.data["announced"].items():
            p = _parse(key, self.spot_region)
            if not p:
                continue
            r, s, e = p
            if r == region and s - gap <= end and e + gap >= start:
                hits.append(val)
        return hits

    # ---- beslissen ------------------------------------------------
    def should_announce(self, region: str, start: date, end: date,
                        tier: str, score: float) -> Optional[str]:
        """Geeft de reden terug waarom we melden, of None om te zwijgen.

        - nieuwe swell in deze regio               -> "new"
        - eerder alleen vroeg gemeld, nu bevestigd -> "confirm"
        - zelfde swell maar flink beter geworden   -> "upgrade"
        """
        prev = self._same_swell(region, start, end)
        if not prev:
            return "new"
        if tier == "confirm" and all(p.get("tier") == "early" for p in prev):
            return "confirm"
        best = max(float(p.get("score", 0)) for p in prev)
        if score - best >= SCORE_BUMP:
            return "upgrade"
        return None

    def record(self, region: str, start: date, end: date, tier: str,
               score: float) -> None:
        self.data["announced"][make_key(region, start, end)] = {
            "tier": tier,
            "score": round(score, 1),
            "at": datetime.utcnow().isoformat(timespec="seconds"),
        }

    # ---- opruimen en opslaan --------------------------------------
    def prune(self, today: Optional[date] = None) -> None:
        today = today or date.today()
        cutoff = today - timedelta(days=KEEP_DAYS)
        keep = {}
        for key, val in self.data["announced"].items():
            try:
                last = date.fromisoformat(key.split("|")[-1])
            except ValueError:
                continue
            if last >= cutoff:
                keep[key] = val
        self.data["announced"] = keep

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
