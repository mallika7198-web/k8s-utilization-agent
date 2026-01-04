"""
Phase 2 LLM Runner - Read-only reasoning layer
Reads {cluster}_analysis_output.json, sends to LLM, writes {cluster}_insights_output.json atomically.
No modifications to Phase 1 output or Prometheus queries.
"""
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    PHASE2_ENABLED,
    ANALYSIS_OUTPUT_PATH,
    INSIGHTS_OUTPUT_PATH,
    PHASE2_LLM_PROMPT,
    LLM_MODE,
    LLM_ENDPOINT_URL,
    LLM_MODEL_NAME,
    LLM_TIMEOUT_SECONDS,
    LLM_API_KEY,
    setup_logging,
    get_clusters_to_run,
    get_analysis_output_path,
    get_insights_output_path,
    RUN_MODE,
    OUTPUT_DIR
)
from phase2.llm_client import LLMClient
from phase2.validator import validate_insights_output
from tracker import append_change

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, data: str) -> None:
    """Write file atomically using temp file and rename"""
    dirp = os.path.dirname(path) or '.'
    os.makedirs(dirp, exist_ok=True)
    
    fd, tmp = tempfile.mkstemp(prefix='.tmp_insights_', dir=dirp, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def run_once() -> Dict[str, Any]:
    """Run Phase 2 LLM analysis once (legacy single-cluster mode)
    
    Returns dict with:
    - insights: Generated LLM insights
    - validation_errors: Any validation issues
    - timestamp: Generation time
    """
    return run_once_for_cluster(ANALYSIS_OUTPUT_PATH, INSIGHTS_OUTPUT_PATH)


def run_once_for_cluster(analysis_path: str, insights_path: str) -> Dict[str, Any]:
    """Run Phase 2 LLM analysis for a specific cluster
    
    Args:
        analysis_path: Path to the cluster's analysis_output.json
        insights_path: Path to write the cluster's insights_output.json
    
    Returns dict with:
    - insights: Generated LLM insights
    - validation_errors: Any validation issues
    - timestamp: Generation time
    """
    
    # 1. Load Phase 1 analysis (read-only)
    logger.info(f"Loading Phase 1 analysis from {analysis_path}...")
    try:
        with open(analysis_path, 'r') as f:
            analysis_output = json.load(f)
    except FileNotFoundError:
        logger.error(f"Phase 1 output not found at {analysis_path}")
        return {'error': 'ANALYSIS_OUTPUT_NOT_FOUND'}
    except json.JSONDecodeError:
        logger.error(f"Phase 1 output is not valid JSON")
        return {'error': 'ANALYSIS_OUTPUT_INVALID_JSON'}
    
    logger.info(f"Loaded {len(json.dumps(analysis_output)):,} bytes")
    
    # 2. Prepare LLM input
    logger.info("Preparing LLM input...")
    llm_input = {
        'analysis_data': analysis_output,
        'analysis_timestamp': analysis_output.get('generated_at'),
        'cluster_summary': analysis_output.get('cluster_summary', {}),
        'deployment_count': len(analysis_output.get('deployment_analysis', [])),
        'hpa_count': len(analysis_output.get('hpa_analysis', [])),
        'node_count': len(analysis_output.get('node_analysis', []))
    }
    
    # 3. Call LLM
    logger.info(f"Calling LLM ({LLM_MODE} mode)...")
    logger.info(f"Endpoint: {LLM_ENDPOINT_URL}")
    logger.info(f"Model: {LLM_MODEL_NAME}")
    logger.debug(f"Timeout: {LLM_TIMEOUT_SECONDS}s")
    
    client = LLMClient(
        mode=LLM_MODE,
        endpoint=LLM_ENDPOINT_URL,
        model=LLM_MODEL_NAME,
        timeout=LLM_TIMEOUT_SECONDS,
        api_key=LLM_API_KEY
    )
    
    try:
        llm_response = client.send_prompt(
            prompt=PHASE2_LLM_PROMPT,
            context=json.dumps(llm_input, indent=2)
        )
        logger.info(f"LLM response received ({len(llm_response):,} characters)")
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {'error': f'LLM_CALL_FAILED: {str(e)}'}
    
    # 4. Parse LLM response
    logger.info("Parsing LLM response...")
    try:
        # Try to extract JSON from response
        insights_json = _extract_json_from_response(llm_response)
        insights_data = json.loads(insights_json)
        logger.info("Parsed JSON insights successfully")
    except json.JSONDecodeError as e:
        logger.error(f"LLM response is not valid JSON: {e}")
        return {'error': f'LLM_RESPONSE_INVALID_JSON: {str(e)}'}
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}")
        return {'error': f'LLM_RESPONSE_PARSE_FAILED: {str(e)}'}
    
    # 5. Validate insights
    logger.info("Validating insights structure...")
    is_valid, errors = validate_insights_output(insights_data, analysis_output)
    
    if not is_valid:
        logger.error("Validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return {'error': 'VALIDATION_FAILED', 'validation_errors': errors}
    
    logger.info("Insights validated successfully")
    
    # 6. Wrap insights with metadata
    output = {
        'generated_at': _now_iso(),
        'analysis_reference': analysis_path,
        'phase2_enabled': True,
        'llm_mode': LLM_MODE,
        'llm_model': LLM_MODEL_NAME,
        'insights': insights_data
    }
    
    return output


def main() -> int:
    """Main entry point for Phase 2 runner"""
    
    if not PHASE2_ENABLED:
        print("⏭️  Phase 2 is disabled (PHASE2_ENABLED=false)")
        return 0
    
    setup_logging()
    logger.info("=" * 50)
    logger.info("PHASE 2: LLM-BASED INSIGHTS GENERATION")
    logger.info("=" * 50)
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Get clusters to process
    clusters = get_clusters_to_run()
    logger.info(f"Processing {len(clusters)} cluster(s) (mode={RUN_MODE})...")
    
    success_count = 0
    failed_count = 0
    output_files = []
    
    # Loop through clusters one by one
    for cluster_info in clusters:
        cluster_name = cluster_info.get('cluster_name', 'unknown')
        analysis_path = get_analysis_output_path(cluster_name)
        insights_path = get_insights_output_path(cluster_name)
        
        logger.info("-" * 50)
        logger.info(f"Processing cluster: {cluster_name}")
        logger.info(f"  Analysis input: {analysis_path}")
        logger.info(f"  Insights output: {insights_path}")
        
        # Check if analysis file exists
        if not os.path.exists(analysis_path):
            logger.warning(f"[{cluster_name}] Analysis file not found: {analysis_path}")
            logger.warning(f"[{cluster_name}] Run Phase 1 first for this cluster")
            failed_count += 1
            continue
        
        # Run Phase 2 analysis for this cluster
        result = run_once_for_cluster(analysis_path, insights_path)
        
        # Check for errors
        if 'error' in result:
            error = result.get('error')
            logger.error(f"[{cluster_name}] Phase 2 failed: {error}")
            if 'validation_errors' in result:
                for err in result['validation_errors']:
                    logger.error(f"  - {err}")
            
            # Don't overwrite existing valid insights on error
            if os.path.exists(insights_path):
                logger.warning(f"[{cluster_name}] Keeping existing valid insights at {insights_path}")
            
            failed_count += 1
            continue
        
        # Write insights atomically
        logger.info(f"[{cluster_name}] Writing insights to {insights_path}...")
        try:
            _atomic_write(insights_path, json.dumps(result, indent=2))
            logger.info(f"[{cluster_name}] Wrote {len(json.dumps(result)):,} bytes")
            output_files.append(insights_path)
            success_count += 1
        except Exception as e:
            logger.error(f"[{cluster_name}] Failed to write insights: {e}")
            failed_count += 1
            continue
    
    # Update tracker
    if output_files:
        try:
            append_change({
                'files_modified': output_files,
                'type': 'phase2_insights',
                'description': f'Phase 2 LLM insights: {success_count} cluster(s) ({LLM_MODE} mode, {LLM_MODEL_NAME})'
            })
        except Exception as e:
            logger.warning(f"Failed to update tracker: {e}")
    
    logger.info("=" * 50)
    logger.info(f"Phase 2 complete: {success_count} succeeded, {failed_count} failed")
    logger.info(f"Output files: {output_files}")
    logger.info("=" * 50)
    
    return 0 if failed_count == 0 else 1


def _extract_json_from_response(response: str) -> str:
    """Extract JSON from LLM response which may contain extra text
    
    Tries to find a valid JSON block in the response, handling:
    - Raw JSON
    - JSON in markdown code blocks (```json...```)
    - JSON within explanatory text
    """
    import re
    
    # Try markdown code block first
    match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
        try:
            json.loads(json_str)  # Validate
            return json_str
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object { ... }
    start = response.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")
    
    # Find matching closing brace
    depth = 0
    for i in range(start, len(response)):
        if response[i] == '{':
            depth += 1
        elif response[i] == '}':
            depth -= 1
            if depth == 0:
                json_str = response[start:i+1]
                try:
                    json.loads(json_str)  # Validate
                    return json_str
                except json.JSONDecodeError:
                    pass
    
    raise ValueError("Could not find valid JSON object in response")


if __name__ == '__main__':
    sys.exit(main())
