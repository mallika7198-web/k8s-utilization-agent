import json
import os

import orchestrator


def test_run_once_structure(monkeypatch):
    # Mock discovery to return one deployment
    monkeypatch.setattr(orchestrator.discovery_mod, 'discover_deployments', lambda *a, **k: {
        'deployments': [{'name': 'myapp', 'namespace': 'default', 'replicas': 1}],
        'discovery_filters': {}
    })
    monkeypatch.setattr(orchestrator.discovery_mod, 'discover_hpas', lambda *a, **k: {'hpas': []})
    monkeypatch.setattr(orchestrator.discovery_mod, 'discover_nodes', lambda *a, **k: {'nodes': []})

    # Provide deterministic CPU/memory samples for a single pod
    sample_series = {
        'myapp-abcde-12345': [
            (1.0, 0.1),
            (2.0, 0.2),
            (3.0, 0.15),
            (4.0, 0.12),
            (5.0, 0.11),
        ]
    }
    monkeypatch.setattr(orchestrator.prom, 'query_pod_cpu_usage', lambda *a, **k: sample_series)
    monkeypatch.setattr(orchestrator.prom, 'query_pod_memory_usage', lambda *a, **k: sample_series)

    out = orchestrator.run_once()

    assert 'generated_at' in out
    assert 'cluster_summary' in out
    assert out['cluster_summary']['deployment_count'] == 1
    assert isinstance(out['deployment_analysis'], list)
    assert len(out['deployment_analysis']) == 1
    da = out['deployment_analysis'][0]
    assert da['deployment'] == 'myapp'
    assert 'resource_facts' in da


def test_run_once_handles_missing_metrics(monkeypatch):
    # Discovery returns one deployment but Prometheus returns no metrics
    monkeypatch.setattr(orchestrator.discovery_mod, 'discover_deployments', lambda *a, **k: {
        'deployments': [{'name': 'silent', 'namespace': 'default', 'replicas': None}],
        'discovery_filters': {}
    })
    monkeypatch.setattr(orchestrator.discovery_mod, 'discover_hpas', lambda *a, **k: {'hpas': []})
    monkeypatch.setattr(orchestrator.discovery_mod, 'discover_nodes', lambda *a, **k: {'nodes': []})

    monkeypatch.setattr(orchestrator.prom, 'query_pod_cpu_usage', lambda *a, **k: {})
    monkeypatch.setattr(orchestrator.prom, 'query_pod_memory_usage', lambda *a, **k: {})

    out = orchestrator.run_once()
    assert len(out['deployment_analysis']) == 1
    da = out['deployment_analysis'][0]
    assert da['insufficient_data'] is True
