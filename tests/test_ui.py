"""
Tests for UI endpoints
"""
import pytest
from unittest.mock import patch, MagicMock
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui import app, load_json, ANALYSIS_FILE, INSIGHTS_FILE


@pytest.fixture
def client():
    """Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestHealthEndpoint:
    """Tests for /health endpoint"""
    
    def test_health_returns_200(self, client):
        """Health endpoint should always return 200"""
        response = client.get('/health')
        assert response.status_code == 200
    
    def test_health_returns_json(self, client):
        """Health endpoint should return JSON"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'healthy'
    
    def test_health_includes_timestamp(self, client):
        """Health endpoint should include timestamp"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'timestamp' in data


class TestReadyEndpoint:
    """Tests for /ready endpoint"""
    
    @patch('ui.load_json')
    def test_ready_returns_200_when_analysis_exists(self, mock_load, client):
        """Ready endpoint should return 200 when analysis file exists"""
        mock_load.return_value = {'cluster_summary': {}}
        
        response = client.get('/ready')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ready'
    
    @patch('ui.load_json')
    def test_ready_returns_503_when_no_analysis(self, mock_load, client):
        """Ready endpoint should return 503 when analysis file missing"""
        mock_load.return_value = None
        
        response = client.get('/ready')
        
        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['status'] == 'not_ready'
    
    @patch('ui.load_json')
    def test_ready_includes_insights_availability(self, mock_load, client):
        """Ready endpoint should indicate if insights available"""
        # Return analysis for first call, insights for second
        mock_load.side_effect = [
            {'cluster_summary': {}},  # analysis
            {'patterns': []}  # insights
        ]
        
        response = client.get('/ready')
        data = json.loads(response.data)
        
        assert 'insights_available' in data


class TestMetricsEndpoint:
    """Tests for /metrics endpoint"""
    
    def test_metrics_returns_200(self, client):
        """Metrics endpoint should return 200"""
        response = client.get('/metrics')
        assert response.status_code == 200
    
    def test_metrics_returns_text(self, client):
        """Metrics endpoint should return text/plain"""
        response = client.get('/metrics')
        assert response.content_type == 'text/plain; charset=utf-8'
    
    def test_metrics_includes_requests_total(self, client):
        """Metrics should include requests_total counter"""
        response = client.get('/metrics')
        assert b'k8s_ui_requests_total' in response.data
    
    def test_metrics_includes_uptime(self, client):
        """Metrics should include uptime gauge"""
        response = client.get('/metrics')
        assert b'k8s_ui_uptime_seconds' in response.data
    
    def test_metrics_includes_analysis_available(self, client):
        """Metrics should include analysis_available gauge"""
        response = client.get('/metrics')
        assert b'k8s_ui_analysis_available' in response.data


class TestApiEndpoints:
    """Tests for API endpoints"""
    
    @patch('ui.load_json')
    def test_api_analysis_returns_data(self, mock_load, client):
        """API analysis endpoint should return analysis data"""
        mock_load.return_value = {'cluster_summary': {'deployment_count': 5}}
        
        response = client.get('/api/analysis')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'cluster_summary' in data
    
    @patch('ui.load_json')
    def test_api_analysis_returns_404_when_missing(self, mock_load, client):
        """API analysis endpoint should return 404 when file missing"""
        mock_load.return_value = None
        
        response = client.get('/api/analysis')
        
        assert response.status_code == 404
    
    @patch('ui.load_json')
    def test_api_insights_returns_data(self, mock_load, client):
        """API insights endpoint should return insights data"""
        mock_load.return_value = {'patterns': [], 'warnings': []}
        
        response = client.get('/api/insights')
        
        assert response.status_code == 200
    
    @patch('ui.load_json')
    def test_api_insights_returns_404_when_missing(self, mock_load, client):
        """API insights endpoint should return 404 when file missing"""
        mock_load.return_value = None
        
        response = client.get('/api/insights')
        
        assert response.status_code == 404


class TestDashboard:
    """Tests for main dashboard"""
    
    @patch('ui.load_json')
    def test_dashboard_renders_with_analysis(self, mock_load, client):
        """Dashboard should render when analysis exists"""
        mock_load.side_effect = [
            {'cluster_summary': {'deployment_count': 3}, 'deployment_analysis': []},  # analysis
            None  # insights
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
    
    @patch('ui.load_json')
    def test_dashboard_shows_error_without_analysis(self, mock_load, client):
        """Dashboard should show error when analysis missing"""
        mock_load.return_value = None
        
        response = client.get('/')
        
        # Should still return 200 but with error template
        assert response.status_code == 200
        assert b'Phase 1 analysis not found' in response.data or b'error' in response.data.lower()
