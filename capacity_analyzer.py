#!/usr/bin/env python3
"""
Kubernetes Capacity Analysis Tool

Read-only, deterministic analysis for:
- Node CPU & memory fragmentation
- Pod CPU & memory request/limit recommendations
- Node sizing direction
- HPA misalignment detection
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Default Configuration (overridden by config.yaml)
# =============================================================================
DEFAULT_CONFIG = {
    "settings": {
        "query_window": "7d",
        "prometheus_timeout": 30,
        "prometheus_verify_tls": False,
    },
    "pod": {
        "cpu_floor_prod": 0.1,
        "cpu_floor_nonprod": 0.05,
        "safety_factor_prod": 1.15,
        "safety_factor_nonprod": 1.10,
        "cpu_request_multiplier": 1.20,
        "cpu_limit_request_multiplier": 1.50,
        "cpu_limit_p100_multiplier": 1.25,
        "memory_limit_request_multiplier": 1.50,
        "memory_limit_p100_multiplier": 1.25,
        "change_tolerance": 0.10,
    },
    "memory_buckets_mi": [256, 512, 1024, 2048, 4096, 8192],
    "memory_buffer_factor": 0.98,
    "thresholds": {
        "node": {
            "cpu_low_pct": 40,
            "cpu_high_pct": 75,
            "memory_low_pct": 50,
            "memory_high_pct": 75,
            "usable_capacity_factor": 0.80,
            "shape_imbalance_threshold": 0.25,
        },
        "hpa": {
            "cpu_low_util_pct": 40,
            "cpu_very_low_util_pct": 30,
            "memory_high_util_pct": 85,
        },
    },
    "limitations_text": "Analysis is advisory. Validate before applying.",
}

# Node recommendation statements (exact wording per spec)
NODE_STATEMENTS = {
    "consolidation": "Workloads can be consolidated onto fewer nodes after applying pod recommendations.",
    "shape_imbalance": "Current node shape appears unbalanced for observed CPU and memory usage.",
    "smaller_nodes": "Using more smaller nodes may improve packing efficiency.",
}

# HPA advisory statements
HPA_STATEMENTS = {
    "min_replicas": "Consider reducing the minimum replica count if sustained usage remains low.",
    "max_replicas": "Consider lowering the maximum replica count if peak scaling is rarely reached.",
    "cpu_based": "HPA may be scaling based on CPU requests that are higher than actual usage.",
    "memory_bound": "Workload appears memory-bound, but HPA is configured to scale on CPU.",
}


# =============================================================================
# Configuration Loading & Helpers
# =============================================================================
def load_config(config_path: str) -> Dict[str, Any]:
    """Load YAML configuration file and merge with defaults"""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def get_config_value(config: Dict[str, Any], *keys, default=None):
    """Safely get nested config value with default fallback"""
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def build_memory_buckets(config: Dict[str, Any]) -> List[int]:
    """Build memory bucket list from config with buffer factor"""
    buckets_mi = get_config_value(config, "memory_buckets_mi", default=DEFAULT_CONFIG["memory_buckets_mi"])
    buffer = get_config_value(config, "memory_buffer_factor", default=DEFAULT_CONFIG["memory_buffer_factor"])
    return [int(mi * 1024 * 1024 * buffer) for mi in buckets_mi]


def is_prod(env: str) -> bool:
    """Determine if environment is production"""
    return env.lower() == "prod"


def normalize_memory_to_bucket(memory_bytes: float, memory_buckets: List[int]) -> int:
    """
    Round memory up to the next standard bucket with buffer.
    
    Why: Standard shapes improve node packing efficiency.
    Buffer prevents tight scheduling that could cause OOM.
    """
    for bucket in memory_buckets:
        if memory_bytes <= bucket:
            return bucket
    # If larger than max bucket, return as-is (no normalization for huge pods)
    return int(memory_bytes)


# =============================================================================
# Prometheus Client
# =============================================================================
# Module-level defaults (used when no config passed)
PROMETHEUS_TIMEOUT = DEFAULT_CONFIG["settings"]["prometheus_timeout"]
PROMETHEUS_VERIFY_TLS = DEFAULT_CONFIG["settings"]["prometheus_verify_tls"]


def prometheus_query(prom_url: str, query: str, timeout: int = None, verify_tls: bool = None) -> List[Dict[str, Any]]:
    """Execute instant query against Prometheus"""
    timeout = timeout if timeout is not None else PROMETHEUS_TIMEOUT
    verify_tls = verify_tls if verify_tls is not None else PROMETHEUS_VERIFY_TLS
    
    try:
        response = requests.get(
            f"{prom_url}/api/v1/query",
            params={"query": query},
            timeout=timeout,
            verify=verify_tls
        )
        if response.status_code == 200:
            return response.json().get("data", {}).get("result", [])
        else:
            logger.warning(f"Query failed: {response.status_code} - {query[:80]}")
            return []
    except requests.RequestException as e:
        logger.warning(f"Prometheus request failed: {e}")
        return []


def extract_value(result: List[Dict], default: Optional[float] = None) -> Optional[float]:
    """Extract numeric value from Prometheus result"""
    if not result:
        return default
    try:
        val = result[0].get("value", [None, None])[1]
        return float(val) if val is not None else default
    except (ValueError, IndexError, TypeError):
        return default


def extract_metrics_by_labels(
    result: List[Dict], 
    label_keys: List[str]
) -> Dict[Tuple[str, ...], float]:
    """Extract metrics grouped by label values"""
    metrics = {}
    for item in result:
        labels = item.get("metric", {})
        key = tuple(labels.get(k, "") for k in label_keys)
        try:
            val = float(item.get("value", [None, None])[1])
            metrics[key] = val
        except (ValueError, TypeError):
            continue
    return metrics


# =============================================================================
# Prometheus Queries
# =============================================================================
# Default query window used when building PromQL queries
DEFAULT_QUERY_WINDOW = DEFAULT_CONFIG["settings"]["query_window"]


def build_promql_queries(query_window: str = None):
    """Build PromQL queries using configured query_window
    
    Note: quantile_over_time with subqueries doesn't support 'by' clause directly.
    We wrap with 'sum by' for proper label grouping.
    For CPU, we use rate() inside the subquery which requires a shorter step.
    """
    window = query_window or DEFAULT_QUERY_WINDOW
    return {
        # Pod Requests & Limits
        "POD_CPU_REQUESTS": 'sum by (namespace, pod)(kube_pod_container_resource_requests{resource="cpu"})',
        "POD_MEMORY_REQUESTS": 'sum by (namespace, pod)(kube_pod_container_resource_requests{resource="memory"})',
        "POD_CPU_LIMITS": 'sum by (namespace, pod)(kube_pod_container_resource_limits{resource="cpu"})',
        "POD_MEMORY_LIMITS": 'sum by (namespace, pod)(kube_pod_container_resource_limits{resource="memory"})',
        # Pod Usage - CPU Percentiles (from Prometheus)
        # Use sum by() wrapper since quantile_over_time doesn't support 'by' with subqueries
        "POD_CPU_P95": f'sum by (namespace, pod)(quantile_over_time(0.95, rate(container_cpu_usage_seconds_total{{container!=""}}[5m])[{window}:5m]))',
        "POD_CPU_P99": f'sum by (namespace, pod)(quantile_over_time(0.99, rate(container_cpu_usage_seconds_total{{container!=""}}[5m])[{window}:5m]))',
        "POD_CPU_P100": f'sum by (namespace, pod)(max_over_time(rate(container_cpu_usage_seconds_total{{container!=""}}[5m])[{window}:5m]))',
        # Pod Usage - Memory Percentiles (from Prometheus)
        "POD_MEMORY_P95": f'sum by (namespace, pod)(quantile_over_time(0.95, container_memory_working_set_bytes{{container!=""}}[{window}]))',
        "POD_MEMORY_P99": f'sum by (namespace, pod)(quantile_over_time(0.99, container_memory_working_set_bytes{{container!=""}}[{window}]))',
        "POD_MEMORY_P100": f'sum by (namespace, pod)(max_over_time(container_memory_working_set_bytes{{container!=""}}[{window}]))',
    }


class PrometheusQueries:
    """All Prometheus queries as per specification
    
    Note: Percentile queries are built dynamically using build_promql_queries()
    with the configured query_window.
    """
    
    # Pod Requests & Limits
    POD_CPU_REQUESTS = 'sum by (namespace, pod)(kube_pod_container_resource_requests{resource="cpu"})'
    POD_MEMORY_REQUESTS = 'sum by (namespace, pod)(kube_pod_container_resource_requests{resource="memory"})'
    POD_CPU_LIMITS = 'sum by (namespace, pod)(kube_pod_container_resource_limits{resource="cpu"})'
    POD_MEMORY_LIMITS = 'sum by (namespace, pod)(kube_pod_container_resource_limits{resource="memory"})'
    
    # Pod to Node mapping - CRITICAL for node-scoped calculations
    # Maps (namespace, pod) -> node for accurate per-node aggregation
    POD_INFO = 'kube_pod_info'
    
    # Node Metrics
    NODE_CPU_ALLOCATABLE = 'kube_node_status_allocatable{resource="cpu"}'
    NODE_MEMORY_ALLOCATABLE = 'kube_node_status_allocatable{resource="memory"}'
    # Current usage (not percentiles - avoids invalid PromQL with aggregation + range)
    NODE_CPU_USAGE = 'sum by (node)(rate(container_cpu_usage_seconds_total{container!=""}[5m]))'
    NODE_MEMORY_USAGE = 'sum by (node)(container_memory_working_set_bytes{container!=""})'
    NODE_INFO = 'kube_node_info'
    
    # HPA Metrics
    HPA_SPEC_MIN = 'kube_horizontalpodautoscaler_spec_min_replicas'
    HPA_SPEC_MAX = 'kube_horizontalpodautoscaler_spec_max_replicas'
    HPA_STATUS_CURRENT = 'kube_horizontalpodautoscaler_status_current_replicas'
    HPA_STATUS_DESIRED = 'kube_horizontalpodautoscaler_status_desired_replicas'
    HPA_INFO = 'kube_horizontalpodautoscaler_info'
    HPA_SPEC_TARGET_METRIC = 'kube_horizontalpodautoscaler_spec_target_metric'


# =============================================================================
# Data Fetching
# =============================================================================
def fetch_pod_metrics(prom_url: str) -> Dict[str, Any]:
    """Fetch all pod-level metrics including pod-to-node mapping"""
    
    # Fetch pod-to-node mapping from kube_pod_info
    # This is CRITICAL for node-scoped calculations in NODE_RIGHTSIZE
    pod_info_raw = prometheus_query(prom_url, PrometheusQueries.POD_INFO)
    pod_to_node = {}  # (namespace, pod) -> node
    for item in pod_info_raw:
        labels = item.get("metric", {})
        ns = labels.get("namespace", "")
        pod = labels.get("pod", "")
        node = labels.get("node", "")
        if ns and pod and node:
            pod_to_node[(ns, pod)] = node
    
    # Build queries with configured query_window
    queries = build_promql_queries()
    
    return {
        "cpu_requests": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.POD_CPU_REQUESTS),
            ["namespace", "pod"]
        ),
        "memory_requests": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.POD_MEMORY_REQUESTS),
            ["namespace", "pod"]
        ),
        "cpu_limits": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.POD_CPU_LIMITS),
            ["namespace", "pod"]
        ),
        "memory_limits": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.POD_MEMORY_LIMITS),
            ["namespace", "pod"]
        ),
        "cpu_p95": extract_metrics_by_labels(
            prometheus_query(prom_url, queries["POD_CPU_P95"]),
            ["namespace", "pod"]
        ),
        "cpu_p99": extract_metrics_by_labels(
            prometheus_query(prom_url, queries["POD_CPU_P99"]),
            ["namespace", "pod"]
        ),
        "cpu_p100": extract_metrics_by_labels(
            prometheus_query(prom_url, queries["POD_CPU_P100"]),
            ["namespace", "pod"]
        ),
        "memory_p95": extract_metrics_by_labels(
            prometheus_query(prom_url, queries["POD_MEMORY_P95"]),
            ["namespace", "pod"]
        ),
        "memory_p99": extract_metrics_by_labels(
            prometheus_query(prom_url, queries["POD_MEMORY_P99"]),
            ["namespace", "pod"]
        ),
        "memory_p100": extract_metrics_by_labels(
            prometheus_query(prom_url, queries["POD_MEMORY_P100"]),
            ["namespace", "pod"]
        ),
        # Pod-to-node mapping for node-scoped aggregation
        "pod_to_node": pod_to_node,
    }


def fetch_node_metrics(prom_url: str) -> Dict[str, Any]:
    """Fetch all node-level metrics
    
    Note: Node usage is fetched as current values (not percentiles) to avoid
    invalid PromQL with aggregation + range selectors. Node efficiency uses
    current CPU/memory usage which is sufficient for sizing recommendations.
    """
    # Get node info for instance -> node mapping (legacy compatibility)
    node_info_raw = prometheus_query(prom_url, PrometheusQueries.NODE_INFO)
    instance_to_node = {}
    for item in node_info_raw:
        labels = item.get("metric", {})
        instance = labels.get("instance", "")
        node = labels.get("node", "")
        if instance and node:
            instance_to_node[instance] = node
    
    return {
        "cpu_allocatable": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.NODE_CPU_ALLOCATABLE),
            ["node"]
        ),
        "memory_allocatable": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.NODE_MEMORY_ALLOCATABLE),
            ["node"]
        ),
        # Current usage by node (not percentiles - simpler and avoids invalid PromQL)
        "cpu_usage": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.NODE_CPU_USAGE),
            ["node"]
        ),
        "memory_usage": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.NODE_MEMORY_USAGE),
            ["node"]
        ),
        "instance_to_node": instance_to_node,
    }


def fetch_hpa_metrics(prom_url: str) -> Dict[str, Any]:
    """Fetch all HPA-level metrics"""
    return {
        "min_replicas": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.HPA_SPEC_MIN),
            ["namespace", "horizontalpodautoscaler"]
        ),
        "max_replicas": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.HPA_SPEC_MAX),
            ["namespace", "horizontalpodautoscaler"]
        ),
        "current_replicas": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.HPA_STATUS_CURRENT),
            ["namespace", "horizontalpodautoscaler"]
        ),
        "desired_replicas": extract_metrics_by_labels(
            prometheus_query(prom_url, PrometheusQueries.HPA_STATUS_DESIRED),
            ["namespace", "horizontalpodautoscaler"]
        ),
        "info": prometheus_query(prom_url, PrometheusQueries.HPA_INFO),
        "target_metrics": prometheus_query(prom_url, PrometheusQueries.HPA_SPEC_TARGET_METRIC),
    }


# =============================================================================
# POD_RESIZE Recommendations
# =============================================================================


def calculate_pod_resize(
    namespace: str,
    pod: str,
    pod_metrics: Dict[str, Any],
    env: str,
    pod_config: Dict[str, Any],
    memory_buckets: List[int]
) -> Optional[Dict[str, Any]]:
    """Calculate POD_RESIZE recommendation for a single pod
    
    Args:
        namespace: Pod namespace
        pod: Pod name
        pod_metrics: Dict with all pod metrics
        env: Environment (prod/nonprod)
        pod_config: Pod threshold config from config.yaml
        memory_buckets: Pre-computed memory bucket list with buffer
    """
    key = (namespace, pod)
    
    # Get current values
    cpu_request_current = pod_metrics["cpu_requests"].get(key)
    memory_request_current = pod_metrics["memory_requests"].get(key)
    cpu_limit_current = pod_metrics["cpu_limits"].get(key)
    memory_limit_current = pod_metrics["memory_limits"].get(key)
    
    # Get usage percentiles
    cpu_p95 = pod_metrics["cpu_p95"].get(key)
    cpu_p99 = pod_metrics["cpu_p99"].get(key)
    cpu_p100 = pod_metrics["cpu_p100"].get(key)
    memory_p95 = pod_metrics["memory_p95"].get(key)
    memory_p99 = pod_metrics["memory_p99"].get(key)
    memory_p100 = pod_metrics["memory_p100"].get(key)
    
    # Skip if no usage data
    if cpu_p99 is None or memory_p99 is None:
        return None
    
    prod = is_prod(env)
    
    # Get thresholds from config
    cpu_floor = pod_config.get("cpu_floor_prod" if prod else "cpu_floor_nonprod", 0.1 if prod else 0.05)
    safety_factor = pod_config.get("safety_factor_prod" if prod else "safety_factor_nonprod", 1.15 if prod else 1.10)
    cpu_request_mult = pod_config.get("cpu_request_multiplier", 1.20)
    cpu_limit_req_mult = pod_config.get("cpu_limit_request_multiplier", 1.50)
    cpu_limit_p100_mult = pod_config.get("cpu_limit_p100_multiplier", 1.25)
    mem_limit_req_mult = pod_config.get("memory_limit_request_multiplier", 1.50)
    mem_limit_p100_mult = pod_config.get("memory_limit_p100_multiplier", 1.25)
    change_tolerance = pod_config.get("change_tolerance", 0.10)
    
    # CPU Request: max(cpu_p99 × multiplier, cpu_floor)
    # Note: CPU is NOT normalized to buckets
    cpu_request_new = max(cpu_p99 * cpu_request_mult, cpu_floor)
    
    # CPU Limit: max(cpu_request_new × 1.50, cpu_p100 × 1.25)
    cpu_limit_new = max(
        cpu_request_new * cpu_limit_req_mult,
        (cpu_p100 or cpu_p99) * cpu_limit_p100_mult
    )
    
    # Memory Request: memory_p99 × safety_factor, then normalize to bucket
    memory_request_raw = memory_p99 * safety_factor
    memory_request_new = normalize_memory_to_bucket(memory_request_raw, memory_buckets)
    
    # Memory Limit: max(memory_request_new × 1.50, memory_p100 × 1.25)
    # Uses normalized memory request for consistency
    memory_limit_new = max(
        memory_request_new * mem_limit_req_mult,
        (memory_p100 or memory_p99) * mem_limit_p100_mult
    )
    
    # Check if changes are needed (use configured tolerance)
    cpu_req_change = abs((cpu_request_new - (cpu_request_current or cpu_request_new)) / max(cpu_request_new, 0.001)) > change_tolerance
    mem_req_change = abs((memory_request_new - (memory_request_current or memory_request_new)) / max(memory_request_new, 1)) > change_tolerance
    
    if not cpu_req_change and not mem_req_change:
        return None
    
    # Calculate savings (negative = reduction/savings, positive = increase needed)
    cpu_request_diff = cpu_request_new - (cpu_request_current or 0)
    memory_request_diff = int(memory_request_new) - int(memory_request_current or 0)
    
    return {
        "type": "POD_RESIZE",
        "namespace": namespace,
        "pod": pod,
        "current": {
            "cpu_request": cpu_request_current,
            "cpu_limit": cpu_limit_current,
            "memory_request": memory_request_current,
            "memory_limit": memory_limit_current,
        },
        "recommended": {
            "cpu_request": round(cpu_request_new, 4),
            "cpu_limit": round(cpu_limit_new, 4),
            "memory_request": int(memory_request_new),
            "memory_limit": int(memory_limit_new),
        },
        "savings": {
            "cpu_cores": round(-cpu_request_diff, 4),  # Positive = savings
            "memory_bytes": -memory_request_diff,  # Positive = savings
            "memory_mb": round(-memory_request_diff / (1024 * 1024), 1),
        },
        "usage_percentiles": {
            "cpu_p95": round(cpu_p95 or 0, 4),
            "cpu_p99": round(cpu_p99, 4),
            "cpu_p100": round(cpu_p100 or 0, 4),
            "memory_p95": int(memory_p95 or 0),
            "memory_p99": int(memory_p99),
            "memory_p100": int(memory_p100 or 0),
        },
        "explanation": build_pod_resize_explanation(
            cpu_request_current, cpu_request_new,
            memory_request_current, memory_request_new,
            cpu_p99, memory_p99, env
        ),
    }


def build_pod_resize_explanation(
    cpu_req_curr: Optional[float],
    cpu_req_new: float,
    mem_req_curr: Optional[float],
    mem_req_new: float,
    cpu_p99: float,
    mem_p99: float,
    env: str
) -> str:
    """Build human-readable explanation for POD_RESIZE"""
    parts = []
    
    if cpu_req_curr:
        cpu_change = ((cpu_req_new - cpu_req_curr) / cpu_req_curr) * 100
        direction = "increase" if cpu_change > 0 else "decrease"
        parts.append(f"CPU request {direction} by {abs(cpu_change):.1f}% based on P99 usage ({cpu_p99:.3f} cores)")
    else:
        parts.append(f"Set CPU request to {cpu_req_new:.3f} cores based on P99 usage")
    
    if mem_req_curr:
        mem_change = ((mem_req_new - mem_req_curr) / mem_req_curr) * 100
        direction = "increase" if mem_change > 0 else "decrease"
        parts.append(f"Memory request {direction} by {abs(mem_change):.1f}% based on P99 usage ({mem_p99 / 1e6:.1f}MB)")
    else:
        parts.append(f"Set memory request to {mem_req_new / 1e6:.1f}MB based on P99 usage")
    
    safety = "prod (1.15x)" if is_prod(env) else "nonprod (1.10x)"
    parts.append(f"Safety factor: {safety}")
    
    return "; ".join(parts)


def analyze_pod_resize(
    pod_metrics: Dict[str, Any], 
    env: str,
    pod_config: Dict[str, Any],
    memory_buckets: List[int],
    exclude_namespaces: List[str] = None
) -> List[Dict[str, Any]]:
    """Generate all POD_RESIZE recommendations
    
    Args:
        pod_metrics: Pod metrics from Prometheus
        env: Environment (prod/nonprod)
        pod_config: Pod threshold config from config.yaml
        memory_buckets: Pre-computed memory bucket list with buffer
        exclude_namespaces: List of namespaces to skip
    """
    recommendations = []
    exclude_namespaces = exclude_namespaces or []
    
    # Get all unique pods
    all_pods = set(pod_metrics["cpu_requests"].keys())
    all_pods.update(pod_metrics["cpu_p99"].keys())
    
    for key in all_pods:
        namespace, pod = key
        # Skip excluded namespaces
        if namespace in exclude_namespaces:
            continue
        rec = calculate_pod_resize(namespace, pod, pod_metrics, env, pod_config, memory_buckets)
        if rec:
            recommendations.append(rec)
    
    return recommendations


# =============================================================================
# NODE_RIGHTSIZE Recommendations (Calculation-Based)
# =============================================================================

def get_pods_on_node(node_name: str, pod_to_node: Dict[Tuple[str, str], str]) -> List[Tuple[str, str]]:
    """Get list of (namespace, pod) tuples scheduled on a specific node"""
    return [pod_key for pod_key, node in pod_to_node.items() if node == node_name]


def calculate_recommended_pod_values(
    pod_key: Tuple[str, str],
    pod_metrics: Dict[str, Any],
    env: str,
    pod_config: Dict[str, Any],
    memory_buckets: List[int]
) -> Tuple[float, int]:
    """Calculate recommended CPU and memory values for a pod after POD_RESIZE
    
    Returns (cpu_request_new, memory_request_new) based on POD_RESIZE formulas.
    These are the post-resize values used for node consolidation calculations.
    """
    cpu_p99 = pod_metrics["cpu_p99"].get(pod_key, 0) or 0
    memory_p99 = pod_metrics["memory_p99"].get(pod_key, 0) or 0
    
    prod = is_prod(env)
    
    # Get thresholds from config
    cpu_floor = pod_config.get("cpu_floor_prod" if prod else "cpu_floor_nonprod", 0.1 if prod else 0.05)
    safety_factor = pod_config.get("safety_factor_prod" if prod else "safety_factor_nonprod", 1.15 if prod else 1.10)
    cpu_request_mult = pod_config.get("cpu_request_multiplier", 1.20)
    
    # CPU: max(cpu_p99 × multiplier, cpu_floor)
    cpu_request_new = max(cpu_p99 * cpu_request_mult, cpu_floor)
    
    # Memory: memory_p99 × safety_factor, then normalize to bucket
    memory_request_raw = memory_p99 * safety_factor
    memory_request_new = normalize_memory_to_bucket(memory_request_raw, memory_buckets)
    
    return cpu_request_new, memory_request_new


def calculate_node_efficiency(
    node_cpu_p95: float,
    node_memory_p95: float,
    node_cpu_capacity: float,
    node_memory_capacity: float
) -> Tuple[float, float, float]:
    """Calculate node efficiency metrics
    
    Returns:
        (cpu_efficiency, memory_efficiency, node_efficiency)
        
    Interpretation of node_efficiency:
        < 0.40 → strongly oversized
        0.40 – 0.65 → moderately oversized
        0.65 – 0.85 → right-sized
        > 0.85 → tight
    """
    cpu_efficiency = node_cpu_p95 / node_cpu_capacity if node_cpu_capacity > 0 else 0
    memory_efficiency = node_memory_p95 / node_memory_capacity if node_memory_capacity > 0 else 0
    node_efficiency = 0.5 * cpu_efficiency + 0.5 * memory_efficiency
    return cpu_efficiency, memory_efficiency, node_efficiency


def calculate_consolidation_feasibility(
    total_cpu_required: float,
    total_memory_required: float,
    node_cpu_capacity: float,
    node_memory_capacity: float,
    current_node_count: int,
    usable_capacity_factor: float = 0.80
) -> Tuple[int, int, int, bool]:
    """Determine whether node count can be reduced
    
    Returns:
        (required_nodes_cpu, required_nodes_memory, required_nodes, consolidation_possible)
    """
    import math
    
    # Usable capacity per node (safe headroom)
    usable_cpu_per_node = node_cpu_capacity * usable_capacity_factor
    usable_memory_per_node = node_memory_capacity * usable_capacity_factor
    
    # Required node count
    required_nodes_cpu = math.ceil(total_cpu_required / usable_cpu_per_node) if usable_cpu_per_node > 0 else current_node_count
    required_nodes_memory = math.ceil(total_memory_required / usable_memory_per_node) if usable_memory_per_node > 0 else current_node_count
    required_nodes = max(required_nodes_cpu, required_nodes_memory)
    
    # Consolidation rule
    consolidation_possible = required_nodes < current_node_count
    
    return required_nodes_cpu, required_nodes_memory, required_nodes, consolidation_possible


def calculate_shape_imbalance(
    node_cpu_p95: float,
    node_memory_p95: float,
    node_cpu_capacity: float,
    node_memory_capacity: float,
    shape_imbalance_threshold: float = 0.25
) -> Tuple[float, float, bool, str]:
    """Detect CPU-heavy or memory-heavy node shapes
    
    Returns:
        (cpu_pressure, memory_pressure, is_imbalanced, imbalance_direction)
        imbalance_direction: 'cpu-heavy' | 'memory-heavy' | 'balanced'
    """
    cpu_pressure = node_cpu_p95 / node_cpu_capacity if node_cpu_capacity > 0 else 0
    memory_pressure = node_memory_p95 / node_memory_capacity if node_memory_capacity > 0 else 0
    
    pressure_diff = abs(cpu_pressure - memory_pressure)
    is_imbalanced = pressure_diff > shape_imbalance_threshold
    
    if not is_imbalanced:
        imbalance_direction = "balanced"
    elif cpu_pressure > memory_pressure:
        imbalance_direction = "cpu-heavy"  # Suggest less memory per CPU
    else:
        imbalance_direction = "memory-heavy"  # Suggest more memory per CPU
    
    return cpu_pressure, memory_pressure, is_imbalanced, imbalance_direction


def calculate_smaller_node_strategy(
    avg_pod_cpu: float,
    avg_pod_memory: float,
    usable_cpu_per_node: float,
    usable_memory_per_node: float,
    node_efficiency: float,
    moderately_oversized_threshold: float = 0.65
) -> Tuple[float, float, bool]:
    """Determine whether smaller nodes would pack workloads better
    
    Returns:
        (cpu_pods_per_node, memory_pods_per_node, recommend_smaller_nodes)
    """
    cpu_pods_per_node = usable_cpu_per_node / avg_pod_cpu if avg_pod_cpu > 0 else 0
    memory_pods_per_node = usable_memory_per_node / avg_pod_memory if avg_pod_memory > 0 else 0
    
    # Recommend smaller nodes if ALL are true:
    # - node_efficiency < moderately_oversized threshold
    # - avg pod size is small relative to node capacity (high packing density possible)
    # High packing density = can fit many pods per node
    recommend_smaller_nodes = (
        node_efficiency < moderately_oversized_threshold and
        cpu_pods_per_node > 10 and  # Can fit many pods
        memory_pods_per_node > 10
    )
    
    return cpu_pods_per_node, memory_pods_per_node, recommend_smaller_nodes


def generate_cluster_node_recommendation(
    node_metrics: Dict[str, Any],
    pod_metrics: Dict[str, Any],
    pod_resize_recs: List[Dict[str, Any]],
    env: str,
    pod_config: Dict[str, Any],
    memory_buckets: List[int],
    thresholds: Dict[str, Any] = None
) -> Optional[Dict[str, Any]]:
    """Generate cluster-level NODE_RIGHTSIZE recommendation based on calculations
    
    Node recommendations are based on post pod-resize values.
    Output: direction (up | down | right-size), reason, example, confidence
    
    Args:
        pod_config: Pod threshold config from config.yaml
        memory_buckets: Pre-computed memory bucket list with buffer
        thresholds: Dict with cpu_low_pct, cpu_high_pct, memory_low_pct, memory_high_pct
    """
    thresholds = thresholds or DEFAULT_CONFIG["thresholds"]["node"]
    cpu_low_pct = thresholds.get("cpu_low_pct", 40) / 100
    cpu_high_pct = thresholds.get("cpu_high_pct", 75) / 100
    memory_low_pct = thresholds.get("memory_low_pct", 50) / 100
    memory_high_pct = thresholds.get("memory_high_pct", 75) / 100
    usable_capacity_factor = thresholds.get("usable_capacity_factor", 0.80)
    shape_imbalance_threshold = thresholds.get("shape_imbalance_threshold", 0.25)
    # Moderately oversized threshold = average of low thresholds
    moderately_oversized = (cpu_low_pct + memory_low_pct) / 2  # ~ 0.45
    
    # Get all nodes
    nodes = list(node_metrics["cpu_allocatable"].keys())
    if not nodes:
        return None
    
    current_node_count = len(nodes)
    if current_node_count == 0:
        return None
    
    # Use first node's capacity as reference (assumes homogeneous cluster)
    # In heterogeneous clusters, this is a simplification
    first_node = nodes[0][0]
    node_cpu_capacity = node_metrics["cpu_allocatable"].get((first_node,), 0)
    node_memory_capacity = node_metrics["memory_allocatable"].get((first_node,), 0)
    
    if not node_cpu_capacity or not node_memory_capacity:
        return None
    
    pod_to_node = pod_metrics.get("pod_to_node", {})
    all_pods = list(pod_to_node.keys())
    
    if not all_pods:
        return None
    
    # Calculate post-resize values for all pods
    # Build a map of pod -> recommended values
    pod_recommended = {}
    for pod_key in all_pods:
        # Check if there's a POD_RESIZE recommendation for this pod
        rec_match = None
        for rec in pod_resize_recs:
            if (rec["namespace"], rec["pod"]) == pod_key:
                rec_match = rec
                break
        
        if rec_match:
            # Use values from POD_RESIZE recommendation
            cpu_new = rec_match["recommended"]["cpu_request"]
            mem_new = rec_match["recommended"]["memory_request"]
        else:
            # Calculate what the recommended values would be
            cpu_new, mem_new = calculate_recommended_pod_values(pod_key, pod_metrics, env, pod_config, memory_buckets)
        
        pod_recommended[pod_key] = (cpu_new, mem_new)
    
    # Step 1: Total required capacity (after POD_RESIZE)
    total_cpu_required = sum(v[0] for v in pod_recommended.values())
    total_memory_required = sum(v[1] for v in pod_recommended.values())
    
    # Step 2: Calculate cluster-wide node metrics
    # Sum node usage across all nodes
    total_node_cpu_p95 = sum(
        node_metrics["cpu_usage"].get((n,), 0) for (n,) in nodes
    )
    total_node_memory_p95 = sum(
        node_metrics["memory_usage"].get((n,), 0) for (n,) in nodes
    )
    total_node_cpu_capacity = sum(
        node_metrics["cpu_allocatable"].get((n,), 0) for (n,) in nodes
    )
    total_node_memory_capacity = sum(
        node_metrics["memory_allocatable"].get((n,), 0) for (n,) in nodes
    )
    
    # Calculate efficiency (cluster-wide average per node)
    avg_node_cpu_p95 = total_node_cpu_p95 / current_node_count
    avg_node_memory_p95 = total_node_memory_p95 / current_node_count
    
    cpu_efficiency, memory_efficiency, node_efficiency = calculate_node_efficiency(
        avg_node_cpu_p95, avg_node_memory_p95,
        node_cpu_capacity, node_memory_capacity
    )
    
    # Step 3: Consolidation feasibility
    req_nodes_cpu, req_nodes_memory, required_nodes, consolidation_possible = calculate_consolidation_feasibility(
        total_cpu_required, total_memory_required,
        node_cpu_capacity, node_memory_capacity,
        current_node_count, usable_capacity_factor
    )
    
    # Step 4: Shape imbalance
    cpu_pressure, memory_pressure, is_imbalanced, imbalance_direction = calculate_shape_imbalance(
        avg_node_cpu_p95, avg_node_memory_p95,
        node_cpu_capacity, node_memory_capacity,
        shape_imbalance_threshold
    )
    
    # Step 5: Smaller node strategy
    avg_pod_cpu = total_cpu_required / len(all_pods) if all_pods else 0
    avg_pod_memory = total_memory_required / len(all_pods) if all_pods else 0
    usable_cpu_per_node = node_cpu_capacity * usable_capacity_factor
    usable_memory_per_node = node_memory_capacity * usable_capacity_factor
    
    cpu_pods_per_node, memory_pods_per_node, recommend_smaller_nodes = calculate_smaller_node_strategy(
        avg_pod_cpu, avg_pod_memory,
        usable_cpu_per_node, usable_memory_per_node,
        node_efficiency, moderately_oversized
    )
    
    # Determine direction, reason, confidence using config thresholds
    direction = None
    reasons = []
    confidence = "low"
    example = ""
    
    # Use config thresholds for decision logic
    # cpu_utilization and memory_utilization as percentages for threshold comparison
    cpu_utilization = cpu_efficiency
    memory_utilization = memory_efficiency
    
    # Decision logic per spec:
    # IF cpu_utilization < cpu_low_pct AND memory_utilization < memory_low_pct → scale down
    # IF cpu_utilization > cpu_high_pct OR memory_utilization > memory_high_pct → scale up
    # ELSE → right size
    
    if cpu_utilization > cpu_high_pct or memory_utilization > memory_high_pct:
        # Scale UP - nodes are tight
        direction = "up"
        reasons.append(f"CPU utilization is {cpu_utilization:.0%} and memory utilization is {memory_utilization:.0%}, indicating nodes are running tight.")
        confidence = "high" if (cpu_utilization > cpu_high_pct and memory_utilization > memory_high_pct) else "medium"
        example = "Consider adding nodes or using larger instance sizes"
    elif cpu_utilization < cpu_low_pct and memory_utilization < memory_low_pct:
        # Scale DOWN - nodes are oversized
        direction = "down"
        if consolidation_possible:
            reasons.append(NODE_STATEMENTS["consolidation"])
            nodes_saved = current_node_count - required_nodes
            confidence = "high" if nodes_saved >= 2 else "medium"
            example = f"Replace {current_node_count} × ({node_cpu_capacity:.0f} CPU, {node_memory_capacity / (1024**3):.0f} GB) nodes with {required_nodes} × ({node_cpu_capacity:.0f} CPU, {node_memory_capacity / (1024**3):.0f} GB) nodes."
        elif recommend_smaller_nodes:
            reasons.append(NODE_STATEMENTS["smaller_nodes"])
            confidence = "medium"
            smaller_cpu = node_cpu_capacity / 2
            smaller_mem = node_memory_capacity / 2
            new_count = required_nodes * 2
            example = f"Replace {current_node_count} × ({node_cpu_capacity:.0f} CPU, {node_memory_capacity / (1024**3):.0f} GB) nodes with {new_count} × ({smaller_cpu:.0f} CPU, {smaller_mem / (1024**3):.0f} GB) nodes."
        else:
            reasons.append(f"CPU utilization is {cpu_utilization:.0%} and memory utilization is {memory_utilization:.0%}, indicating the node is underused.")
            confidence = "medium"
            example = "Consider using smaller node sizes"
    elif is_imbalanced:
        # RIGHT SIZE - shape imbalance
        direction = "right-size"
        reasons.append(NODE_STATEMENTS["shape_imbalance"])
        confidence = "medium"
        if imbalance_direction == "cpu-heavy":
            example = f"Consider node types with less memory relative to CPU (current shape uses {memory_pressure:.0%} memory vs {cpu_pressure:.0%} CPU)"
        else:
            example = f"Consider node types with more memory relative to CPU (current shape uses {memory_pressure:.0%} memory vs {cpu_pressure:.0%} CPU)"
    
    # No recommendation if already right-sized (within acceptable range)
    if not direction:
        return None
    
    # Efficiency state for reporting
    efficiency_state = ""
    if node_efficiency < cpu_low_pct:
        efficiency_state = "strongly_oversized"
    elif node_efficiency < memory_low_pct:
        efficiency_state = "moderately_oversized"
    elif node_efficiency < cpu_high_pct:
        efficiency_state = "right_sized"
    else:
        efficiency_state = "tight"
    
    return {
        "type": "NODE_RIGHTSIZE",
        "direction": direction,
        "reason": " ".join(reasons),
        "example": example,
        "confidence": confidence,
        "metrics": {
            "current_node_count": current_node_count,
            "required_nodes": required_nodes,
            "required_nodes_cpu": req_nodes_cpu,
            "required_nodes_memory": req_nodes_memory,
            "node_cpu_capacity": round(node_cpu_capacity, 2),
            "node_memory_capacity": {
                "bytes": int(node_memory_capacity),
                "gb": round(node_memory_capacity / (1024 ** 3), 1)
            },
            "node_efficiency": round(node_efficiency, 3),
            "cpu_efficiency": round(cpu_efficiency, 3),
            "memory_efficiency": round(memory_efficiency, 3),
            "efficiency_state": efficiency_state,
            "cpu_pressure": round(cpu_pressure, 3),
            "memory_pressure": round(memory_pressure, 3),
            "shape_imbalanced": is_imbalanced,
            "imbalance_direction": imbalance_direction,
            "total_cpu_required": round(total_cpu_required, 2),
            "total_memory_required": {
                "bytes": int(total_memory_required),
                "gb": round(total_memory_required / (1024 ** 3), 1)
            },
            "avg_pod_cpu": round(avg_pod_cpu, 4),
            "avg_pod_memory": {
                "bytes": int(avg_pod_memory),
                "mb": round(avg_pod_memory / (1024 * 1024), 1)
            },
            "cpu_pods_per_node": round(cpu_pods_per_node, 1),
            "memory_pods_per_node": round(memory_pods_per_node, 1),
            "consolidation_possible": consolidation_possible,
            "pod_count": len(all_pods),
        },
    }


def analyze_node_rightsize(
    node_metrics: Dict[str, Any],
    pod_metrics: Dict[str, Any],
    pod_resize_recs: List[Dict[str, Any]],
    env: str,
    pod_config: Dict[str, Any],
    memory_buckets: List[int],
    thresholds: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """Generate NODE_RIGHTSIZE recommendations
    
    Returns a single cluster-level recommendation based on calculations.
    
    Args:
        node_metrics: Node metrics from Prometheus
        pod_metrics: Pod metrics from Prometheus
        pod_resize_recs: POD_RESIZE recommendations (for post-resize values)
        env: Environment (prod/nonprod)
        pod_config: Pod threshold config from config.yaml
        memory_buckets: Pre-computed memory bucket list with buffer
        thresholds: Node thresholds (cpu_low_pct, cpu_high_pct, etc.)
    """
    recommendations = []
    thresholds = thresholds or DEFAULT_CONFIG["thresholds"]["node"]
    
    rec = generate_cluster_node_recommendation(
        node_metrics, pod_metrics, pod_resize_recs, env,
        pod_config, memory_buckets, thresholds
    )
    if rec:
        recommendations.append(rec)
    
    return recommendations


# =============================================================================
# HPA_MISALIGNMENT Detection
# =============================================================================


def detect_hpa_misalignment(
    hpa_metrics: Dict[str, Any],
    pod_metrics: Dict[str, Any],
    env: str,
    thresholds: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """Detect HPA misalignment issues
    
    Uses heuristic pod matching (HPA target name as substring of pod name).
    Generates advisory recommendations only - no automatic changes.
    
    Args:
        thresholds: Dict with cpu_low_util_pct, cpu_very_low_util_pct, memory_high_util_pct
    """
    recommendations = []
    thresholds = thresholds or DEFAULT_CONFIG["thresholds"]["hpa"]
    
    # Convert percentage thresholds to ratios
    cpu_low_util = thresholds.get("cpu_low_util_pct", 40) / 100
    cpu_very_low_util = thresholds.get("cpu_very_low_util_pct", 30) / 100
    memory_high_util = thresholds.get("memory_high_util_pct", 85) / 100
    
    # Parse HPA info to get target deployments
    hpa_targets = {}
    for item in hpa_metrics.get("info", []):
        labels = item.get("metric", {})
        ns = labels.get("namespace", "")
        hpa = labels.get("horizontalpodautoscaler", "")
        target_name = labels.get("scaletargetref_name", "")
        target_kind = labels.get("scaletargetref_kind", "")
        if ns and hpa:
            hpa_targets[(ns, hpa)] = {
                "target_name": target_name,
                "target_kind": target_kind,
            }
    
    # Check each HPA
    for (ns, hpa), target_info in hpa_targets.items():
        key = (ns, hpa)
        
        min_replicas = hpa_metrics["min_replicas"].get(key, 1)
        max_replicas = hpa_metrics["max_replicas"].get(key, 10)
        current_replicas = hpa_metrics["current_replicas"].get(key, 0)
        
        target_name = target_info.get("target_name", "")
        
        # Find pods matching this HPA's target (heuristic: target_name is substring of pod_name)
        matching_pods = [
            k for k in pod_metrics["cpu_p95"].keys()
            if k[0] == ns and target_name and target_name in k[1]
        ]
        
        # Skip if no pods match - do not generate recommendations
        if not matching_pods:
            continue
        
        # Calculate average CPU usage for pods
        avg_cpu_usage = sum(
            pod_metrics["cpu_p95"].get(p, 0) or 0 for p in matching_pods
        ) / len(matching_pods)
        
        avg_cpu_request = sum(
            pod_metrics["cpu_requests"].get(p, 0) for p in matching_pods
        ) / len(matching_pods)
        
        avg_memory_p95 = sum(
            pod_metrics["memory_p95"].get(p, 0) or 0 for p in matching_pods
        ) / len(matching_pods)
        
        avg_memory_request = sum(
            pod_metrics["memory_requests"].get(p, 0) for p in matching_pods
        ) / len(matching_pods)
        
        # Collect advisory statements (not reasons)
        advisory_statements = []
        
        # Rule 1: CPU-based HPA with low CPU usage (cpu_p95 < cpu_low_util_pct% of cpu_request)
        if avg_cpu_request > 0 and avg_cpu_usage / avg_cpu_request < cpu_low_util:
            advisory_statements.append(HPA_STATEMENTS["cpu_based"])
        
        # Rule 2: Memory-bound workload with CPU HPA
        # memory_p95 >= memory_high_util_pct% AND cpu_p95 < cpu_low_util_pct%
        if avg_memory_request > 0 and avg_cpu_request > 0:
            memory_ratio = avg_memory_p95 / avg_memory_request if avg_memory_request > 0 else 0
            cpu_ratio = avg_cpu_usage / avg_cpu_request if avg_cpu_request > 0 else 0
            if memory_ratio >= memory_high_util and cpu_ratio < cpu_low_util:
                advisory_statements.append(HPA_STATEMENTS["memory_bound"])
        
        # Rule 3: minReplicas blocking consolidation (minReplicas > 1 AND avg_cpu < cpu_very_low_util_pct%)
        if min_replicas > 2 and current_replicas == min_replicas:
            avg_utilization = 0
            if avg_cpu_request > 0:
                avg_utilization = avg_cpu_usage / avg_cpu_request
            if avg_utilization < cpu_very_low_util:
                advisory_statements.append(HPA_STATEMENTS["min_replicas"])
        
        # Rule 4: maxReplicas rarely reached (if current is always at min)
        if current_replicas == min_replicas and max_replicas > min_replicas * 2:
            advisory_statements.append(HPA_STATEMENTS["max_replicas"])
        
        if advisory_statements:
            recommendations.append({
                "type": "HPA_MISALIGNMENT",
                "namespace": ns,
                "hpa": hpa,
                "target": target_info,
                "config": {
                    "min_replicas": int(min_replicas),
                    "max_replicas": int(max_replicas),
                    "current_replicas": int(current_replicas),
                },
                "metrics": {
                    "avg_cpu_usage": round(avg_cpu_usage, 4),
                    "avg_cpu_request": round(avg_cpu_request, 4),
                    "avg_memory_p95": int(avg_memory_p95),
                    "avg_memory_request": int(avg_memory_request),
                    "matched_pod_count": len(matching_pods),
                },
                "advisory": advisory_statements,
                "explanation": " ".join(advisory_statements),
            })
    
    return recommendations


# =============================================================================
# Email Placeholder
# =============================================================================
def send_email(recipients: List[str], subject: str, body: str) -> None:
    """Send email notification
    
    TODO: Integrate email provider (SMTP, SendGrid, SES, etc.)
    """
    logger.info(f"[EMAIL PLACEHOLDER] To: {recipients}, Subject: {subject}")
    pass


# =============================================================================
# Output Generation
# =============================================================================
def generate_output(
    cluster_name: str,
    env: str,
    project: str,
    recommendations: List[Dict[str, Any]],
    limitations_text: str,
    totals: Dict[str, int],
    query_window: str = None
) -> Dict[str, Any]:
    """Generate analysis output JSON
    
    Args:
        cluster_name: Name of the cluster being analyzed
        env: Environment (prod/nonprod)
        project: Project identifier
        recommendations: List of all recommendations
        limitations_text: Single consolidated limitations text from config
        totals: Dict with total counts of scanned entities (pods, nodes, hpas)
        query_window: Analysis window (e.g., "7d")
    """
    query_window = query_window or DEFAULT_CONFIG["settings"]["query_window"]
    
    # Calculate affected counts
    pod_resize_recs = [r for r in recommendations if r["type"] == "POD_RESIZE"]
    pod_resize_count = len(pod_resize_recs)
    node_rightsize_count = len([r for r in recommendations if r["type"] == "NODE_RIGHTSIZE"])
    hpa_misalignment_count = len([r for r in recommendations if r["type"] == "HPA_MISALIGNMENT"])
    
    # Calculate total savings from POD_RESIZE recommendations
    total_cpu_savings = sum(r.get("savings", {}).get("cpu_cores", 0) for r in pod_resize_recs)
    total_memory_savings_bytes = sum(r.get("savings", {}).get("memory_bytes", 0) for r in pod_resize_recs)
    total_memory_savings_mb = round(total_memory_savings_bytes / (1024 * 1024), 1)
    total_memory_savings_gb = round(total_memory_savings_bytes / (1024 ** 3), 2)
    
    # Get totals (scanned entities)
    total_pods = totals.get("pods", 0)
    total_nodes = totals.get("nodes", 0)
    total_hpas = totals.get("hpas", 0)
    
    # Build savings summary text
    cpu_savings_text = ""
    mem_savings_text = ""
    
    if total_cpu_savings > 0:
        cpu_savings_text = f"Save {total_cpu_savings:.2f} CPU cores"
    elif total_cpu_savings < 0:
        cpu_savings_text = f"Need {abs(total_cpu_savings):.2f} more CPU cores"
    
    if total_memory_savings_bytes > 0:
        mem_val = f"{total_memory_savings_gb:.1f}GB" if abs(total_memory_savings_gb) >= 1 else f"{total_memory_savings_mb:.0f}MB"
        mem_savings_text = f"Save {mem_val} memory"
    elif total_memory_savings_bytes < 0:
        mem_val = f"{abs(total_memory_savings_gb):.1f}GB" if abs(total_memory_savings_gb) >= 1 else f"{abs(total_memory_savings_mb):.0f}MB"
        mem_savings_text = f"Need {mem_val} more memory"
    
    savings_parts = [p for p in [cpu_savings_text, mem_savings_text] if p]
    
    return {
        "cluster": cluster_name,
        "env": "prod" if is_prod(env) else "nonprod",
        "project": project,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_window": query_window,
        "recommendations": recommendations,
        "limitations": limitations_text,
        "summary": {
            "total_recommendations": len(recommendations),
            "pods": {
                "affected": pod_resize_count,
                "total": total_pods,
                "text": f"{pod_resize_count} out of {total_pods} pods need resizing" if total_pods > 0 else "No pods scanned"
            },
            "nodes": {
                "affected": node_rightsize_count,
                "total": total_nodes,
                "text": f"Node recommendation available (cluster has {total_nodes} nodes)" if node_rightsize_count > 0 else f"No node changes needed ({total_nodes} nodes scanned)"
            },
            "hpa": {
                "affected": hpa_misalignment_count,
                "total": total_hpas,
                "text": f"{hpa_misalignment_count} out of {total_hpas} HPAs are misaligned" if total_hpas > 0 else "No HPAs scanned"
            },
            "potential_savings": {
                "cpu_cores": round(total_cpu_savings, 2),
                "memory_bytes": total_memory_savings_bytes,
                "memory_mb": total_memory_savings_mb,
                "memory_gb": total_memory_savings_gb,
                "text": "; ".join(savings_parts) if savings_parts else "No significant changes"
            },
            # Keep legacy fields for backward compatibility
            "pod_resize_count": pod_resize_count,
            "node_rightsize_count": node_rightsize_count,
            "hpa_misalignment_count": hpa_misalignment_count,
        },
    }


def write_output(output: Dict[str, Any], project: str, env: str) -> str:
    """Write output to JSON file"""
    env_class = "prod" if is_prod(env) else "nonprod"
    output_dir = os.path.join("output", project, env_class)
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "analysis.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    return output_path


# =============================================================================
# Main Analysis Pipeline
# =============================================================================
def analyze_cluster(
    cluster_name: str,
    cluster_config: Dict[str, Any],
    global_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Run complete analysis for a single cluster
    
    Args:
        cluster_name: Name of the cluster
        cluster_config: Cluster configuration from YAML
        global_config: Global config with settings, pod, memory_buckets, thresholds, limitations_text
    """
    env = cluster_config.get("env", "nonprod")
    project = cluster_config.get("project", "unknown")
    prom_url = cluster_config.get("prom_url", "http://localhost:9090")
    owner_email = cluster_config.get("owner_email", [])
    exclude_namespaces = cluster_config.get("exclude_namespaces", [])
    
    # Get config sections
    settings = global_config.get("settings", DEFAULT_CONFIG["settings"])
    pod_config = global_config.get("pod", DEFAULT_CONFIG["pod"])
    memory_buckets = global_config.get("memory_buckets", build_memory_buckets(global_config))
    thresholds = global_config.get("thresholds", DEFAULT_CONFIG["thresholds"])
    limitations_text = global_config.get("limitations_text", DEFAULT_CONFIG["limitations_text"])
    query_window = settings.get("query_window", "7d")
    
    logger.info(f"Analyzing cluster: {cluster_name} (env={env}, project={project})")
    logger.info(f"Prometheus URL: {prom_url}")
    if exclude_namespaces:
        logger.info(f"Excluding namespaces: {exclude_namespaces}")
    
    # Fetch all metrics
    try:
        pod_metrics = fetch_pod_metrics(prom_url)
        logger.info(f"Fetched metrics for {len(pod_metrics.get('cpu_requests', {}))} pods")
    except Exception as e:
        logger.error(f"Failed to fetch pod metrics: {e}")
        pod_metrics = {k: {} for k in [
            "cpu_requests", "memory_requests", "cpu_limits", "memory_limits",
            "cpu_p95", "cpu_p99", "cpu_p100", "memory_p95", "memory_p99", "memory_p100",
            "pod_to_node"
        ]}
    
    try:
        node_metrics = fetch_node_metrics(prom_url)
        logger.info(f"Fetched metrics for {len(node_metrics.get('cpu_allocatable', {}))} nodes")
    except Exception as e:
        logger.error(f"Failed to fetch node metrics: {e}")
        node_metrics = {
            "cpu_allocatable": {}, "memory_allocatable": {},
            "cpu_usage": {}, "memory_usage": {},
            "instance_to_node": {},
        }
    
    try:
        hpa_metrics = fetch_hpa_metrics(prom_url)
        logger.info(f"Fetched metrics for {len(hpa_metrics.get('min_replicas', {}))} HPAs")
    except Exception as e:
        logger.error(f"Failed to fetch HPA metrics: {e}")
        hpa_metrics = {
            "min_replicas": {}, "max_replicas": {},
            "current_replicas": {}, "desired_replicas": {},
            "info": [], "target_metrics": [],
        }
    
    # Generate recommendations
    recommendations = []
    
    # POD_RESIZE (uses pod_config and memory_buckets)
    pod_resize_recs = analyze_pod_resize(pod_metrics, env, pod_config, memory_buckets, exclude_namespaces)
    recommendations.extend(pod_resize_recs)
    logger.info(f"Generated {len(pod_resize_recs)} POD_RESIZE recommendations")
    
    # NODE_RIGHTSIZE (uses post-resize pod values and thresholds)
    node_thresholds = thresholds.get("node", DEFAULT_CONFIG["thresholds"]["node"])
    node_rightsize_recs = analyze_node_rightsize(
        node_metrics, pod_metrics, pod_resize_recs, env,
        pod_config, memory_buckets, node_thresholds
    )
    recommendations.extend(node_rightsize_recs)
    logger.info(f"Generated {len(node_rightsize_recs)} NODE_RIGHTSIZE recommendations")
    
    # HPA_MISALIGNMENT (uses thresholds)
    hpa_thresholds = thresholds.get("hpa", DEFAULT_CONFIG["thresholds"]["hpa"])
    hpa_misalignment_recs = detect_hpa_misalignment(hpa_metrics, pod_metrics, env, hpa_thresholds)
    recommendations.extend(hpa_misalignment_recs)
    logger.info(f"Generated {len(hpa_misalignment_recs)} HPA_MISALIGNMENT recommendations")
    
    # Calculate totals for summary (scanned entities, not just affected)
    totals = {
        "pods": len(pod_metrics.get("cpu_requests", {})),
        "nodes": len(node_metrics.get("cpu_allocatable", {})),
        "hpas": len(hpa_metrics.get("min_replicas", {})),
    }
    
    # Generate output
    output = generate_output(
        cluster_name, env, project, recommendations,
        limitations_text, totals, query_window
    )
    
    # Write output
    output_path = write_output(output, project, env)
    logger.info(f"Wrote analysis to {output_path}")
    
    # Send email notification (placeholder)
    if owner_email and recommendations:
        send_email(
            recipients=owner_email,
            subject=f"[K8s Analysis] {len(recommendations)} recommendations for {cluster_name}",
            body=f"Analysis complete. See {output_path} for details."
        )
    
    return output


def main(config_path: str = "clusters.yaml") -> int:
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Kubernetes Capacity Analysis Tool")
    logger.info("=" * 60)
    
    # Load configuration
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        return 1
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML configuration: {e}")
        return 1
    
    clusters = config.get("clusters", {})
    if not clusters:
        logger.error("No clusters defined in configuration")
        return 1
    
    # Build global config by merging defaults with config file values
    global_config = {
        "settings": {**DEFAULT_CONFIG["settings"], **config.get("settings", {})},
        "pod": {**DEFAULT_CONFIG["pod"], **config.get("pod", {})},
        "memory_buckets_mi": config.get("memory_buckets_mi", DEFAULT_CONFIG["memory_buckets_mi"]),
        "memory_buffer_factor": config.get("memory_buffer_factor", DEFAULT_CONFIG["memory_buffer_factor"]),
        "thresholds": {
            "node": {**DEFAULT_CONFIG["thresholds"]["node"], **config.get("thresholds", {}).get("node", {})},
            "hpa": {**DEFAULT_CONFIG["thresholds"]["hpa"], **config.get("thresholds", {}).get("hpa", {})},
        },
        "limitations_text": config.get("limitations_text", DEFAULT_CONFIG["limitations_text"]),
    }
    
    # Pre-build memory buckets
    global_config["memory_buckets"] = build_memory_buckets(global_config)
    
    logger.info(f"Found {len(clusters)} cluster(s) to analyze")
    logger.info(f"Query window: {global_config['settings']['query_window']}")
    
    # Process each cluster
    success_count = 0
    failed_count = 0
    
    for cluster_name, cluster_config in clusters.items():
        logger.info("-" * 60)
        try:
            # Merge cluster-specific config with global
            cluster_global_config = {**global_config}
            
            # Cluster-specific threshold overrides
            if "thresholds" in cluster_config:
                cluster_global_config["thresholds"] = {
                    "node": {**global_config["thresholds"]["node"], **cluster_config.get("thresholds", {}).get("node", {})},
                    "hpa": {**global_config["thresholds"]["hpa"], **cluster_config.get("thresholds", {}).get("hpa", {})},
                }
            
            analyze_cluster(cluster_name, cluster_config, cluster_global_config)
            success_count += 1
        except Exception as e:
            logger.error(f"Analysis failed for {cluster_name}: {e}")
            failed_count += 1
    
    # Summary
    logger.info("=" * 60)
    logger.info(f"Analysis complete: {success_count} succeeded, {failed_count} failed")
    logger.info("=" * 60)
    
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "clusters.yaml"
    sys.exit(main(config_file))