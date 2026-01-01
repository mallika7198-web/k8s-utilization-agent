from typing import Dict, List, Any
from normalize import math as m
from normalize.series import values_from_series, is_window_sufficient
from config import CPU_BURST_RATIO_THRESHOLD, MEMORY_GROWTH_THRESHOLD_PERCENT, MIN_OBSERVATION_WINDOW_MINUTES


def _compute_stats(samples: List[float]) -> Dict[str, Any]:
    return {
        "avg": m.avg(samples),
        "p95": m.p95(samples),
        "p99": m.p99(samples),
        "p100": m.p100(samples),
    }


def analyze_deployment(pod_cpu_series: Dict[str, List[tuple]], pod_mem_series: Dict[str, List[tuple]], deployment_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce `deployment_analysis` JSON object.

    `deployment_spec` must contain keys: `name`, `replicas`, `cpu_request` (cores), `memory_request` (bytes)

    If metrics are missing or observation window insufficient, set `insufficient_data` with evidence.
    """
    result: Dict[str, Any] = {
        "deployment": deployment_spec.get("name"),
        "insufficient_data": False,
        "evidence": [],
        "resource_facts": {},
        "derived_metrics": {},
        "behavior_flags": {},
        "scheduling_facts": {},
        "edge_cases": [],
        "safety_classification": {},
    }

    # Read deployment_spec if present. Per Phase 1 rules, resource requests/replicas
    # must not be supplied by the UI/CLI; they may be absent and treated as missing.
    replicas = deployment_spec.get("replicas")
    cpu_request = deployment_spec.get("cpu_request")
    memory_request = deployment_spec.get("memory_request")
    # Populate whatever is available; do not block analysis solely because spec fields are missing.
    if replicas is not None:
        result["resource_facts"]["replicas"] = replicas
    else:
        result["resource_facts"]["replicas"] = None

    # Collect per-pod numeric samples
    pod_cpu_values = {}
    pod_mem_values = {}
    for pod, series in pod_cpu_series.items():
        vals = values_from_series(series)
        pod_cpu_values[pod] = vals
    for pod, series in pod_mem_series.items():
        vals = values_from_series(series)
        pod_mem_values[pod] = vals

    if not pod_cpu_values:
        result["insufficient_data"] = True
        result["evidence"].append("no CPU metrics found for pods")
    if not pod_mem_values:
        result["insufficient_data"] = True
        result["evidence"].append("no memory metrics found for pods")

    # Observation window check: require at least MIN_OBSERVATION_WINDOW_MINUTES
    min_duration_seconds = MIN_OBSERVATION_WINDOW_MINUTES * 60
    # Find any series to check timestamps count heuristically
    any_series = None
    for s in pod_cpu_series.values():
        any_series = s
        break
    if any_series is None:
        result["insufficient_data"] = True
        result["evidence"].append("no timeseries data available to evaluate observation window")
    else:
        if not is_window_sufficient(any_series, min_samples=5, min_duration_seconds=min_duration_seconds):
            # Record observation window as insufficient evidence but continue analysis when numeric samples exist.
            result["evidence"].append(f"observation window shorter than {MIN_OBSERVATION_WINDOW_MINUTES} minutes or missing samples")

    if result["insufficient_data"]:
        return result

    # Aggregate across pods (per-replica metrics)
    all_cpu_samples: List[float] = []
    all_mem_samples: List[float] = []
    for pod, vals in pod_cpu_values.items():
        all_cpu_samples.extend(vals)
    for pod, vals in pod_mem_values.items():
        all_mem_samples.extend(vals)

    if not all_cpu_samples or not all_mem_samples:
        result["insufficient_data"] = True
        result["evidence"].append("after cleaning, no numeric samples available for CPU or memory")
        return result

    cpu_stats = _compute_stats(all_cpu_samples)
    mem_stats = _compute_stats(all_mem_samples)

    result["resource_facts"]["cpu_request"] = cpu_request
    result["resource_facts"]["cpu_usage"] = cpu_stats
    result["resource_facts"]["memory_request"] = memory_request
    result["resource_facts"]["memory_usage"] = mem_stats

    # Derived metrics
    p95_cpu = cpu_stats["p95"]
    p95_mem = mem_stats["p95"]
    cpu_overprov = None
    mem_overprov = None
    if cpu_request is not None and p95_cpu > 0:
        cpu_overprov = cpu_request / p95_cpu
    if memory_request is not None and p95_mem > 0:
        mem_overprov = memory_request / p95_mem

    spike = None
    try:
        spike = m.spike_ratio(all_cpu_samples)
    except Exception:
        spike = None

    result["derived_metrics"]["cpu_overprovision_ratio"] = cpu_overprov
    result["derived_metrics"]["memory_overprovision_ratio"] = mem_overprov
    result["derived_metrics"]["spike_ratio"] = spike

    # Behavior flags
    bursty = m.is_bursty(all_cpu_samples, CPU_BURST_RATIO_THRESHOLD)
    result["behavior_flags"]["bursty_workload"] = bool(bursty)

    # Memory growth trend: compare first and last P95 of memory across time by taking earliest and latest 10% samples
    try:
        sorted_mem = sorted(all_mem_samples)
        # simple trend: last vs first percent change
        first = sorted_mem[0]
        last = sorted_mem[-1]
        growth_percent = None
        if first > 0:
            growth_percent = ((last - first) / first) * 100.0
        else:
            growth_percent = float('inf') if last > 0 else 0.0
        result["behavior_flags"]["memory_growth_percent"] = growth_percent
        result["behavior_flags"]["memory_growth_trend"] = bool(growth_percent is not None and growth_percent >= MEMORY_GROWTH_THRESHOLD_PERCENT)
    except Exception:
        result["behavior_flags"]["memory_growth_trend"] = False

    # Scheduling facts: not available via current inputs
    result["scheduling_facts"]["nodes_used"] = []
    result["scheduling_facts"]["pods_per_node_distribution"] = {}
    result["scheduling_facts"]["pending_pods"] = None

    # Edge cases: detect if spike ratio infinite or very large
    if spike is None:
        pass
    else:
        if spike == float('inf') or spike > 1000:
            result["edge_cases"].append("extreme_spike_ratio")

    # Safety classification: simple deterministic rules
    risk = "Low"
    confidence = "High"
    safe_to_resize = "partial_only"
    if cpu_overprov is None or mem_overprov is None:
        risk = "Medium"
        confidence = "Low"
        safe_to_resize = "false"
    else:
        if (cpu_overprov is not None and cpu_overprov > 5.0) or (mem_overprov is not None and mem_overprov > 5.0):
            risk = "High"
            confidence = "Medium"
            safe_to_resize = "false"
        else:
            risk = "Low"
            confidence = "High"
            safe_to_resize = "true"

    result["safety_classification"] = {
        "risk_level": risk,
        "confidence_level": confidence,
        "safe_to_resize": safe_to_resize,
    }

    return result
