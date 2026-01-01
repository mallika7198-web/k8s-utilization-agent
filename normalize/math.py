from typing import List


def avg(samples: List[float]) -> float:
    if not samples:
        raise ValueError("samples must not be empty")
    return sum(samples) / len(samples)


def percentile(samples: List[float], percent: float) -> float:
    if not samples:
        raise ValueError("samples must not be empty")
    if not (0 <= percent <= 100):
        raise ValueError("percent must be between 0 and 100")
    s = sorted(samples)
    n = len(s)
    if n == 1:
        return float(s[0])
    # rank using linear interpolation (0-based index)
    idx = (percent / 100.0) * (n - 1)
    lower = int(idx // 1)
    upper = int(idx // 1 + (0 if idx.is_integer() else 1))
    if upper >= n:
        return float(s[-1])
    if lower == upper:
        return float(s[lower])
    frac = idx - lower
    return float(s[lower] + frac * (s[upper] - s[lower]))


def _nearest_rank_percentile(samples: List[float], percent: float) -> float:
    """Nearest-rank percentile (1..n indexing). Useful for spike detection sensitivity."""
    if not samples:
        raise ValueError("samples must not be empty")
    s = sorted(samples)
    n = len(s)
    import math
    rank = int(math.ceil((percent / 100.0) * n)) - 1
    if rank < 0:
        rank = 0
    if rank >= n:
        rank = n - 1
    return float(s[rank])


def p95(samples: List[float]) -> float:
    return percentile(samples, 95.0)


def p99(samples: List[float]) -> float:
    return percentile(samples, 99.0)


def p100(samples: List[float]) -> float:
    return percentile(samples, 100.0)


def spike_ratio(samples: List[float]) -> float:
    # Use a nearest-rank P95 to increase sensitivity to isolated spikes
    p95v = _nearest_rank_percentile(samples, 95.0)
    p100v = p100(samples)
    if p95v == 0:
        if p100v == 0:
            return 1.0
        return float('inf')
    return p100v / p95v


def is_bursty(samples: List[float], threshold: float) -> bool:
    # Primary check: interpolated P95-based spike ratio
    try:
        p95_interp = p95(samples)
        p100v = p100(samples)
        if p95_interp != 0 and (p100v / p95_interp) >= threshold:
            return True
    except Exception:
        pass

    # Absolute-outlier check: if the maximum is orders of magnitude above central tendency
    try:
        med = percentile(samples, 50)
        if med > 0 and (p100(samples) / med) >= 500:
            return True
    except Exception:
        pass

    # Secondary check: nearest-rank sensitivity combined with a large-outlier test
    try:
        p95_nearest = _nearest_rank_percentile(samples, 95.0)
        p100v = p100(samples)
        if p95_nearest != 0 and (p100v / p95_nearest) >= threshold:
            # Require p100 to be substantially larger than central tendency to avoid small/moderate spikes
            med = percentile(samples, 50)
            # Require the max to be an extreme outlier relative to central tendency.
            # Use a high multiplier to avoid classifying moderate spikes as bursts.
            if med > 0 and (p100v / med) >= 500:
                return True
    except Exception:
        pass

    return False
