from typing import Dict, Any


def analyze_hpa(hpa_config: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal HPA analysis for Phase 1.
    If `hpa_config` is None or empty, return disabled HPA analysis.
    This module does not query k8s objects; it expects the caller to provide HPA config and metrics.
    """
    result: Dict[str, Any] = {
        "hpa_enabled": False,
        "insufficient_data": False,
        "evidence": [],
        "hpa_config_facts": {},
        "scaling_behavior": {},
        "linked_resource_facts": {},
        "analysis_flags": {},
        "safety_classification": {},
    }

    if not hpa_config:
        result["hpa_enabled"] = False
        result["insufficient_data"] = True
        result["evidence"].append("no HPA config provided")
        return result

    result["hpa_enabled"] = True
    result["hpa_config_facts"]["metric_type"] = hpa_config.get("metric_type")
    result["hpa_config_facts"]["target_utilization"] = hpa_config.get("target_utilization")
    result["hpa_config_facts"]["min_replicas"] = hpa_config.get("min_replicas")
    result["hpa_config_facts"]["max_replicas"] = hpa_config.get("max_replicas")

    # Scaling behavior: requires timeseries of replicas over time; if absent, mark insufficient
    replicas_ts = metrics.get("replicas_timeseries")
    if not replicas_ts:
        result["insufficient_data"] = True
        result["evidence"].append("no replicas timeseries provided for scaling behavior analysis")
        return result

    # Deterministic simple analyses: percent time at min/max
    total = len(replicas_ts)
    if total == 0:
        result["insufficient_data"] = True
        result["evidence"].append("replicas timeseries empty")
        return result
    min_r = hpa_config.get("min_replicas")
    max_r = hpa_config.get("max_replicas")
    at_min = sum(1 for v in replicas_ts if v == min_r)
    at_max = sum(1 for v in replicas_ts if v == max_r)
    result["scaling_behavior"]["scale_up_events_24h"] = metrics.get("scale_up_events_24h", 0)
    result["scaling_behavior"]["scale_down_events_24h"] = metrics.get("scale_down_events_24h", 0)
    result["scaling_behavior"]["percent_time_at_min_replicas"] = (at_min / total) * 100.0
    result["scaling_behavior"]["percent_time_at_max_replicas"] = (at_max / total) * 100.0

    # Linked resource facts: expect cpu_request and cpu_p95
    result["linked_resource_facts"]["deployment_cpu_request"] = metrics.get("deployment_cpu_request")
    result["linked_resource_facts"]["deployment_cpu_p95"] = metrics.get("deployment_cpu_p95")
    result["linked_resource_facts"]["average_replica_utilization"] = metrics.get("average_replica_utilization")

    # Analysis flags: simple deterministic checks
    result["analysis_flags"]["scaling_signal_validity"] = not result["insufficient_data"]
    result["analysis_flags"]["utilization_misleading_due_to_inflated_requests"] = False
    if result["linked_resource_facts"]["deployment_cpu_request"] and result["linked_resource_facts"]["deployment_cpu_p95"]:
        if result["linked_resource_facts"]["deployment_cpu_request"] > result["linked_resource_facts"]["deployment_cpu_p95"] * 3:
            result["analysis_flags"]["utilization_misleading_due_to_inflated_requests"] = True

    result["safety_classification"] = {
        "risk_level": "Medium" if result["insufficient_data"] else "Low",
        "confidence_level": "Low" if result["insufficient_data"] else "High",
    }

    return result
