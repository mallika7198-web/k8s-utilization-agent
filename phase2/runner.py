"""
Phase 2 LLM Runner - Read-only reasoning layer
Reads analysis_output.json, sends to LLM, writes insights_output.json atomically.
No modifications to Phase 1 output or Prometheus queries.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any

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
    LLM_TIMEOUT_SECONDS
)
from phase2.llm_client import LLMClient
from phase2.validator import validate_insights_output
from tracker import append_change


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
    """Run Phase 2 LLM analysis once
    
    Returns dict with:
    - insights: Generated LLM insights
    - validation_errors: Any validation issues
    - timestamp: Generation time
    """
    
    # 1. Load Phase 1 analysis (read-only)
    print(f"📖 Loading Phase 1 analysis from {ANALYSIS_OUTPUT_PATH}...")
    try:
        with open(ANALYSIS_OUTPUT_PATH, 'r') as f:
            analysis_output = json.load(f)
    except FileNotFoundError:
        print(f"❌ Phase 1 output not found at {ANALYSIS_OUTPUT_PATH}")
        return {'error': 'ANALYSIS_OUTPUT_NOT_FOUND'}
    except json.JSONDecodeError:
        print(f"❌ Phase 1 output is not valid JSON")
        return {'error': 'ANALYSIS_OUTPUT_INVALID_JSON'}
    
    print(f"   ✓ Loaded {len(json.dumps(analysis_output)):,} bytes")
    
    # 2. Prepare LLM input
    print(f"\n🧠 Preparing LLM input...")
    llm_input = {
        'analysis_data': analysis_output,
        'analysis_timestamp': analysis_output.get('generated_at'),
        'cluster_summary': analysis_output.get('cluster_summary', {}),
        'deployment_count': len(analysis_output.get('deployment_analysis', [])),
        'hpa_count': len(analysis_output.get('hpa_analysis', [])),
        'node_count': len(analysis_output.get('node_analysis', []))
    }
    
    # 3. Call LLM
    print(f"\n🔗 Calling LLM ({LLM_MODE} mode)...")
    print(f"   Endpoint: {LLM_ENDPOINT_URL}")
    print(f"   Model: {LLM_MODEL_NAME}")
    print(f"   Timeout: {LLM_TIMEOUT_SECONDS}s")
    
    client = LLMClient(
        mode=LLM_MODE,
        endpoint=LLM_ENDPOINT_URL,
        model=LLM_MODEL_NAME,
        timeout=LLM_TIMEOUT_SECONDS
    )
    
    try:
        llm_response = client.send_prompt(
            prompt=PHASE2_LLM_PROMPT,
            context=json.dumps(llm_input, indent=2)
        )
        print(f"   ✓ LLM response received ({len(llm_response):,} characters)")
    except Exception as e:
        print(f"   ❌ LLM call failed: {e}")
        return {'error': f'LLM_CALL_FAILED: {str(e)}'}
    
    # 4. Parse LLM response
    print(f"\n📝 Parsing LLM response...")
    try:
        # Try to extract JSON from response
        insights_json = _extract_json_from_response(llm_response)
        insights_data = json.loads(insights_json)
        print(f"   ✓ Parsed JSON insights")
    except json.JSONDecodeError as e:
        print(f"   ❌ LLM response is not valid JSON: {e}")
        return {'error': f'LLM_RESPONSE_INVALID_JSON: {str(e)}'}
    except Exception as e:
        print(f"   ❌ Failed to parse LLM response: {e}")
        return {'error': f'LLM_RESPONSE_PARSE_FAILED: {str(e)}'}
    
    # 5. Validate insights
    print(f"\n✓ Validating insights structure...")
    is_valid, errors = validate_insights_output(insights_data, analysis_output)
    
    if not is_valid:
        print(f"   ❌ Validation failed:")
        for error in errors:
            print(f"      - {error}")
        return {'error': 'VALIDATION_FAILED', 'validation_errors': errors}
    
    print(f"   ✓ Insights valid")
    
    # 6. Wrap insights with metadata
    output = {
        'generated_at': _now_iso(),
        'analysis_reference': ANALYSIS_OUTPUT_PATH,
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
    
    print("=" * 70)
    print("PHASE 2: LLM-BASED INSIGHTS GENERATION")
    print("=" * 70)
    
    # Run Phase 2 analysis
    result = run_once()
    
    # Check for errors
    if 'error' in result:
        error = result.get('error')
        print(f"\n❌ Phase 2 failed: {error}")
        if 'validation_errors' in result:
            for err in result['validation_errors']:
                print(f"   - {err}")
        
        # Don't overwrite existing valid insights on error
        if os.path.exists(INSIGHTS_OUTPUT_PATH):
            print(f"   Keeping existing valid insights at {INSIGHTS_OUTPUT_PATH}")
        
        return 1
    
    # Write insights atomically
    print(f"\n💾 Writing insights to {INSIGHTS_OUTPUT_PATH}...")
    try:
        _atomic_write(INSIGHTS_OUTPUT_PATH, json.dumps(result, indent=2))
        print(f"   ✓ Wrote {len(json.dumps(result)):,} bytes")
    except Exception as e:
        print(f"   ❌ Failed to write insights: {e}")
        return 2
    
    # Update tracker
    try:
        append_change({
            'files_modified': [INSIGHTS_OUTPUT_PATH, 'phase2/runner.py'],
            'type': 'phase2_insights',
            'description': f'Phase 2 LLM insights generated ({LLM_MODE} mode, {LLM_MODEL_NAME})'
        })
    except Exception:
        pass  # Best-effort tracker update
    
    print(f"\n✅ Phase 2 complete")
    print(f"   - Generated at: {result.get('generated_at')}")
    print(f"   - LLM model: {result.get('llm_model')}")
    print(f"   - Output: {INSIGHTS_OUTPUT_PATH}")
    
    return 0


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
