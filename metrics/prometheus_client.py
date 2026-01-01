import time
from typing import List, Tuple, Dict, Any, Optional
import requests
from datetime import datetime, timezone

from config import PROMETHEUS_URL, PROMETHEUS_TIMEOUT_SECONDS, METRICS_WINDOW_MINUTES


class PrometheusError(Exception):
    pass


def _now() -> float:
    return time.time()


def _range_window_seconds(window_minutes: Optional[int] = None) -> int:
    if window_minutes is None:
        window_minutes = METRICS_WINDOW_MINUTES
    return int(window_minutes * 60)


def query_range(promql: str, start_ts: Optional[float] = None, end_ts: Optional[float] = None, step: str = "15s") -> Dict[str, Any]:
    """
    Query Prometheus `/api/v1/query_range` and return parsed JSON result.
    Returns the raw JSON payload as a dict. Caller is responsible for deterministic parsing.
    """
    if end_ts is None:
        end_ts = _now()
    if start_ts is None:
        start_ts = end_ts - _range_window_seconds()

    params = {
        "query": promql,
        "start": str(start_ts),
        "end": str(end_ts),
        "step": step,
    }
    url = f"{PROMETHEUS_URL.rstrip('/')}/api/v1/query_range"
    try:
        r = requests.get(url, params=params, timeout=PROMETHEUS_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise PrometheusError(f"request failed: {e}")
    if r.status_code != 200:
        raise PrometheusError(f"prometheus returned status {r.status_code}: {r.text}")
    data = r.json()
    if data.get("status") != "success":
        raise PrometheusError(f"prometheus error: {data}")
    return data


def parse_matrix_values(matrix: Dict[str, Any]) -> List[Tuple[float, float]]:
    """
    Parse a Prometheus matrix result (single timeseries) into list of (timestamp, value).
    Expects `matrix` to be one element of `data['result'][i]['values']` structure as returned from query_range.
    """
    values = matrix.get("values") or []
    parsed: List[Tuple[float, float]] = []
    for ts_str, val_str in values:
        try:
            ts = float(ts_str)
            val = float(val_str)
        except Exception:
            continue
        parsed.append((ts, val))
    return parsed


def query_pod_cpu_usage(pod_regex: str, start_ts: Optional[float] = None, end_ts: Optional[float] = None, step: str = "15s") -> Dict[str, List[Tuple[float, float]]]:
    """
    Returns a dict mapping pod name -> list of (timestamp, cpu_cores) samples.
    PromQL used: `sum by (pod) (rate(container_cpu_usage_seconds_total{pod=~"<pod_regex>",container!=""}[5m]))`
    """
    promql = f'sum by (pod) (rate(container_cpu_usage_seconds_total{{pod=~"{pod_regex}",container!=""}}[5m]))'
    data = query_range(promql, start_ts=start_ts, end_ts=end_ts, step=step)
    results: Dict[str, List[Tuple[float, float]]] = {}
    for res in data.get("data", {}).get("result", []):
        pod = res.get("metric", {}).get("pod") or "<unknown>"
        results[pod] = parse_matrix_values(res)
    return results


def query_pod_memory_usage(pod_regex: str, start_ts: Optional[float] = None, end_ts: Optional[float] = None, step: str = "15s") -> Dict[str, List[Tuple[float, float]]]:
    """
    Returns a dict mapping pod name -> list of (timestamp, memory_bytes) samples.
    PromQL used: `sum by (pod) (container_memory_working_set_bytes{pod=~"<pod_regex>",container!=""})`
    """
    promql = f'sum by (pod) (container_memory_working_set_bytes{{pod=~"{pod_regex}",container!=""}})'
    data = query_range(promql, start_ts=start_ts, end_ts=end_ts, step=step)
    results: Dict[str, List[Tuple[float, float]]] = {}
    for res in data.get("data", {}).get("result", []):
        pod = res.get("metric", {}).get("pod") or "<unknown>"
        results[pod] = parse_matrix_values(res)
    return results


def query_node_allocatable() -> Dict[str, Dict[str, float]]:
    """
    Query node allocatable CPU and memory.
    Returns mapping node -> {"cpu_cores": float, "memory_bytes": float}
    Uses `node_namespace_pod:allocatable` or `kube_node_status_allocatable` depending on Prometheus setup; attempt common metric names.
    This function attempts both common metric names deterministically and returns what it finds.
    """
    # Try kube_node_status_allocatable first
    try:
        data = query_range('kube_node_status_allocatable_cpu_cores', start_ts=_now() - 60, end_ts=_now(), step='60s')
        results = {}
        for res in data.get('data', {}).get('result', []):
            node = res.get('metric', {}).get('node') or '<unknown>'
            vals = parse_matrix_values(res)
            if vals:
                # take the latest value
                results.setdefault(node, {})['cpu_cores'] = vals[-1][1]
        # memory
        data_mem = query_range('kube_node_status_allocatable_memory_bytes', start_ts=_now() - 60, end_ts=_now(), step='60s')
        for res in data_mem.get('data', {}).get('result', []):
            node = res.get('metric', {}).get('node') or '<unknown>'
            vals = parse_matrix_values(res)
            if vals:
                results.setdefault(node, {})['memory_bytes'] = vals[-1][1]
        return results
    except PrometheusError:
        # Return empty if not available
        return {}
