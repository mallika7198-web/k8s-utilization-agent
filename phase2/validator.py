"""
Phase 2 Insights Validator - Strict validation of LLM output
Ensures insights only contain categories present in Phase 1 data.
No new analysis, no invented data, no safety flag overrides.
"""
from typing import Tuple, List, Dict, Any, Set


# Expected top-level keys in Phase 2 output
EXPECTED_KEYS = {
    'summary',
    'deployment_review',
    'hpa_review', 
    'node_fragmentation_review',
    'cross_layer_risks',
    'limitations'
}

# Nested keys for each review section
DEPLOYMENT_REVIEW_KEYS = {'bursty', 'underutilized', 'memory_pressure', 'unsafe_to_resize'}
HPA_REVIEW_KEYS = {'at_threshold', 'scaling_blocked', 'scaling_down'}
NODE_FRAG_REVIEW_KEYS = {'fragmented_nodes', 'large_request_pods', 'constraint_blockers', 
                         'daemonset_overhead', 'scale_down_blockers'}
CROSS_LAYER_KEYS = {'high', 'medium'}


def _extract_phase1_names(analysis_output: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Extract all valid object names from Phase 1 data"""
    names = {
        'deployments': set(),
        'hpas': set(),
        'nodes': set(),
        'pods': set(),
        'all': set()
    }
    
    # Extract deployment names
    for dep in analysis_output.get('deployment_analysis', []):
        dep_info = dep.get('deployment', {})
        name = dep_info.get('name', '')
        if name:
            names['deployments'].add(name)
            names['all'].add(name)
    
    # Extract HPA names
    for hpa in analysis_output.get('hpa_analysis', []):
        hpa_info = hpa.get('hpa', {})
        name = hpa_info.get('name', '')
        if name:
            names['hpas'].add(name)
            names['all'].add(name)
    
    # Extract node names and pod names from fragmentation attribution
    for node in analysis_output.get('node_analysis', []):
        node_info = node.get('node', {})
        name = node_info.get('name', '')
        if name:
            names['nodes'].add(name)
            names['all'].add(name)
        
        # Extract pods from fragmentation attribution
        frag_attr = node.get('fragmentation_attribution', {})
        if frag_attr:
            for pod in frag_attr.get('large_request_pods', []):
                pod_name = pod.get('pod_name', '')
                if pod_name:
                    names['pods'].add(pod_name)
                    names['all'].add(pod_name)
            
            for blocker in frag_attr.get('constraint_blockers', []):
                pod_name = blocker.get('pod_name', '')
                if pod_name:
                    names['pods'].add(pod_name)
                    names['all'].add(pod_name)
            
            for blocker in frag_attr.get('scale_down_blockers', []):
                pod_name = blocker.get('pod_name', '')
                if pod_name:
                    names['pods'].add(pod_name)
                    names['all'].add(pod_name)
    
    # Extract from cross_layer_observations
    for obs in analysis_output.get('cross_layer_observations', []):
        for comp in obs.get('affected_components', []):
            names['all'].add(comp)
    
    return names


def _extract_name_from_entry(entry: str) -> str:
    """Extract base name from an entry like 'pod-name (reason)'"""
    if '(' in entry:
        return entry.split('(')[0].strip()
    return entry.strip()


def validate_insights_output(
    insights: Any,
    analysis_output: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Validate LLM-generated insights against Phase 1 data
    
    Strict validation rules:
    1. Only expected top-level keys allowed
    2. All referenced objects must exist in Phase 1
    3. Safety flags must be respected (unsafe_to_resize)
    4. Insufficient data must be reflected in limitations
    
    Args:
        insights: LLM-generated insights object
        analysis_output: Phase 1 analysis output for cross-validation
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # 1. Basic type check
    if not isinstance(insights, dict):
        return False, ['Insights must be a JSON object']
    
    # 2. Check for expected keys (at least summary and one review section)
    found_keys = set(insights.keys())
    
    if 'summary' not in found_keys:
        errors.append('Missing required key: summary')
    
    review_keys = {'deployment_review', 'hpa_review', 'node_fragmentation_review', 'cross_layer_risks'}
    if not (found_keys & review_keys):
        errors.append(f'Must have at least one review section: {review_keys}')
    
    # 3. Validate summary is a string
    if 'summary' in insights:
        if not isinstance(insights['summary'], str):
            errors.append('summary must be a string')
        elif len(insights['summary']) > 500:
            errors.append('summary too long (max 500 chars) - should be concise')
    
    # 4. Extract valid names from Phase 1
    valid_names = _extract_phase1_names(analysis_output)
    
    # 5. Validate deployment_review structure and references
    if 'deployment_review' in insights:
        dep_review = insights['deployment_review']
        if not isinstance(dep_review, dict):
            errors.append('deployment_review must be an object')
        else:
            for key in dep_review:
                if key not in DEPLOYMENT_REVIEW_KEYS:
                    errors.append(f'deployment_review.{key} is not a valid category')
                elif not isinstance(dep_review[key], list):
                    errors.append(f'deployment_review.{key} must be an array')
                else:
                    for entry in dep_review[key]:
                        if not isinstance(entry, str):
                            errors.append(f'deployment_review.{key} entries must be strings')
                        else:
                            name = _extract_name_from_entry(entry)
                            if name and name not in valid_names['deployments'] and name not in valid_names['all']:
                                errors.append(f'deployment_review.{key}: "{name}" not found in Phase 1')
    
    # 6. Validate hpa_review structure and references
    if 'hpa_review' in insights:
        hpa_review = insights['hpa_review']
        if not isinstance(hpa_review, dict):
            errors.append('hpa_review must be an object')
        else:
            for key in hpa_review:
                if key not in HPA_REVIEW_KEYS:
                    errors.append(f'hpa_review.{key} is not a valid category')
                elif not isinstance(hpa_review[key], list):
                    errors.append(f'hpa_review.{key} must be an array')
                else:
                    for entry in hpa_review[key]:
                        if not isinstance(entry, str):
                            errors.append(f'hpa_review.{key} entries must be strings')
                        else:
                            name = _extract_name_from_entry(entry)
                            if name and name not in valid_names['hpas'] and name not in valid_names['all']:
                                errors.append(f'hpa_review.{key}: "{name}" not found in Phase 1')
    
    # 7. Validate node_fragmentation_review structure and references
    if 'node_fragmentation_review' in insights:
        node_review = insights['node_fragmentation_review']
        if not isinstance(node_review, dict):
            errors.append('node_fragmentation_review must be an object')
        else:
            for key in node_review:
                if key not in NODE_FRAG_REVIEW_KEYS:
                    errors.append(f'node_fragmentation_review.{key} is not a valid category')
                elif not isinstance(node_review[key], list):
                    errors.append(f'node_fragmentation_review.{key} must be an array')
                else:
                    for entry in node_review[key]:
                        if not isinstance(entry, str):
                            errors.append(f'node_fragmentation_review.{key} entries must be strings')
                        else:
                            name = _extract_name_from_entry(entry)
                            # Allow all Phase 1 names (nodes, pods, etc)
                            if name and name not in valid_names['all']:
                                errors.append(f'node_fragmentation_review.{key}: "{name}" not found in Phase 1')
    
    # 8. Validate cross_layer_risks
    if 'cross_layer_risks' in insights:
        risks = insights['cross_layer_risks']
        if not isinstance(risks, dict):
            errors.append('cross_layer_risks must be an object')
        else:
            for key in risks:
                if key not in CROSS_LAYER_KEYS:
                    errors.append(f'cross_layer_risks.{key} is not a valid category (use high/medium)')
                elif not isinstance(risks[key], list):
                    errors.append(f'cross_layer_risks.{key} must be an array')
    
    # 9. Validate limitations is a list
    if 'limitations' in insights:
        if not isinstance(insights['limitations'], list):
            errors.append('limitations must be an array')
        else:
            for i, lim in enumerate(insights['limitations']):
                if not isinstance(lim, str):
                    errors.append(f'limitations[{i}] must be a string')
    
    # 10. Safety check: unsafe_to_resize deployments should not appear in resize suggestions
    unsafe_deployments = set()
    for dep in analysis_output.get('deployment_analysis', []):
        if dep.get('unsafe_to_resize', False):
            dep_name = dep.get('deployment', {}).get('name', '')
            if dep_name:
                unsafe_deployments.add(dep_name)
    
    # No action_candidates in new format, but check if old format slipped through
    if 'action_candidates' in insights:
        errors.append('action_candidates not allowed - Phase 2 groups facts only, no action suggestions')
    
    # 11. Check insufficient_data is reflected in limitations
    has_insufficient_data = any(
        node.get('insufficient_data', False)
        for node in analysis_output.get('node_analysis', [])
    )
    
    if has_insufficient_data:
        limitations = insights.get('limitations', [])
        if not isinstance(limitations, list) or len(limitations) == 0:
            errors.append('Phase 1 has insufficient_data nodes but limitations is empty')
    
    return len(errors) == 0, errors
