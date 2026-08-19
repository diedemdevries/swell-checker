"""Hoekjes-rekenwerk voor kustorientatie en windrichting.

Alle richtingen zijn in graden, en volgen de meteorologische conventie:
een windrichting van 90 graden betekent wind DIE UIT het oosten KOMT.
"""


def norm(deg: float) -> float:
    """Breng een hoek terug naar het bereik [0, 360)."""
    return deg % 360.0


def ang_diff(a: float, b: float) -> float:
    """Kortste hoekafstand tussen twee richtingen, altijd 0..180."""
    d = abs(norm(a) - norm(b)) % 360.0
    return 360.0 - d if d > 180.0 else d


def in_window(direction: float, window) -> bool:
    """Valt een richting binnen een venster? Werkt ook over 0 graden heen.

    in_window(350, [300, 30]) -> True
    """
    lo, hi = norm(window[0]), norm(window[1])
    d = norm(direction)
    if lo <= hi:
        return lo <= d <= hi
    return d >= lo or d <= hi


def window_center(window):
    """Middelpunt van een venster, ook als het over 0 graden heen loopt."""
    lo, hi = norm(window[0]), norm(window[1])
    span = (hi - lo) % 360.0
    return norm(lo + span / 2.0)


def window_span(window) -> float:
    lo, hi = norm(window[0]), norm(window[1])
    return (hi - lo) % 360.0 or 360.0


def offshore_direction(faces: float) -> float:
    """Waar de wind vandaan moet komen om offshore te zijn.

    Een strand dat op het westen (270) kijkt heeft offshore wind uit het
    oosten (90).
    """
    return norm(faces + 180.0)


def is_offshore(wind_from: float, faces: float, tolerance: float = 50.0) -> bool:
    return ang_diff(wind_from, offshore_direction(faces)) <= tolerance
