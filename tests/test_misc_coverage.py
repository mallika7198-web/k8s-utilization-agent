import json
import os
import tempfile
import requests
from types import SimpleNamespace

import metrics.prometheus_client as pc
import tracker as tr
import analysis.hpa_analysis as ha
import analysis.deployment_analysis as da
import orchestrator


def test_query_range_prometheus_error(monkeypatch):
    class FakeResp:
        status_code = 500
        text = 'err'
        def json(self):
            return {'status': 'error'}

    def fake_get(*a, **k):
        return FakeResp()

    monkeypatch.setattr(requests, 'get', fake_get)
    try:
        pc.query_range('up')
    except pc.PrometheusError:
        pass
    else:
        raise AssertionError('Expected PrometheusError')


def test_hpa_utilization_flag():
    cfg = {'min_replicas': 1, 'max_replicas': 2, 'metric_type': 'cpu', 'target_utilization': 50}
    metrics = {'replicas_timeseries': [1,1,1], 'deployment_cpu_request': 10.0, 'deployment_cpu_p95': 2.0}
    res = ha.analyze_hpa(cfg, metrics)
    assert res['analysis_flags']['utilization_misleading_due_to_inflated_requests'] is True


def test_deployment_insufficient_no_series():
    res = da.analyze_deployment({}, {}, {'name': 'x'})
    assert res['insufficient_data'] is True


def test_orchestrator_main_writes(tmp_path, monkeypatch):
    p = tmp_path / 'out.json'
    monkeypatch.setattr(orchestrator, 'ANALYSIS_OUTPUT_PATH', str(p))
    monkeypatch.setattr(orchestrator, 'append_change', lambda *a, **k: True)
    rc = orchestrator.main()
    assert rc == 0
    assert p.exists()
    data = json.loads(p.read_text())
    assert 'generated_at' in data


def test_tracker_atomic_failure(monkeypatch, tmp_path):
    p = tmp_path / 't.json'
    # simulate atomic write failure
    monkeypatch.setattr(tr, '_atomic_write', lambda *a, **k: (_ for _ in ()).throw(Exception('fail')))
    ok = tr.append_change({'files_modified': ['a'], 'type': 'x'}, tracker_path=str(p))
    assert ok is False
