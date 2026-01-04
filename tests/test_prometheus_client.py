"""
Tests for Prometheus client module
"""
import pytest
from unittest.mock import patch, MagicMock
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from metrics.prometheus_client import (
    PrometheusError,
    PrometheusConnectionError,
    PrometheusQueryError,
    query_instant,
    query_range,
    query_instant_cached,
    query_range_cached,
    clear_cache,
    _query_cache
)


class TestPrometheusError:
    """Tests for PrometheusError exception classes"""
    
    def test_prometheus_error_is_exception(self):
        """PrometheusError should be an Exception"""
        assert issubclass(PrometheusError, Exception)
    
    def test_prometheus_connection_error_inherits(self):
        """PrometheusConnectionError should inherit from PrometheusError"""
        assert issubclass(PrometheusConnectionError, PrometheusError)
    
    def test_prometheus_query_error_inherits(self):
        """PrometheusQueryError should inherit from PrometheusError"""
        assert issubclass(PrometheusQueryError, PrometheusError)


class TestQueryInstant:
    """Tests for query_instant function"""
    
    @patch('metrics.prometheus_client.requests.get')
    def test_successful_query(self, mock_get, mock_prometheus_response):
        """Should return results on successful query"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prometheus_response
        
        result = query_instant('up')
        
        assert len(result) == 1
        assert result[0]['metric']['pod'] == 'api-server-abc123'
    
    @patch('metrics.prometheus_client.requests.get')
    def test_query_failure_raises_error(self, mock_get):
        """Should raise PrometheusQueryError on non-200 response"""
        mock_get.return_value.status_code = 400
        mock_get.return_value.text = "Bad Request"
        
        with pytest.raises(PrometheusQueryError):
            query_instant('invalid{query')
    
    @patch('metrics.prometheus_client.requests.get')
    @patch('metrics.prometheus_client.time.sleep')
    def test_connection_error_retries(self, mock_sleep, mock_get):
        """Should retry on connection errors with backoff"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        with pytest.raises(PrometheusConnectionError):
            query_instant('up')
        
        # Should have attempted MAX_RETRIES times
        assert mock_get.call_count == 3
        # Should have slept between retries (3 retries = 3 sleeps before failure)
        assert mock_sleep.call_count == 3


class TestQueryRange:
    """Tests for query_range function"""
    
    @patch('metrics.prometheus_client.requests.get')
    def test_successful_range_query(self, mock_get, mock_prometheus_response):
        """Should return results on successful range query"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prometheus_response
        
        result = query_range('rate(container_cpu_usage_seconds_total[5m])', minutes=15)
        
        assert len(result) == 1
    
    @patch('metrics.prometheus_client.requests.get')
    def test_query_includes_time_params(self, mock_get, mock_prometheus_response):
        """Should include start, end, and step params"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prometheus_response
        
        query_range('up', minutes=10)
        
        call_args = mock_get.call_args
        params = call_args[1]['params']
        assert 'start' in params
        assert 'end' in params
        assert 'step' in params
        assert params['step'] == '1m'


class TestCaching:
    """Tests for query caching functionality"""
    
    def setup_method(self):
        """Clear cache before each test"""
        clear_cache()
    
    @patch('metrics.prometheus_client.requests.get')
    def test_cache_hit_avoids_request(self, mock_get, mock_prometheus_response):
        """Cached query should not make HTTP request"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prometheus_response
        
        # First call should hit Prometheus
        result1 = query_instant_cached('up')
        assert mock_get.call_count == 1
        
        # Second call should use cache
        result2 = query_instant_cached('up')
        assert mock_get.call_count == 1  # No additional call
        
        assert result1 == result2
    
    @patch('metrics.prometheus_client.requests.get')
    def test_clear_cache_invalidates(self, mock_get, mock_prometheus_response):
        """clear_cache should invalidate cached results"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prometheus_response
        
        query_instant_cached('up')
        assert mock_get.call_count == 1
        
        clear_cache()
        
        query_instant_cached('up')
        assert mock_get.call_count == 2  # New request after cache clear
    
    @patch('metrics.prometheus_client.requests.get')
    def test_different_queries_cached_separately(self, mock_get, mock_prometheus_response):
        """Different queries should have separate cache entries"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prometheus_response
        
        query_instant_cached('up')
        query_instant_cached('node_cpu_seconds_total')
        
        assert mock_get.call_count == 2
