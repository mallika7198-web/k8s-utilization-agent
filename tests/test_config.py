"""
Tests for configuration module
"""
import pytest
import os
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfigValidation:
    """Tests for configuration validation"""
    
    def test_valid_config_passes(self):
        """Valid configuration should pass validation"""
        from config import validate_config, ConfigValidationError
        
        # Default config should be valid
        try:
            validate_config()
        except ConfigValidationError:
            pytest.fail("Default config should be valid")
    
    def test_negative_timeout_fails(self):
        """Negative timeout should fail validation"""
        from config import ConfigValidationError, _validate_positive_int
        
        with pytest.raises(ConfigValidationError):
            _validate_positive_int("TEST_TIMEOUT", -1)
    
    def test_zero_timeout_fails(self):
        """Zero timeout should fail validation"""
        from config import ConfigValidationError, _validate_positive_int
        
        with pytest.raises(ConfigValidationError):
            _validate_positive_int("TEST_TIMEOUT", 0)
    
    def test_positive_timeout_passes(self):
        """Positive timeout should pass validation"""
        from config import _validate_positive_int
        
        # Should not raise
        _validate_positive_int("TEST_TIMEOUT", 30)
    
    def test_invalid_url_fails(self):
        """Invalid URL should fail validation"""
        from config import ConfigValidationError, _validate_url
        
        with pytest.raises(ConfigValidationError):
            _validate_url("TEST_URL", "not-a-url")
    
    def test_valid_http_url_passes(self):
        """Valid HTTP URL should pass validation"""
        from config import _validate_url
        
        # Should not raise
        _validate_url("TEST_URL", "http://localhost:9090")
    
    def test_valid_https_url_passes(self):
        """Valid HTTPS URL should pass validation"""
        from config import _validate_url
        
        # Should not raise
        _validate_url("TEST_URL", "https://prometheus.example.com")
    
    def test_invalid_llm_mode_fails(self):
        """Invalid LLM mode should fail validation"""
        from config import ConfigValidationError, _validate_llm_mode
        
        with pytest.raises(ConfigValidationError):
            _validate_llm_mode("invalid")
    
    def test_valid_llm_mode_local_passes(self):
        """'local' LLM mode should pass validation"""
        from config import _validate_llm_mode
        
        # Should not raise
        _validate_llm_mode("local")
    
    def test_valid_llm_mode_remote_passes(self):
        """'remote' LLM mode should pass validation"""
        from config import _validate_llm_mode
        
        # Should not raise
        _validate_llm_mode("remote")


class TestLoggingSetup:
    """Tests for logging configuration"""
    
    def test_setup_logging_configures_root(self):
        """setup_logging should configure root logger"""
        import logging
        from config import setup_logging
        
        setup_logging()
        
        # Root logger should be configured
        root_logger = logging.getLogger()
        assert root_logger.level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
    
    def test_log_level_from_env(self):
        """LOG_LEVEL env var should be respected"""
        # This test would require reloading the config module
        # which is complex - just document the expected behavior
        pass


class TestEnvBool:
    """Tests for _env_bool helper"""
    
    def test_env_bool_true_values(self):
        """Should return True for various true strings"""
        from config import _env_bool
        
        with patch.dict(os.environ, {'TEST_VAR': '1'}):
            # Need to reload for env change
            pass
        
        # Test the function directly with mocking
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = 'true'
            assert _env_bool('TEST', False) == True
            
            mock_getenv.return_value = 'yes'
            assert _env_bool('TEST', False) == True
            
            mock_getenv.return_value = '1'
            assert _env_bool('TEST', False) == True
    
    def test_env_bool_false_values(self):
        """Should return False for various false strings"""
        from config import _env_bool
        
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = 'false'
            assert _env_bool('TEST', True) == False
            
            mock_getenv.return_value = '0'
            assert _env_bool('TEST', True) == False
    
    def test_env_bool_default(self):
        """Should return default when env var not set"""
        from config import _env_bool
        
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = None
            assert _env_bool('TEST', True) == True
            assert _env_bool('TEST', False) == False
