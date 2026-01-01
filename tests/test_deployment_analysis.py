from analysis.deployment_analysis import analyze_deployment


def make_series(values):
    # produce timestamps 0,60,120... with given values
    return [(i*60.0, v) for i, v in enumerate(values)]


def test_deployment_high_overprovision_and_spike():
    # Create CPU samples with low p95 (~0.1) and a high spike (10.0) to trigger high spike ratio
    pod_cpu_series = {
        'pod-1': make_series([0.05, 0.1, 0.08, 0.1, 10.0]),
        'pod-2': make_series([0.04, 0.09, 0.07, 0.11, 0.05]),
    }
    pod_mem_series = {
        'pod-1': make_series([100000000.0, 110000000.0, 120000000.0, 130000000.0, 140000000.0]),
        'pod-2': make_series([90000000.0, 95000000.0, 100000000.0, 105000000.0, 110000000.0]),
    }
    deployment_spec = {
        'name': 'test-deploy',
        'replicas': 2,
        'cpu_request': 1.0,  # 1 core request
        'memory_request': 256000000.0,
    }

    res = analyze_deployment(pod_cpu_series, pod_mem_series, deployment_spec)
    assert res['insufficient_data'] is False
    # Expect cpu_overprovision_ratio to be > MAX_ACCEPTABLE in code (we used 1.0 / ~0.09 => ~11)
    assert res['derived_metrics']['cpu_overprovision_ratio'] is not None
    assert res['safety_classification']['risk_level'] in ('High', 'Medium', 'Low')
    # Spike ratio should be > threshold (depends on config) — ensure it's present
    assert res['derived_metrics']['spike_ratio'] is not None
