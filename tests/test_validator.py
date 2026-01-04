"""
Tests for Phase 2 validator module

Note: The validator is intentionally flexible and only requires at least ONE
of the expected keys (cluster_summary, patterns, warnings, action_candidates, limitations).
This allows LLMs some flexibility in output format.
"""
import pytest
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase2.validator import validate_insights_output


class TestValidateInsightsOutput:
    """Tests for validate_insights_output function"""
    
    def test_valid_insights_passes(self, sample_insights_output, sample_analysis_output):
        """Valid insights should pass validation"""
        is_valid, errors = validate_insights_output(sample_insights_output, sample_analysis_output)
        assert is_valid
        assert len(errors) == 0
    
    def test_missing_all_keys_fails(self, sample_analysis_output):
        """Missing all expected keys should fail validation"""
        insights = {"random_key": "random_value"}
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('must have at least one' in e for e in errors)
    
    def test_single_key_passes(self, sample_analysis_output):
        """Single valid key should pass (flexible validator)"""
        insights = {"cluster_summary": "The cluster is healthy"}
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid
    
    def test_cluster_summary_not_string_fails(self, sample_analysis_output):
        """cluster_summary must be a string"""
        insights = {
            "cluster_summary": 123,  # Should be string
            "patterns": []
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('cluster_summary should be a string' in e for e in errors)
    
    def test_patterns_not_list_fails(self, sample_analysis_output):
        """patterns must be a list"""
        insights = {
            "cluster_summary": "Test",
            "patterns": "not a list"
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('patterns should be a list' in e for e in errors)
    
    def test_warnings_not_list_fails(self, sample_analysis_output):
        """warnings must be a list"""
        insights = {
            "cluster_summary": "Test",
            "warnings": {"key": "value"}  # Should be list
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('warnings should be a list' in e for e in errors)
    
    def test_empty_arrays_valid(self, sample_analysis_output):
        """Empty arrays should be valid"""
        insights = {
            "cluster_summary": "Cluster is healthy",
            "patterns": [],
            "warnings": [],
            "action_candidates": [],
            "priorities": "None",
            "limitations": []
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_non_dict_insights_fails(self, sample_analysis_output):
        """Non-dict insights should fail"""
        insights = "just a string"
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid
        assert any('must be a JSON object' in e for e in errors)
    
    def test_list_items_must_be_dict_or_string(self, sample_analysis_output):
        """List items should be dict or string"""
        insights = {
            "cluster_summary": "Test",
            "patterns": [123, 456]  # Should be dicts or strings
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert not is_valid


class TestSafetyFlagValidation:
    """Tests for safety flag cross-validation with Phase 1"""
    
    def test_resize_action_on_safe_deployment_passes(self, sample_analysis_output):
        """Resize actions should be allowed on safe deployments"""
        # api-server has unsafe_to_resize=False
        insights = {
            "cluster_summary": "Test",
            "action_candidates": [
                {
                    "action_id": "ACT-1",
                    "type": "RESIZE",
                    "title": "Resize api-server",
                    "scope": "Deployment"
                }
            ]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        # Should pass since api-server is safe to resize
        assert is_valid


class TestFlexibleValidation:
    """Tests verifying the validator's intentionally flexible behavior"""
    
    def test_partial_keys_accepted(self, sample_analysis_output):
        """Validator should accept partial key sets"""
        # Only patterns and limitations
        insights = {
            "patterns": [{"pattern_id": "P1", "description": "Test"}],
            "limitations": ["Limited data"]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid
    
    def test_string_limitations_accepted(self, sample_analysis_output):
        """Limitations can be strings, not just dicts"""
        insights = {
            "cluster_summary": "Test",
            "limitations": ["Simple string limitation", "Another limitation"]
        }
        
        is_valid, errors = validate_insights_output(insights, sample_analysis_output)
        
        assert is_valid
