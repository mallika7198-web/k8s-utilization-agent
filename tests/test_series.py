from normalize.series import values_from_series, is_window_sufficient


def test_values_from_series_filters():
    s = [(1.0, '1'), (2.0, 2.0), (3.0, 'nan'), (4.0, None), (5.0, 5)]
    vals = values_from_series(s)
    assert vals == [1.0, 2.0, 5.0]


def test_is_window_sufficient():
    # timestamps spanning 600 seconds, 6 samples
    s = [(0.0, 1), (100.0, 1), (200.0, 1), (300.0, 1), (400.0, 1), (600.0, 1)]
    assert is_window_sufficient(s, min_samples=5, min_duration_seconds=500) is True
    assert is_window_sufficient(s, min_samples=10, min_duration_seconds=500) is False
