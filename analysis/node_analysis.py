from typing import Dict, Any, List
from metrics.prometheus_client import query_node_allocatable, query_range, PrometheusError
from normalize.series import values_from_series


def analyze_nodes() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "insufficient_data": False,
        "evidence": [],
        "node_capacity": {},
        "requested_vs_actual": {},
        "fragmentation_metrics": {},
        "bin_packing": {},
        "daemonset_overhead": {},
        "autoscaler_facts": {},
        "analysis_flags": {},
        "safety_classification": {},
    }

    try:
        alloc = query_node_allocatable()
    except PrometheusError:
        alloc = {}

    if not alloc:
        result["insufficient_data"] = True
        result["evidence"].append("no node allocatable metrics available from Prometheus")
        return result

    # Map nodes to capacities
    for node, caps in alloc.items():
        result["node_capacity"][node] = caps

    # Requested vs actual: requires kubelet metrics of requested resources; not available deterministically
    result["requested_vs_actual"]["total_requested_cpu"] = None
    result["requested_vs_actual"]["total_requested_memory"] = None
    result["requested_vs_actual"]["actual_avg_cpu"] = None
    result["requested_vs_actual"]["actual_avg_memory"] = None

    # Fragmentation and bin packing require pod scheduling details; mark insufficient
    result["fragmentation_metrics"]["largest_free_cpu_block"] = None
    result["fragmentation_metrics"]["largest_free_memory_block"] = None
    result["fragmentation_metrics"]["fragmentation_type"] = "None"

    result["bin_packing"]["pods_per_node"] = {}
    result["bin_packing"]["packing_efficiency_indicator"] = None

    result["daemonset_overhead"]["cpu"] = None
    result["daemonset_overhead"]["memory"] = None

    result["autoscaler_facts"]["scale_up_events"] = None
    result["autoscaler_facts"]["scale_down_blocked"] = None

    result["analysis_flags"]["bin_packing_efficiency"] = None
    result["safety_classification"]["risk_level"] = "Medium"
    result["safety_classification"]["confidence_level"] = "Low"

    return result
