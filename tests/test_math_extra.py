import pytest
from normalize import math as m


def test_percentile_errors():
    with pytest.raises(ValueError):
        m.percentile([], 50)
    with pytest.raises(ValueError):
        m.percentile([1, 2, 3], -1)


def test_nearest_rank_and_spike_infinite():
    # p95 nearest is zero, p100 non-zero -> spike_ratio infinity
    # Construct a list where 95% of items are zero and the max is non-zero
    s = [0]*19 + [10]
    assert m.spike_ratio(s) == float('inf')
    assert m._nearest_rank_percentile([1,2,3,4], 50) == 2.0


def test_is_bursty_various():
    assert m.is_bursty([1,1,1,1,1], 2.0) is False
    assert m.is_bursty([1,1,1,10000], 2.0) is True
