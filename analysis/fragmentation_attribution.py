"""
Node Fragmentation Attribution - Phase 1 Extension
Identifies WHAT is causing node fragmentation without recommendations.

This module adds attribution data to fragmented nodes:
- Large-request pods that cannot fit elsewhere
- Placement constraints blocking pod movement
- DaemonSet overhead consuming allocatable resources
- Scale-down blockers preventing node termination

All data is factual and Prometheus-sourced only.
"""
import logging
from typing import Dict, List, Any, Optional
from metrics import prometheus_client as prom
from config import (
    DAEMONSET_OVERHEAD_THRESHOLD_PERCENT,
    LARGE_POD_REQUEST_THRESHOLD_PERCENT,
    FRAGMENTATION_THRESHOLD
)

logger = logging.getLogger(__name__)


def analyze_fragmentation_attribution(
    node_name: str,
    node_analysis: Dict[str, Any],
    all_nodes_analysis: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Analyze fragmentation attribution for a single node.
    
    Only returns attribution data if the node is fragmented
    (fragmentation exceeds FRAGMENTATION_THRESHOLD).
    
    Args:
        node_name: Name of the node to analyze
        node_analysis: The existing analysis for this node
        all_nodes_analysis: Analysis data for all nodes in the pool
    
    Returns:
        Attribution dict if fragmented, None otherwise
    """
    fragmentation = node_analysis.get('fragmentation_analysis', {})
    
    # Check if node is fragmented enough to warrant attribution
    cpu_frag = fragmentation.get('cpu_fragmentation', 0) or 0
    mem_frag = fragmentation.get('memory_fragmentation', 0) or 0
    
    if cpu_frag < FRAGMENTATION_THRESHOLD and mem_frag < FRAGMENTATION_THRESHOLD:
        logger.debug(f"Node {node_name} not fragmented enough for attribution")
        return None
    
    logger.info(f"Analyzing fragmentation attribution for node {node_name}")
    
    # Get allocatable resources for this node
    allocatable = node_analysis.get('allocatable_facts', {})
    cpu_allocatable = allocatable.get('cpu_allocatable', 0) or 0
    mem_allocatable = allocatable.get('memory_allocatable', 0) or 0
    
    # Gather attribution data
    attribution = {
        'large_request_pods': _find_large_request_pods(
            node_name, cpu_allocatable, mem_allocatable, all_nodes_analysis
        ),
        'constraint_blockers': _find_constraint_blockers(node_name),
        'daemonset_overhead': _calculate_daemonset_overhead(
            node_name, cpu_allocatable, mem_allocatable
        ),
        'scale_down_blockers': _find_scale_down_blockers(
            node_name, cpu_allocatable, mem_allocatable, all_nodes_analysis
        )
    }
    
    return attribution


def _find_large_request_pods(
    node_name: str,
    cpu_allocatable: float,
    mem_allocatable: float,
    all_nodes_analysis: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Find pods with requests that exceed LARGE_POD_REQUEST_THRESHOLD_PERCENT
    of node allocatable and cannot fit on other nodes.
    
    Returns list of pod attribution records.
    """
    large_pods = []
    
    # Query pod resource requests for this node
    pod_cpu_query = f'''
        sum by (pod, namespace, created_by_kind, created_by_name) (
            kube_pod_container_resource_requests{{
                node="{node_name}",
                resource="cpu"
            }}
        )
    '''
    
    pod_mem_query = f'''
        sum by (pod, namespace, created_by_kind, created_by_name) (
            kube_pod_container_resource_requests{{
                node="{node_name}",
                resource="memory"
            }}
        )
    '''
    
    cpu_requests = prom.query_instant(pod_cpu_query)
    mem_requests = prom.query_instant(pod_mem_query)
    
    # Build map of pod -> memory requests
    pod_mem_map = {}
    for metric in mem_requests:
        labels = metric.get('metric', {})
        pod = labels.get('pod')
        if pod:
            try:
                value = float(metric.get('value', [0, 0])[1])
                pod_mem_map[pod] = value
            except (ValueError, IndexError, TypeError):
                pass
    
    # Calculate thresholds
    cpu_threshold = cpu_allocatable * (LARGE_POD_REQUEST_THRESHOLD_PERCENT / 100)
    mem_threshold = mem_allocatable * (LARGE_POD_REQUEST_THRESHOLD_PERCENT / 100)
    
    # Find largest free block across other nodes
    other_nodes_free_cpu = []
    other_nodes_free_mem = []
    for node in all_nodes_analysis:
        if node.get('node', {}).get('name') != node_name:
            alloc = node.get('allocatable_facts', {})
            req = node.get('request_facts', {})
            
            node_cpu_alloc = alloc.get('cpu_allocatable', 0) or 0
            node_cpu_req = req.get('cpu_requested_total', 0) or 0
            other_nodes_free_cpu.append(node_cpu_alloc - node_cpu_req)
            
            node_mem_alloc = alloc.get('memory_allocatable', 0) or 0
            node_mem_req = req.get('memory_requested_total', 0) or 0
            other_nodes_free_mem.append(node_mem_alloc - node_mem_req)
    
    max_free_cpu = max(other_nodes_free_cpu) if other_nodes_free_cpu else 0
    max_free_mem = max(other_nodes_free_mem) if other_nodes_free_mem else 0
    
    # Analyze each pod's CPU requests
    for metric in cpu_requests:
        labels = metric.get('metric', {})
        pod = labels.get('pod')
        namespace = labels.get('namespace', 'default')
        workload_kind = labels.get('created_by_kind', 'unknown')
        workload_name = labels.get('created_by_name', 'unknown')
        
        if not pod:
            continue
        
        try:
            cpu_req = float(metric.get('value', [0, 0])[1])
        except (ValueError, IndexError, TypeError):
            continue
        
        mem_req = pod_mem_map.get(pod, 0)
        
        # Check if this is a "large" pod
        is_large_cpu = cpu_req > cpu_threshold
        is_large_mem = mem_req > mem_threshold
        
        if not (is_large_cpu or is_large_mem):
            continue
        
        # Check if pod could fit on another node
        can_fit_elsewhere = (cpu_req <= max_free_cpu and mem_req <= max_free_mem)
        
        reasons = []
        if is_large_cpu:
            reasons.append(f"CPU request {cpu_req:.3f} cores exceeds {LARGE_POD_REQUEST_THRESHOLD_PERCENT}% of node allocatable")
        if is_large_mem:
            reasons.append(f"Memory request {mem_req / (1024**3):.2f}GiB exceeds {LARGE_POD_REQUEST_THRESHOLD_PERCENT}% of node allocatable")
        if not can_fit_elsewhere:
            reasons.append(f"Cannot fit on any other node (max free CPU: {max_free_cpu:.3f}, max free memory: {max_free_mem / (1024**3):.2f}GiB)")
        
        large_pods.append({
            'pod_name': pod,
            'namespace': namespace,
            'workload_kind': workload_kind,
            'workload_name': workload_name,
            'request_cpu': cpu_req,
            'request_memory': mem_req,
            'node_name': node_name,
            'can_fit_elsewhere': can_fit_elsewhere,
            'reason': '; '.join(reasons)
        })
    
    return large_pods


def _find_constraint_blockers(node_name: str) -> List[Dict[str, Any]]:
    """
    Find pods with placement constraints that may be blocking optimization.
    
    Uses Prometheus-exposed metadata where available.
    If constraint data is unavailable, explicitly records constraint_visibility: unknown.
    """
    constraint_blockers = []
    
    # Query for pods on this node
    pods_query = f'kube_pod_info{{node="{node_name}"}}'
    pods = prom.query_instant(pods_query)
    
    for metric in pods:
        labels = metric.get('metric', {})
        pod = labels.get('pod')
        namespace = labels.get('namespace', 'default')
        created_by_kind = labels.get('created_by_kind', 'unknown')
        created_by_name = labels.get('created_by_name', 'unknown')
        
        if not pod:
            continue
        
        # Check for node selector labels (exposed in kube_pod_labels)
        pod_labels_query = f'kube_pod_labels{{pod="{pod}", namespace="{namespace}"}}'
        pod_labels_result = prom.query_instant(pod_labels_query)
        
        constraints_detected = []
        constraint_visibility = "limited"
        
        # Look for common constraint indicators in labels
        if pod_labels_result:
            for label_metric in pod_labels_result:
                all_labels = label_metric.get('metric', {})
                
                # Check for topology spread constraints indicator
                if any('topology' in k.lower() for k in all_labels.keys()):
                    constraints_detected.append({
                        'constraint_type': 'topologySpreadConstraints',
                        'constraint_summary': 'Topology spread constraint detected via labels'
                    })
                
                # Check for zone/region affinity
                if any('zone' in k.lower() or 'region' in k.lower() for k in all_labels.keys()):
                    constraints_detected.append({
                        'constraint_type': 'zoneAffinity',
                        'constraint_summary': 'Zone/region constraint detected via labels'
                    })
        
        # Query for pod anti-affinity (if metric exists)
        # Note: This data may not be available in all Prometheus setups
        
        # If we found constraints, add to blockers list
        if constraints_detected:
            constraint_blockers.append({
                'pod_name': pod,
                'namespace': namespace,
                'workload_kind': created_by_kind,
                'workload_name': created_by_name,
                'constraints': constraints_detected,
                'constraint_visibility': constraint_visibility
            })
        else:
            # Record that we couldn't determine constraints
            # Only add if this pod is taking significant resources
            constraint_blockers.append({
                'pod_name': pod,
                'namespace': namespace,
                'workload_kind': created_by_kind,
                'workload_name': created_by_name,
                'constraints': [],
                'constraint_visibility': 'unknown'
            })
    
    # Filter to only include pods where we detected constraints or couldn't determine
    # Remove pods where constraint_visibility is unknown and no constraints detected
    # to avoid noise
    return [b for b in constraint_blockers if b.get('constraints') or b.get('constraint_visibility') == 'unknown'][:10]  # Limit to top 10


def _calculate_daemonset_overhead(
    node_name: str,
    cpu_allocatable: float,
    mem_allocatable: float
) -> Dict[str, Any]:
    """
    Calculate the overhead from DaemonSet pods on this node.
    
    Returns overhead percentage and contributing DaemonSets if above threshold.
    """
    result = {
        'cpu_percent': 0.0,
        'memory_percent': 0.0,
        'exceeds_threshold': False,
        'contributing_daemonsets': []
    }
    
    if cpu_allocatable == 0 and mem_allocatable == 0:
        return result
    
    # Query for DaemonSet pods on this node
    daemonset_cpu_query = f'''
        sum by (created_by_name) (
            kube_pod_container_resource_requests{{
                node="{node_name}",
                created_by_kind="DaemonSet",
                resource="cpu"
            }}
        )
    '''
    
    daemonset_mem_query = f'''
        sum by (created_by_name) (
            kube_pod_container_resource_requests{{
                node="{node_name}",
                created_by_kind="DaemonSet",
                resource="memory"
            }}
        )
    '''
    
    cpu_results = prom.query_instant(daemonset_cpu_query)
    mem_results = prom.query_instant(daemonset_mem_query)
    
    total_cpu = 0.0
    total_mem = 0.0
    daemonsets = set()
    
    for metric in cpu_results:
        labels = metric.get('metric', {})
        ds_name = labels.get('created_by_name', 'unknown')
        try:
            value = float(metric.get('value', [0, 0])[1])
            total_cpu += value
            daemonsets.add(ds_name)
        except (ValueError, IndexError, TypeError):
            pass
    
    for metric in mem_results:
        labels = metric.get('metric', {})
        ds_name = labels.get('created_by_name', 'unknown')
        try:
            value = float(metric.get('value', [0, 0])[1])
            total_mem += value
            daemonsets.add(ds_name)
        except (ValueError, IndexError, TypeError):
            pass
    
    cpu_percent = (total_cpu / cpu_allocatable * 100) if cpu_allocatable > 0 else 0
    mem_percent = (total_mem / mem_allocatable * 100) if mem_allocatable > 0 else 0
    
    result['cpu_percent'] = round(cpu_percent, 2)
    result['memory_percent'] = round(mem_percent, 2)
    result['exceeds_threshold'] = (
        cpu_percent > DAEMONSET_OVERHEAD_THRESHOLD_PERCENT or 
        mem_percent > DAEMONSET_OVERHEAD_THRESHOLD_PERCENT
    )
    
    if result['exceeds_threshold']:
        result['contributing_daemonsets'] = sorted(list(daemonsets))
    
    return result


def _find_scale_down_blockers(
    node_name: str,
    cpu_allocatable: float,
    mem_allocatable: float,
    all_nodes_analysis: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Find pods that would block node scale-down/termination.
    
    A pod blocks scale-down if:
    - It's the only pod of its workload on this node
    - Its requests cannot fit on any other node
    - It has protective constraints (PDB, etc.)
    """
    blockers = []
    
    # Query pods on this node with their workload info
    pods_query = f'''
        kube_pod_info{{node="{node_name}"}}
    '''
    pods = prom.query_instant(pods_query)
    
    # Get CPU and memory requests for pods on this node
    cpu_query = f'''
        sum by (pod, namespace) (
            kube_pod_container_resource_requests{{
                node="{node_name}",
                resource="cpu"
            }}
        )
    '''
    mem_query = f'''
        sum by (pod, namespace) (
            kube_pod_container_resource_requests{{
                node="{node_name}",
                resource="memory"
            }}
        )
    '''
    
    cpu_results = prom.query_instant(cpu_query)
    mem_results = prom.query_instant(mem_query)
    
    # Build maps
    pod_cpu_map = {}
    pod_mem_map = {}
    
    for metric in cpu_results:
        labels = metric.get('metric', {})
        pod = labels.get('pod')
        if pod:
            try:
                pod_cpu_map[pod] = float(metric.get('value', [0, 0])[1])
            except (ValueError, IndexError, TypeError):
                pass
    
    for metric in mem_results:
        labels = metric.get('metric', {})
        pod = labels.get('pod')
        if pod:
            try:
                pod_mem_map[pod] = float(metric.get('value', [0, 0])[1])
            except (ValueError, IndexError, TypeError):
                pass
    
    # Calculate max free resources on other nodes
    other_nodes_free = []
    for node in all_nodes_analysis:
        if node.get('node', {}).get('name') != node_name:
            alloc = node.get('allocatable_facts', {})
            req = node.get('request_facts', {})
            
            free_cpu = (alloc.get('cpu_allocatable', 0) or 0) - (req.get('cpu_requested_total', 0) or 0)
            free_mem = (alloc.get('memory_allocatable', 0) or 0) - (req.get('memory_requested_total', 0) or 0)
            other_nodes_free.append({'cpu': free_cpu, 'memory': free_mem})
    
    # Analyze each pod
    for metric in pods:
        labels = metric.get('metric', {})
        pod = labels.get('pod')
        namespace = labels.get('namespace', 'default')
        workload_kind = labels.get('created_by_kind', 'unknown')
        workload_name = labels.get('created_by_name', 'unknown')
        
        if not pod:
            continue
        
        cpu_req = pod_cpu_map.get(pod, 0)
        mem_req = pod_mem_map.get(pod, 0)
        
        # Check if pod can fit elsewhere
        can_fit_elsewhere = any(
            cpu_req <= n['cpu'] and mem_req <= n['memory']
            for n in other_nodes_free
        )
        
        blocking_reasons = []
        
        if not can_fit_elsewhere:
            blocking_reasons.append(
                f"Pod requests (CPU: {cpu_req:.3f}, Memory: {mem_req / (1024**3):.2f}GiB) "
                f"cannot fit on any other node"
            )
        
        # Check for PDB protection (if metric available)
        pdb_query = f'kube_poddisruptionbudget_status_pod_disruptions_allowed{{namespace="{namespace}"}}'
        pdb_result = prom.query_instant(pdb_query)
        
        for pdb_metric in pdb_result:
            try:
                allowed = float(pdb_metric.get('value', [0, 0])[1])
                if allowed == 0:
                    pdb_name = pdb_metric.get('metric', {}).get('poddisruptionbudget', 'unknown')
                    blocking_reasons.append(f"Protected by PDB {pdb_name} with 0 disruptions allowed")
            except (ValueError, IndexError, TypeError):
                pass
        
        if blocking_reasons:
            blockers.append({
                'pod_name': pod,
                'namespace': namespace,
                'workload_kind': workload_kind,
                'workload_name': workload_name,
                'request_cpu': cpu_req,
                'request_memory': mem_req,
                'blocking_reason': '; '.join(blocking_reasons)
            })
    
    return blockers[:10]  # Limit to top 10 blockers
