"""Onthouden wat we al gemeld hebben.

Zonder dit krijg je elke zes uur hetzelfde bericht over dezelfde swell.
Het bestand wordt door de GitHub Action teruggecommit naar de repo, dus
het overleeft tussen runs.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

KEEP_DAYS = 45
SCORE_BUMP = 12.0   # zoveel moet een swell verbeteren voor een herhaalbericht


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"announced": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
                self.data.setdefault("announced", {})
            except (json.JSONDecodeError, OSError):
                pass  # corrupt bestand: begin schoon, liever dubbel dan stil

    # ---- beslissen ------------------------------------------------
    def should_announce(self, key: str, tier: str, score: float) -> Optional[str]:
        """Geeft de reden terug waarom we melden, of None om te zwijgen.

        - nieuw blok                     -> "new"
        - eerder als vroege waarschuwing, nu bevestigd -> "confirm"
        - zelfde niveau maar flink beter -> "upgrade"
        """
        prev = self.data["announced"].get(key)
        if prev is None:
            return "new"
        if prev.get("tier") == "early" and tier == "confirm":
            return "confirm"
        if score - float(prev.get("score", 0)) >= SCORE_BUMP:
            return "upgrade"
        return None

    def record(self, key: str, tier: str, score: float) -> None:
        self.data["announced"][key] = {
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
                start = date.fromisoformat(key.split("|")[-1])
            except ValueError:
                continue
            if start >= cutoff:
                keep[key] = val
        self.data["announced"] = keep

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
