"""
Deployment analysis - Phase 1 (Facts only, deterministic)
Analyzes CPU, memory, replica counts, and scheduling behavior
"""
from metrics import prometheus_client as prom


def analyze_deployments(deployments):
    """Analyze deployments for resource usage patterns and scheduling behavior
    
    Returns list of deployment analysis objects with:
    - resource_facts: CPU/memory usage statistics (avg, p95, p99, p100)
    - behavior_flags: Idle, overprovisioned, bursty, etc.
    - scheduling_facts: Replica counts, request/limit configuration
    - edge_cases: Unusual patterns or constraints
    """
    analysis = []
    
    for dep in deployments:
        name = dep['name']
        namespace = dep['namespace']
        replicas = dep.get('replicas', 1)
        
        # Query metrics for this deployment
        cpu_data = prom.query_range(
            f'rate(container_cpu_usage_seconds_total{{pod=~".*{name}.*",namespace="{namespace}"}}[5m])'
        )
        memory_data = prom.query_range(
            f'container_memory_usage_bytes{{pod=~".*{name}.*",namespace="{namespace}"}}'
        )
        
        # Pod count
        pod_count = prom.query_instant(
            f'count(kube_pod_info{{pod=~".*{name}.*",namespace="{namespace}"}}) by ()'
        )
        pod_count_val = int(float(pod_count[0]['value'][1])) if pod_count else 0
        
        # Extract resource statistics
        cpu_avg = _compute_avg(cpu_data)
        cpu_p95, cpu_p99, cpu_p100 = _compute_percentiles(cpu_data, [0.95, 0.99, 1.0])
        
        mem_avg = _compute_avg(memory_data)
        mem_p95, mem_p99, mem_p100 = _compute_percentiles(memory_data, [0.95, 0.99, 1.0])
        
        # Compute utilization flags
        flags = _compute_behavior_flags(
            cpu_avg, cpu_p95, cpu_p99, cpu_p100,
            mem_avg, mem_p95, mem_p99, mem_p100,
            replicas, pod_count_val
        )
        
        analysis.append({
            'deployment': {
                'name': name,
                'namespace': namespace,
                'replicas': replicas,
                'desired_replicas': replicas
            },
            'insufficient_data': len(cpu_data) == 0 and len(memory_data) == 0,
            'evidence': _build_evidence(name, len(cpu_data), len(memory_data), pod_count_val),
            'resource_facts': {
                'cpu_avg_cores': round(cpu_avg, 4),
                'cpu_p95_cores': round(cpu_p95, 4),
                'cpu_p99_cores': round(cpu_p99, 4),
                'cpu_p100_cores': round(cpu_p100, 4),
                'memory_avg_bytes': int(mem_avg),
                'memory_p95_bytes': int(mem_p95),
                'memory_p99_bytes': int(mem_p99),
                'memory_p100_bytes': int(mem_p100),
                'pod_count': pod_count_val
            },
            'derived_metrics': {
                'cpu_per_pod': round(cpu_avg / max(pod_count_val, 1), 4),
                'memory_per_pod': int(mem_avg / max(pod_count_val, 1)),
                'replica_efficiency': round(pod_count_val / max(replicas, 1), 2)
            },
            'behavior_flags': flags,
            'scheduling_facts': {
                'scheduler_healthy': pod_count_val > 0 if replicas > 0 else True,
                'pod_disruption_budgets': None,
                'affinity_rules': None
            },
            'edge_cases': _detect_edge_cases(replicas, pod_count_val, cpu_avg, mem_avg)
        })
    
    return analysis


def _compute_behavior_flags(cpu_avg, cpu_p95, cpu_p99, cpu_p100, mem_avg, mem_p95, mem_p99, mem_p100, replicas, pod_count):
    """Determine behavioral flags based on resource usage patterns"""
    flags = []
    
    # Idle detection: all metrics near zero
    if cpu_avg < 0.001 and mem_avg < 10_000_000:  # < 1m CPU, < 10MB memory
        flags.append('IDLE')
    
    # Overprovisioned: p99 far below p100
    if cpu_p99 > 0 and cpu_p100 / max(cpu_p99, 0.0001) > 2.0:
        flags.append('CPU_BURSTY')
    if mem_p99 > 0 and mem_p100 / max(mem_p99, 1) > 2.0:
        flags.append('MEMORY_BURSTY')
    
    # Underutilized: low average usage
    if cpu_avg < 0.1 and replicas > 1:
        flags.append('CPU_UNDERUTILIZED')
    if mem_avg < 100_000_000 and replicas > 1:  # < 100MB
        flags.append('MEMORY_UNDERUTILIZED')
    
    # Replica mismatch
    if pod_count < replicas:
        flags.append('PENDING_PODS')
    elif pod_count > replicas:
        flags.append('EXTRA_PODS')
    
    return flags


def _detect_edge_cases(replicas, pod_count, cpu_avg, mem_avg):
    """Detect unusual or edge case configurations"""
    cases = {}
    
    if replicas == 1:
        cases['single_replica'] = 'No high availability'
    
    if replicas == 0 and pod_count > 0:
        cases['zero_replicas_with_pods'] = f'{pod_count} pods running with 0 replicas'
    
    if replicas > 0 and pod_count == 0:
        cases['no_running_pods'] = 'Deployment scaled to 0 or unable to schedule'
    
    if cpu_avg > 2.0:  # 2 full cores on average
        cases['high_cpu_usage'] = f'{cpu_avg:.2f} cores average'
    
    if mem_avg > 1_000_000_000:  # > 1GB
        cases['high_memory_usage'] = f'{mem_avg / 1_000_000_000:.1f}GB average'
    
    return cases


def _build_evidence(name, cpu_count, mem_count, pod_count):
    """Build list of evidence statements"""
    evidence = []
    
    if pod_count == 0:
        evidence.append(f'No pods currently running for deployment {name}')
    else:
        evidence.append(f'{pod_count} pod(s) found for deployment {name}')
    
    if cpu_count == 0:
        evidence.append('CPU metrics not available in Prometheus')
    else:
        evidence.append(f'{cpu_count} CPU metric points collected')
    
    if mem_count == 0:
        evidence.append('Memory metrics not available in Prometheus')
    else:
        evidence.append(f'{mem_count} memory metric points collected')
    
    return evidence


def _compute_percentiles(data, percentiles):
    """Compute percentiles from metric data
    
    Args:
        data: List of metric objects with 'values' key
        percentiles: List of percentile values (0.0-1.0)
    
    Returns:
        List of percentile values in same order as input
    """
    if not data:
        return [0] * len(percentiles)
    
    values = []
    for metric in data:
        vals = metric.get('values', [])
        for val in vals:
            try:
                values.append(float(val[1]))
            except (ValueError, IndexError, TypeError):
                pass
    
    if not values:
        return [0] * len(percentiles)
    
    values.sort()
    result = []
    for p in percentiles:
        idx = int(len(values) * p)
        result.append(values[min(idx, len(values) - 1)])
    
    return result


def _compute_avg(data):
    """Compute average from metric data
    
    Args:
        data: List of metric objects with 'values' key
    
    Returns:
        Average value, or 0 if no data
    """
    if not data:
        return 0
    
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
    
    return total / max(count, 1)
    
    return total / count if count > 0 else 0
