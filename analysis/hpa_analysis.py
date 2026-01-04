"""
HPA analysis - Phase 1 (Facts only, deterministic)
Analyzes horizontal pod autoscaler configuration and scaling behavior
"""
from metrics import prometheus_client as prom


def analyze_hpas(hpas):
    """Analyze HPAs for scaling behavior and configuration
    
    Returns list of HPA analysis objects with:
    - hpa_config_facts: Min/max replicas, target metrics
    - scaling_behavior: Current replica count, scaling events
    - linked_resource_facts: Which deployment/statefulset is targeted
    - analysis_flags: Unusual scaling patterns or misconfigurations
    """
    analysis = []
    
    for hpa in hpas:
        name = hpa.get('name', 'unknown')
        namespace = hpa.get('namespace', 'default')
        
        # Get HPA status and configuration - use correct metric name
        current_replicas = prom.query_instant(
            f'kube_horizontalpodautoscaler_status_current_replicas{{horizontalpodautoscaler="{name}",namespace="{namespace}"}}'
        )
        desired_replicas = prom.query_instant(
            f'kube_horizontalpodautoscaler_status_desired_replicas{{horizontalpodautoscaler="{name}",namespace="{namespace}"}}'
        )
        
        current_val = _extract_value(current_replicas)
        desired_val = _extract_value(desired_replicas)
        
        min_replicas = hpa.get('min_replicas', 1)
        max_replicas = hpa.get('max_replicas', 10)
        
        # Get target info from Prometheus
        target_info = prom.query_instant(
            f'kube_horizontalpodautoscaler_info{{horizontalpodautoscaler="{name}",namespace="{namespace}"}}'
        )
        target_kind = 'Deployment'
        target_name = None
        if target_info:
            labels = target_info[0].get('metric', {})
            target_kind = labels.get('scaletargetref_kind', 'Deployment')
            target_name = labels.get('scaletargetref_name')
        
        # Detect scaling issues
        flags = _compute_hpa_flags(current_val, desired_val, min_replicas, max_replicas)
        
        analysis.append({
            'hpa_name': name,
            'hpa_namespace': namespace,
            'hpa_enabled': True,
            'insufficient_data': current_val is None or desired_val is None,
            'evidence': _build_hpa_evidence(name, current_val, desired_val),
            'hpa_config_facts': {
                'min_replicas': min_replicas,
                'max_replicas': max_replicas,
                'metric_type': 'cpu',
                'target_utilization': None
            },
            'scaling_behavior': {
                'current_replicas': current_val or 0,
                'desired_replicas': desired_val or 0,
                'at_min': (current_val or 0) == min_replicas,
                'at_max': (current_val or 0) == max_replicas,
                'scaling_up_events': 0,
                'scaling_down_events': 0
            },
            'linked_resource_facts': {
                'target_kind': target_kind,
                'target_name': target_name
            },
            'analysis_flags': flags,
            'safety_classification': _classify_hpa_safety(flags)
        })
    
    return analysis


def _compute_hpa_flags(current, desired, min_replicas, max_replicas):
    """Determine scaling behavior flags"""
    flags = []
    
    if current is None or desired is None:
        flags.append('INSUFFICIENT_DATA')
        return flags
    
    # Stuck scaling
    if current != desired:
        if desired > max_replicas:
            flags.append('SCALING_BEYOND_MAX')
        elif desired < min_replicas:
            flags.append('SCALING_BELOW_MIN')
        elif current < desired:
            flags.append('SCALING_UP_PENDING')
        elif current > desired:
            flags.append('SCALING_DOWN_IN_PROGRESS')
    
    # At capacity
    if current == max_replicas:
        flags.append('AT_MAX_REPLICAS')
    
    if current == min_replicas:
        flags.append('AT_MIN_REPLICAS')
    
    # Configuration issues
    if min_replicas > max_replicas:
        flags.append('INVALID_CONFIG_MIN_GT_MAX')
    
    if max_replicas - min_replicas < 2:
        flags.append('LIMITED_SCALING_RANGE')
    
    return flags


def _build_hpa_evidence(name, current, desired):
    """Build evidence statements about HPA"""
    evidence = []
    
    if current is None:
        evidence.append(f'Unable to determine current replica count for HPA {name}')
    else:
        evidence.append(f'HPA {name} currently has {current} replicas')
    
    if desired is None:
        evidence.append(f'Unable to determine desired replica count for HPA {name}')
    elif desired != current:
        evidence.append(f'HPA {name} desires {desired} replicas (currently {current})')
    
    return evidence


def _classify_hpa_safety(flags):
    """Classify HPA safety level based on flags"""
    if any('INVALID_CONFIG' in f or 'INSUFFICIENT_DATA' in f for f in flags):
        return 'UNSAFE'
    elif any('PENDING' in f or 'STUCK' in f for f in flags):
        return 'DEGRADED'
    elif len(flags) == 0:
        return 'HEALTHY'
    else:
        return 'CAUTION'


def _extract_value(metric_result):
    """Extract numeric value from Prometheus metric result"""
    if not metric_result or len(metric_result) == 0:
        return None
    
    try:
        value = metric_result[0].get('value', [None, None])[1]
        return int(float(value)) if value else None
    except (ValueError, IndexError, TypeError, KeyError):
        return None
