"""
Node analysis - Phase 1 (Facts only, deterministic)
Analyzes node capacity, allocatable resources, and pod scheduling
"""
import logging
from typing import List, Dict, Any
from metrics import prometheus_client as prom
from config import FRAGMENTATION_THRESHOLD

logger = logging.getLogger(__name__)


def analyze_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Analyze nodes for resource allocation and scheduling
    
    Returns list of node analysis objects with:
    - capacity_facts: Total CPU, memory, storage
    - allocatable_facts: Available resources for pod scheduling
    - utilization_facts: Current usage across node
    - fragmentation_analysis: Pod distribution and packing efficiency
    - fragmentation_attribution: (if fragmented) What is causing fragmentation
    """
    analysis = []
    
    for node in nodes:
        name = node.get('name', 'unknown')
        
        # Get node metrics
        pod_count = prom.query_instant(
            f'count(kube_pod_info{{node="{name}"}}) by (node)'
        )
        node_cpu_usage = prom.query_range(
            f'sum(rate(node_cpu_seconds_total{{mode!="idle",instance=~".*"}}[5m]))'
        )
        node_memory_avail = prom.query_instant(
            f'node_memory_MemAvailable_bytes'
        )
        node_memory_total = prom.query_instant(
            f'node_memory_MemTotal_bytes'
        )
        
        # Get allocatable from kube-state-metrics
        cpu_allocatable = prom.query_instant(
            f'kube_node_status_allocatable{{node="{name}",resource="cpu"}}'
        )
        memory_allocatable = prom.query_instant(
            f'kube_node_status_allocatable{{node="{name}",resource="memory"}}'
        )
        pods_allocatable = prom.query_instant(
            f'kube_node_status_allocatable{{node="{name}",resource="pods"}}'
        )
        
        # Get capacity from kube-state-metrics
        cpu_capacity = prom.query_instant(
            f'kube_node_status_capacity{{node="{name}",resource="cpu"}}'
        )
        memory_capacity = prom.query_instant(
            f'kube_node_status_capacity{{node="{name}",resource="memory"}}'
        )
        pods_capacity = prom.query_instant(
            f'kube_node_status_capacity{{node="{name}",resource="pods"}}'
        )
        
        # Get requests from pods on this node
        cpu_requests = prom.query_instant(
            f'sum(kube_pod_container_resource_requests{{node="{name}",resource="cpu"}})'
        )
        memory_requests = prom.query_instant(
            f'sum(kube_pod_container_resource_requests{{node="{name}",resource="memory"}})'
        )
        
        # Get node conditions
        node_ready = prom.query_instant(
            f'kube_node_status_condition{{node="{name}",condition="Ready",status="true"}}'
        )
        memory_pressure = prom.query_instant(
            f'kube_node_status_condition{{node="{name}",condition="MemoryPressure",status="true"}}'
        )
        disk_pressure = prom.query_instant(
            f'kube_node_status_condition{{node="{name}",condition="DiskPressure",status="true"}}'
        )
        pid_pressure = prom.query_instant(
            f'kube_node_status_condition{{node="{name}",condition="PIDPressure",status="true"}}'
        )
        
        pod_count_val = _extract_value(pod_count)
        cpu_alloc_val = _extract_value(cpu_allocatable)
        mem_alloc_val = _extract_value(memory_allocatable)
        pods_alloc_val = _extract_value(pods_allocatable)
        cpu_cap_val = _extract_value(cpu_capacity)
        mem_cap_val = _extract_value(memory_capacity)
        pods_cap_val = _extract_value(pods_capacity)
        cpu_req_val = _extract_value(cpu_requests)
        mem_req_val = _extract_value(memory_requests)
        mem_avail_val = _extract_value(node_memory_avail)
        mem_total_val = _extract_value(node_memory_total)
        
        # Compute CPU usage from rate
        cpu_usage_val = _compute_avg_from_range(node_cpu_usage)
        
        # Compute memory usage from total - available
        mem_usage_val = None
        if mem_total_val and mem_avail_val:
            mem_usage_val = mem_total_val - mem_avail_val
        
        # Compute fragmentation metrics
        cpu_frag = None
        mem_frag = None
        packing_eff = None
        
        if cpu_alloc_val and cpu_req_val:
            # Fragmentation = (allocatable - requested) / allocatable
            # High fragmentation = lots of unused allocatable capacity
            cpu_frag = max(0, (cpu_alloc_val - cpu_req_val) / cpu_alloc_val) if cpu_alloc_val > 0 else None
        
        if mem_alloc_val and mem_req_val:
            mem_frag = max(0, (mem_alloc_val - mem_req_val) / mem_alloc_val) if mem_alloc_val > 0 else None
        
        if pods_alloc_val and pod_count_val:
            packing_eff = pod_count_val / pods_alloc_val if pods_alloc_val > 0 else None
        
        node_analysis = {
            'node': {
                'name': name,
                'labels': node.get('labels', {})
            },
            'insufficient_data': cpu_alloc_val is None and mem_alloc_val is None,
            'evidence': _build_node_evidence(name, pod_count_val, cpu_alloc_val, mem_alloc_val),
            'capacity_facts': {
                'cpu_cores': cpu_cap_val,
                'memory_bytes': mem_cap_val,
                'ephemeral_storage_bytes': None,
                'pods_max': int(pods_cap_val) if pods_cap_val else 110
            },
            'allocatable_facts': {
                'cpu_allocatable': cpu_alloc_val,
                'memory_allocatable': mem_alloc_val,
                'pods_allocatable': int(pods_alloc_val) if pods_alloc_val else 110
            },
            'request_facts': {
                'cpu_requested_total': cpu_req_val,
                'memory_requested_total': mem_req_val,
                'pods_requested_count': pod_count_val or 0
            },
            'utilization_facts': {
                'cpu_usage_cores': cpu_usage_val,
                'memory_usage_bytes': mem_usage_val,
                'memory_available_bytes': mem_avail_val,
                'pod_count': pod_count_val or 0
            },
            'fragmentation_analysis': {
                'pod_packing_efficiency': packing_eff,
                'memory_fragmentation': mem_frag,
                'cpu_fragmentation': cpu_frag
            },
            'scheduling_facts': _analyze_scheduling(name, pod_count_val),
            'node_conditions': {
                'ready': _extract_value(node_ready) == 1,
                'memory_pressure': _extract_value(memory_pressure) == 1,
                'disk_pressure': _extract_value(disk_pressure) == 1,
                'pid_pressure': _extract_value(pid_pressure) == 1
            }
        }
        
        analysis.append(node_analysis)
    
    # Second pass: Add fragmentation attribution for fragmented nodes
    _add_fragmentation_attribution(analysis)
    
    return analysis


def _add_fragmentation_attribution(all_nodes_analysis: List[Dict[str, Any]]) -> None:
    """
    Add fragmentation_attribution to nodes that are fragmented.
    
    This is a second pass that runs after all nodes have basic analysis,
    because attribution needs cross-node comparison.
    """
    from analysis.fragmentation_attribution import analyze_fragmentation_attribution
    
    for node_analysis in all_nodes_analysis:
        node_name = node_analysis.get('node', {}).get('name', 'unknown')
        fragmentation = node_analysis.get('fragmentation_analysis', {})
        
        cpu_frag = fragmentation.get('cpu_fragmentation', 0) or 0
        mem_frag = fragmentation.get('memory_fragmentation', 0) or 0
        
        # Only add attribution if node is fragmented
        if cpu_frag >= FRAGMENTATION_THRESHOLD or mem_frag >= FRAGMENTATION_THRESHOLD:
            logger.info(f"Node {node_name} is fragmented, computing attribution")
            attribution = analyze_fragmentation_attribution(
                node_name,
                node_analysis,
                all_nodes_analysis
            )
            if attribution:
                node_analysis['fragmentation_attribution'] = attribution


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


def _build_node_evidence(name, pod_count, cpu_alloc, mem_alloc):
    """Build evidence statements about node"""
    evidence = []
    
    if pod_count is None:
        evidence.append(f'Unable to determine pod count for node {name}')
    else:
        evidence.append(f'Node {name} has {pod_count} pods scheduled')
    
    if cpu_alloc:
        evidence.append(f'CPU allocatable: {cpu_alloc} cores')
    
    if mem_alloc:
        mem_gb = mem_alloc / (1024**3)
        evidence.append(f'Memory allocatable: {mem_gb:.2f} GiB')
    
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
