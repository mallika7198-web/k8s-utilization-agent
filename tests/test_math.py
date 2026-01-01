import os
import importlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalize import math as m


def test_percentiles_and_avg():
    samples = [1,2,3,4,5,6,7,8,9,100]
    assert round(m.avg(samples), 2) == 14.5
    assert round(m.percentile(samples, 95), 2) == 59.05
    assert round(m.percentile(samples, 99), 2) == 91.81
    assert m.p100(samples) == 100


def test_burst_detection_non_burst():
    s = [1]*9 + [100]
    assert m.is_bursty(s, 2.0) is False


def test_burst_detection_burst():
    s = [1]*9 + [1000]
    assert m.is_bursty(s, 2.0) is True


def test_config_override():
    os.environ["METRICS_WINDOW_MINUTES"] = "30"
    import config as cfg
    importlib.reload(cfg)
    assert cfg.METRICS_WINDOW_MINUTES == 30
