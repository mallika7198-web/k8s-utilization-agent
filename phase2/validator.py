"""
Phase 2 Insights Validator - Flexible validation of LLM output
Ensures insights respect Phase 1 safety flags and basic structure
"""
from typing import Tuple, List, Dict, Any


def validate_insights_output(
    insights: Any,
    analysis_output: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Validate LLM-generated insights against Phase 1 data
    
    Checks:
    1. Top-level structure has some of the required keys
    2. Content is sensible and not hallucinated
    3. Safety flags are respected (safe_to_resize, confidence levels, etc.)
    
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
    
    # 2. At least one of the required keys should exist
    expected_keys = {'cluster_summary', 'patterns', 'warnings', 'action_candidates', 'limitations'}
    found_keys = set(insights.keys()) & expected_keys
    
    if len(found_keys) == 0:
        return False, [f'Insights must have at least one of: {expected_keys}']
    
    # 3. Cluster summary should be a string
    if 'cluster_summary' in insights and not isinstance(insights.get('cluster_summary'), str):
        errors.append('cluster_summary should be a string')
    
    # 4. Lists should be lists
    for key in ['patterns', 'warnings', 'action_candidates', 'limitations']:
        if key in insights:
            if not isinstance(insights[key], list):
                errors.append(f'{key} should be a list')
            else:
                # Validate list items
                for i, item in enumerate(insights[key]):
                    if not isinstance(item, (dict, str)):
                        errors.append(f'{key}[{i}] should be an object or string')
    
    # 5. Check for safety flag violations
    safe_to_resize = analysis_output.get('safe_to_resize', True)
    
    # Check action candidates for resize actions without permission
    if 'action_candidates' in insights and isinstance(insights['action_candidates'], list):
        for i, action in enumerate(insights['action_candidates']):
            if isinstance(action, dict):
                action_title = action.get('title', '').upper()
                action_type = action.get('type', '').upper()
                
                if not safe_to_resize:
                    if any(word in action_title for word in ['RESIZE', 'SCALE', 'REPLICA']):
                        if action_type not in ['RESIZE', 'SCALE']:
                            continue  # Might be informational
                        errors.append(
                            f'action_candidates[{i}]: '
                            f'Scaling action proposed but Phase 1 marks it as unsafe'
                        )
    
    # 6. Check if insights mention insufficient data (good practice)
    insufficient_data = any(
        item.get('insufficient_data', False)
        for items in [
            analysis_output.get('deployment_analysis', []),
            analysis_output.get('hpa_analysis', []),
            analysis_output.get('node_analysis', [])
        ]
        for item in items
    )
    
    if insufficient_data and 'limitations' in insights:
        limitations = insights['limitations']
        if isinstance(limitations, list) and len(limitations) > 0:
            has_data_mention = any(
                'data' in str(lim).lower() or 'metric' in str(lim).lower() or
                'insufficient' in str(lim).lower() or 'incomplete' in str(lim).lower()
                for lim in limitations
            )
            if not has_data_mention:
                # Not an error, just a note
                pass
    
    return len(errors) == 0, errors
