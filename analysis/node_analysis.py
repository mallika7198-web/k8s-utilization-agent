"""
Node analysis - Phase 1 (Facts only, deterministic)
Analyzes node capacity, allocatable resources, and pod scheduling
"""
from metrics import prometheus_client as prom


def analyze_nodes(nodes):
    """Analyze nodes for resource allocation and scheduling
    
    Returns list of node analysis objects with:
    - capacity_facts: Total CPU, memory, storage
    - allocatable_facts: Available resources for pod scheduling
    - utilization_facts: Current usage across node
    - fragmentation_analysis: Pod distribution and packing efficiency
    """
    analysis = []
    
    for node in nodes:
        name = node.get('name', 'unknown')
        
        # Get node metrics
        pod_count = prom.query_instant(
            f'count(kube_pod_info{{node="{name}"}}) by (node)'
        )
        node_cpu_usage = prom.query_range(
            f'rate(node_cpu_seconds_total{{node="{name}"}}[5m])'
        )
        node_memory_usage = prom.query_range(
            f'node_memory_MemAvailable_bytes{{node="{name}"}}'
        )
        
        pod_count_val = _extract_value(pod_count)
        
        analysis.append({
            'node': {
                'name': name,
                'labels': node.get('labels', {})
            },
            'insufficient_data': pod_count_val is None,
            'evidence': _build_node_evidence(name, pod_count_val),
            'capacity_facts': {
                'cpu_cores': None,
                'memory_bytes': None,
                'ephemeral_storage_bytes': None,
                'pods_max': 110
            },
            'allocatable_facts': {
                'cpu_allocatable': None,
                'memory_allocatable': None,
                'pods_allocatable': 110
            },
            'request_facts': {
                'cpu_requested_total': None,
                'memory_requested_total': None,
                'pods_requested_count': pod_count_val or 0
            },
            'utilization_facts': {
                'cpu_usage_cores': _compute_avg_from_range(node_cpu_usage),
                'memory_available_bytes': _extract_value(node_memory_usage) if node_memory_usage else None,
                'pod_count': pod_count_val or 0
            },
            'fragmentation_analysis': {
                'pod_packing_efficiency': None,
                'memory_fragmentation': None,
                'cpu_fragmentation': None
            },
            'scheduling_facts': _analyze_scheduling(name, pod_count_val),
            'node_conditions': {
                'ready': True,
                'memory_pressure': False,
                'disk_pressure': False,
                'pid_pressure': False
            }
        })
    
    return analysis


def _analyze_scheduling(node_name, pod_count):
    """Analyze scheduling health for a node"""
    conditions = {}
    
    if pod_count is None:
        conditions['pod_count_unknown'] = True
    elif pod_count == 0:
        conditions['no_pods_scheduled'] = True
    elif pod_count > 100:
        conditions['high_pod_density'] = f'{pod_count} pods > 100 threshold'
    
    return conditions


def _build_node_evidence(name, pod_count):
    """Build evidence statements about node"""
    evidence = []
    
    if pod_count is None:
        evidence.append(f'Unable to determine pod count for node {name}')
    else:
        evidence.append(f'Node {name} has {pod_count} pods scheduled')
    
    return evidence


def _extract_value(metric_result):
    """Extract numeric value from Prometheus metric result"""
    if not metric_result or len(metric_result) == 0:
        return None
    
    try:
        value = metric_result[0].get('value', [None, None])[1]
        return float(value) if value else None
    except (ValueError, IndexError, TypeError, KeyError):
        return None


def _compute_avg_from_range(data):
    """Compute average from range query result"""
    if not data:
        return None
    
    total = 0
    count = 0
    
    for metric in data:
        vals = metric.get('values', [])
        for val in vals:
            try:
                total += float(val[1])
                count += 1
            except (ValueError, IndexError, TypeError):
                pass
    
    return total / max(count, 1) if count > 0 else None
