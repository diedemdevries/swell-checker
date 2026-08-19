#!/usr/bin/env python3
"""Surf check — draait elke paar uur, meldt alleen als het de moeite is.

  python main.py                 normale run
  python main.py --dry-run       alles doen, niets versturen
  python main.py --verbose       laat per spot zien waarom het afvalt
  python main.py --demo          verzonnen swell, om het bericht te zien
"""

import argparse
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

import booking, flights, forecast, notify
from scoring import find_blocks, score_day, score_hour
from state import State

ROOT = Path(__file__).parent


def load_config(path: Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def tier_for(start: date, today: date, cfg: dict):
    """Vroege waarschuwing, bevestiging, of nog te ver weg."""
    days_out = (start - today).days
    lo, hi = cfg["trip"]["confirm_days"]
    if lo <= days_out <= hi:
        return "confirm"
    lo, hi = cfg["trip"]["early_warning_days"]
    if lo <= days_out <= hi:
        return "early"
    return None


def in_season(spot: dict, today: date) -> bool:
    season = spot.get("season")
    return not season or today.month in season


def scan(cfg: dict, today: date, verbose: bool = False, fetch=None):
    """Alle spots langs, alle blokken terug die aan de eisen voldoen."""
    criteria = cfg["criteria"]
    horizon = min(max(cfg["trip"]["early_warning_days"]) + 1, 7)
    all_blocks = []

    active, skipped = [], []
    for spot in cfg["spots"]:
        (active if in_season(spot, today) else skipped).append(spot)
    if verbose:
        for spot in skipped:
            print(f"  {spot['name']:<28} buiten seizoen")

    # Eén gebundelde call voor alles; fetch= is er voor de tests.
    if fetch is None:
        bulk = forecast.fetch_many(active, days=horizon)
    else:
        bulk = {}
        for spot in active:
            try:
                bulk[spot["name"]] = fetch(spot, days=horizon)
            except Exception as exc:  # noqa: BLE001
                print(f"  {spot['name']:<28} forecast mislukt: {exc}")
                bulk[spot["name"]] = []

    for spot in active:
        rows = bulk.get(spot["name"]) or []
        if not rows:
            if verbose:
                print(f"  {spot['name']:<28} geen data")
            continue

        by_day = forecast.group_by_day(rows)
        days = []
        for d in sorted(by_day):
            hours = [score_hour(r, spot, criteria) for r in by_day[d]]
            days.append(score_day(d, hours, criteria))

        min_days = cfg["tiers"][spot["tier"]]["min_days"]
        blocks = find_blocks(spot, days, min_days)
        all_blocks.extend(blocks)

        if verbose:
            good = sum(1 for d in days if d.qualifies)
            note = f"{len(blocks)} blok(ken)" if blocks else (
                days[0].fail if days and days[0].fail else "niets")
            print(f"  {spot['name']:<28} {good}/{len(days)} goede dagen · {note}")

    return all_blocks


def build_trip(block, cfg: dict, today: date):
    """Vertaal een swell-blok naar vlucht, auto en bed.

    De vlucht wordt niet op vaste datums gezocht maar over een venster
    rond het blok -- Ryanair zoekt daarbinnen zelf de goedkoopste
    combinatie, en dat scheelt vaak flink.
    """
    t = cfg["trip"]
    out_from = max(block.start - timedelta(days=t["flex_days_before"]), today)
    out_to = block.start                          # uiterlijk op dag 1 aankomen
    if out_to < out_from:
        out_to = out_from
    back_from = block.end                         # niet eerder dan de laatste dag
    back_to = block.end + timedelta(days=t["flex_days_after"])
    if back_to > out_from + timedelta(days=t["max_trip_nights"]):
        back_to = out_from + timedelta(days=t["max_trip_nights"])
    if back_to < back_from:
        back_to = back_from

    airport = block.spot["airport"]
    city = cfg["airport_city"].get(airport, airport)
    people = t["people"]

    f = flights.cheapest(cfg["origins"], airport, out_from, out_to,
                         back_from, back_to, cfg["links"]["flight"], people)

    # Auto en bed volgen de datums die de vlucht daadwerkelijk opleverde.
    out_d = date.fromisoformat(f.out_date)
    back_d = date.fromisoformat(f.back_date)
    c = booking.car_for(airport, city, out_d, back_d,
                        cfg["car_eur_day"], cfg["links"]["car"])
    s = booking.stay_for(city, out_d, back_d,
                         t["max_hostel_eur_night"], people,
                         cfg["links"]["stay"])
    return f, c, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=str(ROOT / "state.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--demo", action="store_true",
                    help="verzonnen swell, om het bericht te bekijken")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    today = date.today()
    tg = notify.Telegram(dry_run=args.dry_run)
    state = State(Path(args.state))

    print(f"Surf check · {datetime.now():%Y-%m-%d %H:%M} · {len(cfg['spots'])} spots")

    if args.demo:
        from fixtures import demo_block
        blocks = [demo_block(cfg)]
    else:
        blocks = scan(cfg, today, verbose=args.verbose)

    if not blocks:
        print("Geen blok haalt de eisen. Stil blijven.")
        return 0

    # Alleen blokken binnen een alarmvenster, beste eerst.
    candidates = []
    for b in blocks:
        t = "confirm" if args.demo else tier_for(b.start, today, cfg)
        if t:
            candidates.append((b, t))
    candidates.sort(key=lambda bt: bt[0].rank_score, reverse=True)

    if not candidates:
        print(f"{len(blocks)} blok(ken) gevonden, maar geen binnen een alarmvenster.")
        return 0

    print(f"{len(candidates)} kandidaat(en). Beste: "
          f"{candidates[0][0].spot['name']} score {candidates[0][0].score:.0f}")

    sent = 0
    for block, tier in candidates:
        reason = "new" if args.demo else state.should_announce(block.key(), tier, block.score)
        if not reason:
            print(f"  {block.spot['name']} — al gemeld, overslaan")
            continue

        try:
            f, c, s = build_trip(block, cfg, today)
        except Exception as exc:  # noqa: BLE001
            print(f"  {block.spot['name']} — trip bouwen mislukt: {exc}")
            traceback.print_exc()
            continue

        runner = next((b for b, _ in candidates
                       if b.spot["name"] != block.spot["name"]), None)
        msg = notify.build_message(block, f, c, s, reason, tier,
                                   cfg["trip"]["people"], runner,
                                   cfg["trip"]["flight_reference_eur"])
        if tg.send(msg):
            tg.poll(f"{block.spot['name']} — {block.n_days} dagen. Gaan we?",
                    ["Ik ben in 🤙", "Kan niet 😔"])
            state.record(block.key(), tier, block.score)
            sent += 1
        break   # één voorstel per run, geen spam

    if sent == 0:
        print("Niets nieuws te melden.")

    state.prune(today)
    # Een demo-run is nep: die mag niet in het geheugen belanden, anders
    # onderdrukt hij later een echte swell op diezelfde datum.
    if not args.dry_run and not args.demo:
        state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
