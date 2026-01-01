"""Orchestrator: run discovery -> analysis -> aggregate -> atomic write.
Copilot: Phase-1 Analysis only. No LLM. No suggestions. Deterministic facts and flags only. Prometheus is the source of truth. All configuration from config.py. Update tracker.json for every change.
"""
from datetime import datetime, timezone
import json
import os
import tempfile
from typing import List, Dict, Any

from config import ANALYSIS_OUTPUT_PATH
from metrics import discovery as discovery_mod
from metrics import prometheus_client as prom
from analysis import deployment_analysis as dep_analysis
from analysis import hpa_analysis as hpa_analysis_mod
from analysis import node_analysis as node_analysis_mod
from tracker import append_change


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, data: str) -> None:
    dirp = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.tmp_analysis_', dir=dirp)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(data)
        # Atomic replace
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


# use tracker.append_change for append-only updates (best-effort)


def run_once() -> Dict[str, Any]:
    # 1) Check Prometheus connectivity first
    prometheus_available = False
    try:
        prom.query_range('up')
        prometheus_available = True
    except prom.PrometheusError as e:
        print(f"⚠️  PROMETHEUS NOT REACHABLE: {e}")
        print(f"   Expected URL: {prom.PROMETHEUS_URL}")
        print(f"   Proceeding with empty metrics...")
    except Exception as e:
        print(f"⚠️  PROMETHEUS CONNECTION ERROR: {e}")
        print(f"   Proceeding with empty metrics...")

    # 2) Discovery
    deps = discovery_mod.discover_deployments()
    hpas = discovery_mod.discover_hpas()
    nodes = discovery_mod.discover_nodes()

    discovery_filters = {
        'deployments': deps.get('discovery_filters'),
        'hpas': {},
        'nodes': {},
    }

    # 3) Analyze deployments
    deployment_results: List[Dict[str, Any]] = dep_analysis.analyze_deployments(
        deps.get('deployments', [])
    )

    # 4) HPA analysis
    hpa_results: List[Dict[str, Any]] = hpa_analysis_mod.analyze_hpas(
        hpas.get('hpas', [])
    )

    # 5) Node analysis
    node_result = node_analysis_mod.analyze_nodes(
        nodes.get('nodes', [])
    )

    # 5) Aggregate
    output: Dict[str, Any] = {
        'generated_at': _now_iso(),
        'cluster_summary': {
            'deployment_count': len(deployment_results),
            'hpa_count': len(hpa_results),
            'node_count': len(nodes.get('nodes', [])),
        },
        'analysis_scope': discovery_filters,
        'deployment_analysis': deployment_results,
        'hpa_analysis': hpa_results,
        'node_analysis': node_result,
        'cross_layer_observations': [],
    }

    return output


def main() -> int:
    print("🔄 Starting Kubernetes Utilization Analysis...")
    out = run_once()
    # Write atomically
    try:
        _atomic_write(ANALYSIS_OUTPUT_PATH, json.dumps(out, indent=2))
    except Exception as e:
        print("❌ Failed to write analysis output:", e)
        return 2

    # Update tracker.json best-effort using append-only utility
    try:
        append_change({
            'files_modified': [ANALYSIS_OUTPUT_PATH, 'orchestrator.py', '.tracker.json'],
            'type': 'analysis',
            'description': 'Orchestrator run: produced canonical analysis output'
        }, tracker_path=os.path.join(os.path.dirname(__file__), '.tracker.json'))
    except Exception:
        pass

    print(f"✅ Wrote analysis to {ANALYSIS_OUTPUT_PATH}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
