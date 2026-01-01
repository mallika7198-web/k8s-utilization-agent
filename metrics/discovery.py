from typing import List, Dict, Any, Optional
import re
from .prometheus_client import query_range, parse_matrix_values, _now
from config import EXCLUDED_NAMESPACES, METRICS_WINDOW_MINUTES


def _latest_value_from_result(res: Dict[str, Any]) -> Optional[float]:
    vals = parse_matrix_values(res)
    if not vals:
        return None
    return vals[-1][1]


def _namespace_allowed(ns: str, exclude_list: List[str]) -> bool:
    return ns not in exclude_list


def discover_deployments(namespace_allow: Optional[List[str]] = None,
                         namespace_deny: Optional[List[str]] = None,
                         deployment_regex: Optional[str] = None) -> Dict[str, Any]:
    """
    Discover deployments using Prometheus-exposed metrics only.

    Returns dict with keys:
      - deployments: list of {name, namespace, replicas}
      - discovery_filters: recorded filters applied

    This function attempts to use kube-state-metrics metrics when available
    (`kube_deployment_spec_replicas`, `kube_pod_info`). If those are absent,
    it falls back to heuristics based on pod names to infer deployment names.
    """
    exclude = [s.strip() for s in (EXCLUDED_NAMESPACES or "").split(',') if s.strip()]

    # 1) Query deployments replicas via kube_deployment_spec_replicas
    try:
        data = query_range('kube_deployment_spec_replicas', start_ts=_now() - 60, end_ts=_now(), step='60s')
        dep_map: Dict[str, Dict[str, Any]] = {}
        for res in data.get('data', {}).get('result', []):
            metric = res.get('metric', {})
            name = metric.get('deployment') or metric.get('deployment_name') or metric.get('name')
            ns = metric.get('namespace') or 'default'
            if not name:
                continue
            if namespace_allow and ns not in namespace_allow:
                continue
            if namespace_deny and ns in namespace_deny:
                continue
            if not _namespace_allowed(ns, exclude):
                continue
            if deployment_regex and not re.search(deployment_regex, name):
                continue
            latest = _latest_value_from_result(res)
            dep_map.setdefault(f"{ns}/{name}", {})['name'] = name
            dep_map[f"{ns}/{name}"]['namespace'] = ns
            dep_map[f"{ns}/{name}"]['replicas'] = int(latest) if latest is not None else None
        deployments = list(dep_map.values())
    except Exception:
        deployments = []

    # 2) If no deployments found via kube metrics, attempt to infer from pods
    if not deployments:
        try:
            data = query_range('kube_pod_info', start_ts=_now() - (METRICS_WINDOW_MINUTES * 60), end_ts=_now(), step='60s')
            pods = []
            for res in data.get('data', {}).get('result', []):
                metric = res.get('metric', {})
                pod = metric.get('pod') or metric.get('pod_name')
                ns = metric.get('namespace') or 'default'
                if not pod:
                    continue
                if namespace_allow and ns not in namespace_allow:
                    continue
                if namespace_deny and ns in namespace_deny:
                    continue
                if not _namespace_allowed(ns, exclude):
                    continue
                pods.append({'pod': pod, 'namespace': ns})

            # Heuristic: derive deployment by stripping typical pod suffixes
            dep_map = {}
            for p in pods:
                pod = p['pod']
                ns = p['namespace']
                m = re.match(r'^(?P<dep>.+)-[0-9a-f]{5,10}-[a-z0-9]{5,10}$', pod)
                if m:
                    name = m.group('dep')
                else:
                    # fallback: use pod as-is (best-effort)
                    name = pod
                if deployment_regex and not re.search(deployment_regex, name):
                    continue
                key = f"{ns}/{name}"
                dep_map.setdefault(key, {'name': name, 'namespace': ns, 'replicas': None})
            deployments = list(dep_map.values())
        except Exception:
            deployments = []

    discovery_filters = {
        'namespace_allow': namespace_allow,
        'namespace_deny': namespace_deny,
        'deployment_regex': deployment_regex,
        'excluded_namespaces': exclude,
    }

    return {'deployments': deployments, 'discovery_filters': discovery_filters}


def discover_nodes() -> Dict[str, Any]:
    """Discover nodes via Prometheus node metrics (allocatable/capacity)."""
    try:
        data_cpu = query_range('kube_node_status_allocatable_cpu_cores', start_ts=_now() - 60, end_ts=_now(), step='60s')
        data_mem = query_range('kube_node_status_allocatable_memory_bytes', start_ts=_now() - 60, end_ts=_now(), step='60s')
        nodes = {}
        for res in data_cpu.get('data', {}).get('result', []):
            node = res.get('metric', {}).get('node') or '<unknown>'
            val = _latest_value_from_result(res)
            nodes.setdefault(node, {})['cpu_cores'] = val
        for res in data_mem.get('data', {}).get('result', []):
            node = res.get('metric', {}).get('node') or '<unknown>'
            val = _latest_value_from_result(res)
            nodes.setdefault(node, {})['memory_bytes'] = val
        return {'nodes': [{'name': n, **nodes[n]} for n in nodes]}
    except Exception:
        return {'nodes': []}


def discover_hpas() -> Dict[str, Any]:
    """Discover HPAs via kube-state-metrics when available (kube_hpa_* metrics)."""
    try:
        data = query_range('kube_horizontalpodautoscaler_spec_min_replicas', start_ts=_now() - 60, end_ts=_now(), step='60s')
        hpas = []
        for res in data.get('data', {}).get('result', []):
            metric = res.get('metric', {})
            name = metric.get('hpa') or metric.get('horizontalpodautoscaler') or metric.get('name')
            ns = metric.get('namespace') or 'default'
            val = _latest_value_from_result(res)
            hpas.append({'name': name, 'namespace': ns, 'min_replicas': int(val) if val is not None else None})
        return {'hpas': hpas}
    except Exception:
        return {'hpas': []}
