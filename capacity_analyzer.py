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
# Constants
# =============================================================================
PROMETHEUS_TIMEOUT = 30
PROMETHEUS_VERIFY_TLS = False  # Set True for production with valid certs
QUERY_WINDOW = "7d"

# Thresholds
CPU_FLOOR_PROD = 0.1  # 100m
CPU_FLOOR_NONPROD = 0.05  # 50m
SAFETY_FACTOR_PROD = 1.15
SAFETY_FACTOR_NONPROD = 1.10
CPU_REQUEST_MULTIPLIER = 1.20
CPU_LIMIT_REQUEST_MULTIPLIER = 1.50
CPU_LIMIT_P100_MULTIPLIER = 1.25
MEMORY_LIMIT_REQUEST_MULTIPLIER = 1.50
MEMORY_LIMIT_P100_MULTIPLIER = 1.25

# Fragmentation/efficiency thresholds
LOW_EFFICIENCY_THRESHOLD = 0.3
HIGH_FRAGMENTATION_THRESHOLD = 0.5
LOW_CPU_USAGE_RATIO = 0.2  # avg << request
HIGH_MEMORY_PRESSURE_RATIO = 0.9  # memory_p95 ≈ request

# Node recommendation actions (standardized)
NODE_ACTIONS = {
    "down": {
        "action": "DOWNSIZE_NODE",
        "meaning": "Node is underutilized and can be replaced with a smaller instance to reduce cost"
    },
    "right-size": {
        "action": "RIGHT_SIZE_NODE",
        "meaning": "Node has high fragmentation; consider rebalancing workloads or switching to a different instance type"
    },
    "consolidate": {
        "action": "CONSOLIDATE_NODE",
        "meaning": "Workloads can be moved to other nodes; this node may be removable"
    },
    "none": {
        "action": "NO_ACTION",
        "meaning": "Node is healthy and appropriately sized"
    }
}


# =============================================================================
# Configuration Loading
# =============================================================================
def load_config(config_path: str) -> Dict[str, Any]:
    """Load YAML configuration file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def is_prod(env: str) -> bool:
    """Determine if environment is production"""
    return env.lower() == "prod"


# =============================================================================
# Prometheus Client
# =============================================================================
def prometheus_query(prom_url: str, query: str) -> List[Dict[str, Any]]:
    """Execute instant query against Prometheus"""
    try:
        response = requests.get(
            f"{prom_url}/api/v1/query",
            params={"query": query},
            timeout=PROMETHEUS_TIMEOUT,
            verify=PROMETHEUS_VERIFY_TLS
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
def build_promql_queries():
    """Build PromQL queries using configured QUERY_WINDOW
    
    Note: quantile_over_time with subqueries doesn't support 'by' clause directly.
    We wrap with 'sum by' for proper label grouping.
    For CPU, we use rate() inside the subquery which requires a shorter step.
    """
    return {
        # Pod Requests & Limits
        "POD_CPU_REQUESTS": 'sum by (namespace, pod)(kube_pod_container_resource_requests{resource="cpu"})',
        "POD_MEMORY_REQUESTS": 'sum by (namespace, pod)(kube_pod_container_resource_requests{resource="memory"})',
        "POD_CPU_LIMITS": 'sum by (namespace, pod)(kube_pod_container_resource_limits{resource="cpu"})',
        "POD_MEMORY_LIMITS": 'sum by (namespace, pod)(kube_pod_container_resource_limits{resource="memory"})',
        # Pod Usage - CPU Percentiles (from Prometheus)
        # Use sum by() wrapper since quantile_over_time doesn't support 'by' with subqueries
        "POD_CPU_P95": f'sum by (namespace, pod)(quantile_over_time(0.95, rate(container_cpu_usage_seconds_total{{container!=""}}[5m])[{QUERY_WINDOW}:5m]))',
        "POD_CPU_P99": f'sum by (namespace, pod)(quantile_over_time(0.99, rate(container_cpu_usage_seconds_total{{container!=""}}[5m])[{QUERY_WINDOW}:5m]))',
        "POD_CPU_P100": f'sum by (namespace, pod)(max_over_time(rate(container_cpu_usage_seconds_total{{container!=""}}[5m])[{QUERY_WINDOW}:5m]))',
        # Pod Usage - Memory Percentiles (from Prometheus)
        "POD_MEMORY_P95": f'sum by (namespace, pod)(quantile_over_time(0.95, container_memory_working_set_bytes{{container!=""}}[{QUERY_WINDOW}]))',
        "POD_MEMORY_P99": f'sum by (namespace, pod)(quantile_over_time(0.99, container_memory_working_set_bytes{{container!=""}}[{QUERY_WINDOW}]))',
        "POD_MEMORY_P100": f'sum by (namespace, pod)(max_over_time(container_memory_working_set_bytes{{container!=""}}[{QUERY_WINDOW}]))',
    }


class PrometheusQueries:
    """All Prometheus queries as per specification
    
    Note: Percentile queries use QUERY_WINDOW constant for consistency.
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
    
    # Build queries with configured QUERY_WINDOW
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
# Known limitation for Phase-1
MEMORY_PRESSURE_LIMITATION = (
    "CPU reductions do not yet account for node-level memory pressure. "
    "Manual review recommended before applying CPU reduction on memory-constrained nodes."
)


def calculate_pod_resize(
    namespace: str,
    pod: str,
    pod_metrics: Dict[str, Any],
    env: str
) -> Optional[Dict[str, Any]]:
    """Calculate POD_RESIZE recommendation for a single pod
    
    TODO: Add node-level memory pressure check before recommending CPU reduction.
    Design rule: Do NOT reduce CPU if memory is already tight on the node.
    Currently not enforced - see MEMORY_PRESSURE_LIMITATION.
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
    
    # CPU Request: max(cpu_p99 × 1.20, cpu_floor)
    cpu_floor = CPU_FLOOR_PROD if prod else CPU_FLOOR_NONPROD
    cpu_request_new = max(cpu_p99 * CPU_REQUEST_MULTIPLIER, cpu_floor)
    
    # CPU Limit: max(cpu_request_new × 1.50, cpu_p100 × 1.25)
    cpu_limit_new = max(
        cpu_request_new * CPU_LIMIT_REQUEST_MULTIPLIER,
        (cpu_p100 or cpu_p99) * CPU_LIMIT_P100_MULTIPLIER
    )
    
    # Memory Request: memory_p99 × safety_factor
    safety_factor = SAFETY_FACTOR_PROD if prod else SAFETY_FACTOR_NONPROD
    memory_request_new = memory_p99 * safety_factor
    
    # Memory Limit: max(memory_request_new × 1.50, memory_p100 × 1.25)
    memory_limit_new = max(
        memory_request_new * MEMORY_LIMIT_REQUEST_MULTIPLIER,
        (memory_p100 or memory_p99) * MEMORY_LIMIT_P100_MULTIPLIER
    )
    
    # Check if changes are needed (allow 10% tolerance)
    cpu_req_change = abs((cpu_request_new - (cpu_request_current or cpu_request_new)) / max(cpu_request_new, 0.001)) > 0.1
    mem_req_change = abs((memory_request_new - (memory_request_current or memory_request_new)) / max(memory_request_new, 1)) > 0.1
    
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
    exclude_namespaces: List[str] = None
) -> List[Dict[str, Any]]:
    """Generate all POD_RESIZE recommendations
    
    Args:
        pod_metrics: Pod metrics from Prometheus
        env: Environment (prod/nonprod)
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
        rec = calculate_pod_resize(namespace, pod, pod_metrics, env)
        if rec:
            recommendations.append(rec)
    
    return recommendations


# =============================================================================
# NODE_RIGHTSIZE Recommendations
# =============================================================================
def get_pods_on_node(node_name: str, pod_to_node: Dict[Tuple[str, str], str]) -> List[Tuple[str, str]]:
    """Get list of (namespace, pod) tuples scheduled on a specific node
    
    This is CRITICAL for accurate node-scoped calculations.
    Using cluster-wide pod totals would give incorrect fragmentation/efficiency.
    """
    return [pod_key for pod_key, node in pod_to_node.items() if node == node_name]


def calculate_node_rightsize(
    node_name: str,
    node_metrics: Dict[str, Any],
    pod_metrics: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Calculate NODE_RIGHTSIZE recommendation for a single node
    
    IMPORTANT: All pod aggregations are NODE-SCOPED using pod_to_node mapping.
    This fixes the previous bug where cluster-wide totals were incorrectly used.
    
    Formulas (node-scoped):
    - cpu_fragmentation = 1 - (Σ pod_cpu_p95_on_node / Σ pod_cpu_request_on_node)
    - node_efficiency = 0.5 × (Σ pod_cpu_p95_on_node / node_cpu_capacity)
                      + 0.5 × (node_memory_usage / node_memory_capacity)
    """
    
    # Get node capacity
    cpu_allocatable = node_metrics["cpu_allocatable"].get((node_name,))
    memory_allocatable = node_metrics["memory_allocatable"].get((node_name,))
    
    if not cpu_allocatable or not memory_allocatable:
        return None
    
    # Get current node memory usage (not percentile - avoids invalid PromQL)
    node_memory_usage = node_metrics["memory_usage"].get((node_name,), 0)
    
    # Get pod-to-node mapping
    pod_to_node = pod_metrics.get("pod_to_node", {})
    
    # Find all pods scheduled on THIS node
    # This is the CRITICAL fix - we must scope to this node only
    pods_on_node = get_pods_on_node(node_name, pod_to_node)
    
    if not pods_on_node:
        # No pods on node - cannot calculate fragmentation
        return None
    
    # Calculate NODE-SCOPED pod totals (NOT cluster-wide)
    # Sum only requests and usage for pods actually on this node
    total_pod_cpu_request_on_node = sum(
        pod_metrics["cpu_requests"].get(pod_key, 0)
        for pod_key in pods_on_node
    )
    total_pod_cpu_p95_on_node = sum(
        pod_metrics["cpu_p95"].get(pod_key, 0) or 0
        for pod_key in pods_on_node
    )
    total_pod_memory_request_on_node = sum(
        pod_metrics["memory_requests"].get(pod_key, 0)
        for pod_key in pods_on_node
    )
    
    # CPU Fragmentation (node-scoped): 1 - (Σ pod_cpu_p95_on_node / Σ pod_cpu_request_on_node)
    # High fragmentation = requests much higher than actual usage
    cpu_fragmentation = 0
    cpu_fragmentation_undefined = False
    if total_pod_cpu_request_on_node > 0:
        cpu_fragmentation = 1 - (total_pod_cpu_p95_on_node / total_pod_cpu_request_on_node)
        cpu_fragmentation = max(0, min(1, cpu_fragmentation))
    else:
        # Edge case: no CPU requests on node (daemon-only or empty node)
        cpu_fragmentation_undefined = True
    
    # Free Memory (node-scoped)
    free_memory = memory_allocatable - total_pod_memory_request_on_node
    
    # Node Efficiency (node-scoped):
    # 0.5 × (Σ pod_cpu_p95_on_node / node_cpu_capacity) + 0.5 × (node_memory_usage / node_memory_capacity)
    # Uses current memory usage (not percentile) to avoid invalid PromQL
    cpu_efficiency = total_pod_cpu_p95_on_node / cpu_allocatable if cpu_allocatable > 0 else 0
    memory_efficiency = node_memory_usage / memory_allocatable if memory_allocatable > 0 else 0
    node_efficiency = 0.5 * cpu_efficiency + 0.5 * memory_efficiency
    
    # Decision: IF node_efficiency is low AND fragmentation is high → NODE_RIGHTSIZE
    if node_efficiency >= LOW_EFFICIENCY_THRESHOLD or cpu_fragmentation <= HIGH_FRAGMENTATION_THRESHOLD:
        return None
    
    # Determine direction
    if node_efficiency < 0.2:
        direction = "down"
    elif cpu_fragmentation > 0.7:
        direction = "right-size"
    else:
        direction = "down"
    
    # Get standardized recommendation with action and meaning
    recommendation_info = NODE_ACTIONS.get(direction, NODE_ACTIONS["none"])
    
    result = {
        "type": "NODE_RIGHTSIZE",
        "node": node_name,
        "direction": direction,  # Keep for backward compatibility
        "recommendation": {
            "action": recommendation_info["action"],
            "meaning": recommendation_info["meaning"]
        },
        "metrics": {
            "cpu_allocatable": round(cpu_allocatable, 2),
            "memory_allocatable": {
                "bytes": int(memory_allocatable),
                "gb": round(memory_allocatable / (1024 ** 3), 1)
            },
            "cpu_fragmentation": round(cpu_fragmentation, 3) if not cpu_fragmentation_undefined else None,
            "cpu_fragmentation_undefined": cpu_fragmentation_undefined,
            "free_memory": {
                "bytes": int(free_memory),
                "gb": round(free_memory / (1024 ** 3), 1)
            },
            "node_efficiency": round(node_efficiency, 3),
            "pods_on_node": len(pods_on_node),
            "total_pod_cpu_request_on_node": round(total_pod_cpu_request_on_node, 4),
            "total_pod_cpu_p95_on_node": round(total_pod_cpu_p95_on_node, 4),
        },
        "explanation": build_node_rightsize_explanation(
            node_name, direction, cpu_fragmentation, node_efficiency, len(pods_on_node)
        ),
    }
    
    # Add limitation if CPU fragmentation is undefined
    if cpu_fragmentation_undefined:
        result["limitation"] = f"CPU fragmentation undefined on node {node_name} (no CPU requests)"
    
    return result


def build_node_rightsize_explanation(
    node_name: str,
    direction: str,
    fragmentation: float,
    efficiency: float,
    pod_count: int
) -> str:
    """Build explanation for NODE_RIGHTSIZE recommendation"""
    return (
        f"Node {node_name} has low efficiency ({efficiency:.1%}) "
        f"and high CPU fragmentation ({fragmentation:.1%}) "
        f"across {pod_count} pods. "
        f"Recommendation: {direction}. "
        f"Consider consolidating workloads or resizing the node."
    )


def analyze_node_rightsize(
    node_metrics: Dict[str, Any],
    pod_metrics: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate all NODE_RIGHTSIZE recommendations"""
    recommendations = []
    
    for (node_name,) in node_metrics["cpu_allocatable"].keys():
        rec = calculate_node_rightsize(node_name, node_metrics, pod_metrics)
        if rec:
            recommendations.append(rec)
    
    return recommendations


# =============================================================================
# HPA_MISALIGNMENT Detection
# =============================================================================

# Limitation: HPA to pod matching is heuristic
HPA_POD_MATCHING_LIMITATION = (
    "HPA to pod mapping is heuristic and depends on naming conventions. "
    "Pods are matched if the HPA target name is a substring of the pod name."
)


def detect_hpa_misalignment(
    hpa_metrics: Dict[str, Any],
    pod_metrics: Dict[str, Any],
    env: str
) -> List[Dict[str, Any]]:
    """Detect HPA misalignment issues
    
    LIMITATION: HPA target is matched to pods using name substring matching.
    This is a heuristic that depends on standard Kubernetes naming conventions
    (e.g., deployment 'myapp' creates pods 'myapp-xyz-abc').
    """
    recommendations = []
    
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
        
        # Find pods matching this HPA's target
        # NOTE: This is heuristic substring matching - see HPA_POD_MATCHING_LIMITATION
        matching_pods = [
            k for k in pod_metrics["cpu_p95"].keys()
            if k[0] == ns and target_name and target_name in k[1]
        ]
        
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
        
        misalignment_reasons = []
        
        # Rule 1: CPU-based HPA with low CPU usage (avg_cpu_usage << cpu_request)
        if avg_cpu_request > 0 and avg_cpu_usage / avg_cpu_request < LOW_CPU_USAGE_RATIO:
            misalignment_reasons.append(
                f"CPU-based HPA with low CPU usage ({avg_cpu_usage:.3f} cores vs {avg_cpu_request:.3f} request)"
            )
        
        # Rule 2: Memory-bound workload with CPU HPA
        if avg_memory_request > 0 and avg_cpu_request > 0:
            memory_ratio = avg_memory_p95 / avg_memory_request if avg_memory_request > 0 else 0
            cpu_ratio = avg_cpu_usage / avg_cpu_request if avg_cpu_request > 0 else 0
            if memory_ratio > HIGH_MEMORY_PRESSURE_RATIO and cpu_ratio < LOW_CPU_USAGE_RATIO:
                misalignment_reasons.append(
                    f"Memory-bound workload (memory {memory_ratio:.1%} of request) "
                    f"but HPA scales on CPU ({cpu_ratio:.1%} of request)"
                )
        
        # Rule 3: minReplicas blocking consolidation
        if min_replicas > 2 and current_replicas == min_replicas:
            avg_utilization = 0
            if avg_cpu_request > 0:
                avg_utilization = avg_cpu_usage / avg_cpu_request
            if avg_utilization < 0.3:  # Low utilization
                misalignment_reasons.append(
                    f"High minReplicas ({int(min_replicas)}) blocking consolidation "
                    f"with low utilization ({avg_utilization:.1%})"
                )
        
        if misalignment_reasons:
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
                "reasons": misalignment_reasons,
                "explanation": "; ".join(misalignment_reasons),
                "limitation": HPA_POD_MATCHING_LIMITATION,
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
    limitations: List[str],
    totals: Dict[str, int]
) -> Dict[str, Any]:
    """Generate analysis output JSON
    
    Args:
        cluster_name: Name of the cluster being analyzed
        env: Environment (prod/nonprod)
        project: Project identifier
        recommendations: List of all recommendations
        limitations: List of limitation messages
        totals: Dict with total counts of scanned entities (pods, nodes, hpas)
    """
    # Add global limitations
    all_limitations = limitations.copy()
    
    # Check if any POD_RESIZE recommendations exist - add memory pressure limitation
    if any(r["type"] == "POD_RESIZE" for r in recommendations):
        all_limitations.append(MEMORY_PRESSURE_LIMITATION)
    
    # Check for undefined CPU fragmentation in NODE_RIGHTSIZE
    for rec in recommendations:
        if rec["type"] == "NODE_RIGHTSIZE" and rec.get("limitation"):
            all_limitations.append(rec["limitation"])
    
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
        "analysis_window": QUERY_WINDOW,  # e.g., "7d" - how many days of data used
        "recommendations": recommendations,
        "limitations": all_limitations,
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
                "text": f"{node_rightsize_count} out of {total_nodes} nodes show inefficiency" if total_nodes > 0 else "No nodes scanned"
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
    cluster_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Run complete analysis for a single cluster"""
    env = cluster_config.get("env", "nonprod")
    project = cluster_config.get("project", "unknown")
    prom_url = cluster_config.get("prom_url", "http://localhost:9090")
    owner_email = cluster_config.get("owner_email", [])
    exclude_namespaces = cluster_config.get("exclude_namespaces", [])
    
    logger.info(f"Analyzing cluster: {cluster_name} (env={env}, project={project})")
    logger.info(f"Prometheus URL: {prom_url}")
    if exclude_namespaces:
        logger.info(f"Excluding namespaces: {exclude_namespaces}")
    
    limitations = []
    
    # Fetch all metrics
    try:
        pod_metrics = fetch_pod_metrics(prom_url)
        logger.info(f"Fetched metrics for {len(pod_metrics.get('cpu_requests', {}))} pods")
    except Exception as e:
        logger.error(f"Failed to fetch pod metrics: {e}")
        limitations.append(f"Pod metrics unavailable: {e}")
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
        limitations.append(f"Node metrics unavailable: {e}")
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
        limitations.append(f"HPA metrics unavailable: {e}")
        hpa_metrics = {
            "min_replicas": {}, "max_replicas": {},
            "current_replicas": {}, "desired_replicas": {},
            "info": [], "target_metrics": [],
        }
    
    # Generate recommendations
    recommendations = []
    
    # POD_RESIZE
    pod_resize_recs = analyze_pod_resize(pod_metrics, env, exclude_namespaces)
    recommendations.extend(pod_resize_recs)
    logger.info(f"Generated {len(pod_resize_recs)} POD_RESIZE recommendations")
    
    # NODE_RIGHTSIZE
    node_rightsize_recs = analyze_node_rightsize(node_metrics, pod_metrics)
    recommendations.extend(node_rightsize_recs)
    logger.info(f"Generated {len(node_rightsize_recs)} NODE_RIGHTSIZE recommendations")
    
    # HPA_MISALIGNMENT
    hpa_misalignment_recs = detect_hpa_misalignment(hpa_metrics, pod_metrics, env)
    recommendations.extend(hpa_misalignment_recs)
    logger.info(f"Generated {len(hpa_misalignment_recs)} HPA_MISALIGNMENT recommendations")
    
    # Calculate totals for summary (scanned entities, not just affected)
    totals = {
        "pods": len(pod_metrics.get("cpu_requests", {})),
        "nodes": len(node_metrics.get("cpu_allocatable", {})),
        "hpas": len(hpa_metrics.get("min_replicas", {})),
    }
    
    # Generate output
    output = generate_output(cluster_name, env, project, recommendations, limitations, totals)
    
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
    
    logger.info(f"Found {len(clusters)} cluster(s) to analyze")
    
    # Process each cluster
    success_count = 0
    failed_count = 0
    
    for cluster_name, cluster_config in clusters.items():
        logger.info("-" * 60)
        try:
            analyze_cluster(cluster_name, cluster_config)
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
