from typing import List, Tuple, Dict
from datetime import datetime


def values_from_series(series: List[Tuple[float, float]]) -> List[float]:
    """Extract numeric values from a list of (timestamp, value) tuples.
    Drops NaNs and non-finite values.
    """
    vals: List[float] = []
    for ts, v in series:
        if v is None:
            continue
        try:
            fv = float(v)
        except Exception:
            continue
        if fv != fv:  # NaN
            continue
        vals.append(fv)
    return vals


def is_window_sufficient(series: List[Tuple[float, float]], min_samples: int, min_duration_seconds: int) -> bool:
    """Check that series spans at least `min_duration_seconds` and has at least `min_samples` samples."""
    if not series:
        return False
    if len(series) < min_samples:
        return False
    timestamps = [ts for ts, _ in series]
    duration = max(timestamps) - min(timestamps)
    return duration >= min_duration_seconds
