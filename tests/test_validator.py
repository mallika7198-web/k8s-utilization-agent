"""
Tests for Phase 2 validator module

The validator ensures:
1. LLM output follows the concise grouped format
2. Only Phase-1 categories and objects are referenced
3. Safety flags (unsafe_to_resize, insufficient_data) are respected
4. No action_candidates (Phase 2 groups facts only)
"""
import pytest
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase2.validator import validate_insights_output, _extract_phase1_names


class TestExtractPhase1Names:
    """Tests for _extract_phase1_names helper"""
    
    def test_extracts_deployment_names(self, sample_analysis_output):
        """Should extract all deployment names"""
        names = _extract_phase1_names(sample_analysis_output)
        
        assert 'api-server' in names['deployments']
        assert 'background-worker' in names['deployments']
        assert 'web-frontend' in names['deployments']
    
    def test_extracts_hpa_names(self, sample_analysis_output):
        """Should extract all HPA names"""
        names = _extract_phase1_names(sample_analysis_output)
        
        assert 'api-server' in names['hpas']
    
    def test_extracts_node_names(self, sample_analysis_output):
        """Should extract all node names"""
        names = _extract_phase1_names(sample_analysis_output)
        
        assert 'node-1' in names['nodes']
        assert 'node-2' in names['nodes']
    
    def test_extracts_pod_names_from_fragmentation(self, sample_analysis_output):
        """Should extract pod names from fragmentation attribution"""
        names = _extract_phase1_names(sample_analysis_output)
        
        assert 'background-worker-abc' in names['pods']
        assert 'api-server-xyz' in names['pods']


class TestValidateInsightsOutput:
    """Tests for validate_insights_output function"""
    
    def test_valid_insights_passes(self, sample_insights_output, sample_analysis_output):
        """Valid insights should pass validation"""
        is_valid, errors = validate_insights_output(sample_insights_output, sample_analysis_output)
        assert is_valid, f"Unexpected errors: {errors}"
        assert len(errors) == 0
    
    def test_missing_summary_fails(self, sample_analysis_output):
        """Missing summary key should fail validation"""
        insights = {
            "deployment_review": {"bursty": [], "underutilized": [], "memory_pressure": [], "unsafe_to_resize": []}
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('Missing required key: summary' in e for e in errors)
    
    def test_missing_all_review_sections_fails(self, sample_analysis_output):
        """Missing all review sections should fail validation"""
        insights = {"summary": "Test summary", "limitations": []}
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('Must have at least one review section' in e for e in errors)
    
    def test_summary_not_string_fails(self, sample_analysis_output):
        """summary must be a string"""
        insights = {
            "summary": 123,  # Should be string
            "deployment_review": {"bursty": []}
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('summary must be a string' in e for e in errors)
    
    def test_summary_too_long_fails(self, sample_analysis_output):
        """summary should be concise (max 500 chars)"""
        insights = {
            "summary": "x" * 600,  # Too long
            "deployment_review": {"bursty": []}
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('summary too long' in e for e in errors)
    
    def test_deployment_review_not_dict_fails(self, sample_analysis_output):
        """deployment_review must be an object"""
        insights = {
            "summary": "Test",
            "deployment_review": ["not", "a", "dict"]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('deployment_review must be an object' in e for e in errors)
    
    def test_invalid_deployment_review_key_fails(self, sample_analysis_output):
        """Invalid keys in deployment_review should fail"""
        insights = {
            "summary": "Test",
            "deployment_review": {
                "bursty": [],
                "invalid_key": ["test"]  # Not a valid category
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('deployment_review.invalid_key is not a valid category' in e for e in errors)
    
    def test_deployment_review_value_not_list_fails(self, sample_analysis_output):
        """deployment_review values must be arrays"""
        insights = {
            "summary": "Test",
            "deployment_review": {
                "bursty": "not a list"
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('deployment_review.bursty must be an array' in e for e in errors)
    
    def test_non_dict_insights_fails(self, sample_analysis_output):
        """Non-dict insights should fail"""
        insights = "just a string"
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('must be a JSON object' in e for e in errors)
    
    def test_empty_arrays_valid(self, sample_analysis_output):
        """Empty arrays should be valid"""
        insights = {
            "summary": "Cluster is healthy",
            "deployment_review": {
                "bursty": [],
                "underutilized": [],
                "memory_pressure": [],
                "unsafe_to_resize": []
            },
            "limitations": []
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid, f"Unexpected errors: {errors}"


class TestPhase1ReferenceValidation:
    """Tests for Phase 1 reference validation"""
    
    def test_unknown_deployment_name_fails(self, sample_analysis_output):
        """Referencing unknown deployment should fail"""
        insights = {
            "summary": "Test",
            "deployment_review": {
                "bursty": ["unknown-deployment"]  # Not in Phase 1
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('not found in Phase 1' in e for e in errors)
    
    def test_valid_deployment_name_passes(self, sample_analysis_output):
        """Referencing valid deployment should pass"""
        insights = {
            "summary": "Test",
            "deployment_review": {
                "bursty": ["api-server"],  # Exists in Phase 1
                "underutilized": [],
                "memory_pressure": [],
                "unsafe_to_resize": []
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid, f"Unexpected errors: {errors}"
    
    def test_name_with_reason_suffix_passes(self, sample_analysis_output):
        """Names with (reason) suffix should validate correctly"""
        insights = {
            "summary": "Test",
            "node_fragmentation_review": {
                "fragmented_nodes": [],
                "large_request_pods": [],
                "constraint_blockers": ["api-server-xyz (podAntiAffinity)"],  # Has suffix
                "daemonset_overhead": [],
                "scale_down_blockers": []
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid, f"Unexpected errors: {errors}"
    
    def test_unknown_node_name_fails(self, sample_analysis_output):
        """Referencing unknown node should fail"""
        insights = {
            "summary": "Test",
            "node_fragmentation_review": {
                "fragmented_nodes": ["node-999"],  # Not in Phase 1
                "large_request_pods": [],
                "constraint_blockers": [],
                "daemonset_overhead": [],
                "scale_down_blockers": []
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('not found in Phase 1' in e for e in errors)


class TestSafetyFlagValidation:
    """Tests for safety flag cross-validation with Phase 1"""
    
    def test_action_candidates_not_allowed(self, sample_analysis_output):
        """action_candidates should not be allowed (Phase 2 groups facts only)"""
        insights = {
            "summary": "Test",
            "deployment_review": {"bursty": []},
            "action_candidates": [
                {"action_id": "ACT-1", "description": "Do something"}
            ]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('action_candidates not allowed' in e for e in errors)
    
    def test_insufficient_data_must_be_in_limitations(self, sample_analysis_output):
        """When Phase 1 has insufficient_data, limitations must be present"""
        # Add insufficient_data to analysis
        sample_analysis_output['node_analysis'][0]['insufficient_data'] = True
        
        insights = {
            "summary": "Test",
            "deployment_review": {"bursty": []},
            "limitations": []  # Empty but should have something
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('insufficient_data' in e and 'limitations is empty' in e for e in errors)


class TestHPAReviewValidation:
    """Tests for HPA review section validation"""
    
    def test_valid_hpa_review_passes(self, sample_analysis_output):
        """Valid HPA review should pass"""
        insights = {
            "summary": "Test",
            "hpa_review": {
                "at_threshold": ["api-server"],
                "scaling_blocked": [],
                "scaling_down": []
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid, f"Unexpected errors: {errors}"
    
    def test_invalid_hpa_review_key_fails(self, sample_analysis_output):
        """Invalid keys in hpa_review should fail"""
        insights = {
            "summary": "Test",
            "hpa_review": {
                "invalid_key": []
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('hpa_review.invalid_key is not a valid category' in e for e in errors)


class TestCrossLayerRisksValidation:
    """Tests for cross_layer_risks section validation"""
    
    def test_valid_cross_layer_risks_passes(self, sample_analysis_output):
        """Valid cross_layer_risks should pass"""
        insights = {
            "summary": "Test",
            "cross_layer_risks": {
                "high": ["background-worker"],
                "medium": []
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid, f"Unexpected errors: {errors}"
    
    def test_invalid_risk_level_fails(self, sample_analysis_output):
        """Invalid risk level keys should fail"""
        insights = {
            "summary": "Test",
            "cross_layer_risks": {
                "critical": []  # Not valid, should be high/medium
            }
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('not a valid category' in e for e in errors)


class TestLimitationsValidation:
    """Tests for limitations section validation"""
    
    def test_valid_limitations_passes(self, sample_analysis_output):
        """Valid limitations should pass"""
        insights = {
            "summary": "Test",
            "deployment_review": {"bursty": []},
            "limitations": ["Limited data", "Short observation window"]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid, f"Unexpected errors: {errors}"
    
    def test_limitations_not_list_fails(self, sample_analysis_output):
        """limitations must be a list"""
        insights = {
            "summary": "Test",
            "deployment_review": {"bursty": []},
            "limitations": "not a list"
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('limitations must be an array' in e for e in errors)
    
    def test_limitations_non_string_entry_fails(self, sample_analysis_output):
        """limitations entries must be strings"""
        insights = {
            "summary": "Test",
            "deployment_review": {"bursty": []},
            "limitations": [123, {"key": "value"}]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('limitations[0] must be a string' in e for e in errors)
