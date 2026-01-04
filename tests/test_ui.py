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
            {'cluster_summary': {'deployment_count': 3}, 'deployment_analysis': [], 'node_analysis': [], 'hpa_analysis': []},  # analysis
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


class TestFragmentationAttributionUI:
    """Tests for Node Fragmentation Attribution display"""
    
    @patch('ui.load_json')
    def test_dashboard_renders_fragmentation_attribution(self, mock_load, client):
        """Dashboard should render fragmentation attribution when present"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 1, 'hpa_count': 0, 'node_count': 1},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': [{
                    'node': {'name': 'node-1', 'labels': {}},
                    'node_conditions': {'ready': True},
                    'allocatable_facts': {'cpu_allocatable': 4, 'memory_allocatable': 8000000000, 'pods_allocatable': 110},
                    'utilization_facts': {'cpu_usage_cores': 2, 'memory_usage_bytes': 4000000000, 'pod_count': 10},
                    'fragmentation_analysis': {'pod_packing_efficiency': 0.7, 'cpu_fragmentation': 0.45, 'memory_fragmentation': 0.35},
                    'fragmentation_attribution': {
                        'large_request_pods': [
                            {'pod_name': 'payments-api-abc', 'reason': 'CPU request 50% of node'}
                        ],
                        'constraint_blockers': [
                            {'pod_name': 'orders-api-xyz', 'constraint_type': 'podAntiAffinity'}
                        ],
                        'daemonset_overhead': {
                            'cpu_percent': 18.0,
                            'memory_percent': 12.0,
                            'exceeds_threshold': True,
                            'contributing_daemonsets': ['node-exporter', 'fluentd']
                        },
                        'scale_down_blockers': [
                            {'pod_name': 'analytics-worker', 'blocking_reason': 'PDB prevents eviction'}
                        ]
                    }
                }]
            },
            None  # no insights
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Check fragmentation attribution UI elements
        assert b'Attribution' in response.data
        assert b'Large Request Pods' in response.data
        assert b'payments-api-abc' in response.data
        assert b'Constraint Blockers' in response.data
        assert b'orders-api-xyz' in response.data
        assert b'DaemonSet Overhead' in response.data
        assert b'Scale-Down Blockers' in response.data
        assert b'analytics-worker' in response.data
    
    @patch('ui.load_json')
    def test_dashboard_handles_no_fragmentation_attribution(self, mock_load, client):
        """Dashboard should handle nodes without fragmentation attribution"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 0, 'hpa_count': 0, 'node_count': 1},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': [{
                    'node': {'name': 'node-1', 'labels': {}},
                    'node_conditions': {'ready': True},
                    'allocatable_facts': {'cpu_allocatable': 4, 'memory_allocatable': 8000000000, 'pods_allocatable': 110},
                    'utilization_facts': {'cpu_usage_cores': 1, 'memory_usage_bytes': 2000000000, 'pod_count': 5},
                    'fragmentation_analysis': {'pod_packing_efficiency': 0.85, 'cpu_fragmentation': 0.15, 'memory_fragmentation': 0.10}
                    # No fragmentation_attribution key
                }]
            },
            None
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Should not have Attribution button for non-fragmented nodes
        assert b'node-1' in response.data
    
    @patch('ui.load_json')
    def test_dashboard_handles_empty_attribution_lists(self, mock_load, client):
        """Dashboard should handle empty attribution lists gracefully"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 0, 'hpa_count': 0, 'node_count': 1},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': [{
                    'node': {'name': 'node-1', 'labels': {}},
                    'node_conditions': {'ready': True},
                    'allocatable_facts': {'cpu_allocatable': 4, 'memory_allocatable': 8000000000, 'pods_allocatable': 110},
                    'utilization_facts': {'cpu_usage_cores': 2, 'memory_usage_bytes': 4000000000, 'pod_count': 10},
                    'fragmentation_analysis': {'pod_packing_efficiency': 0.7, 'cpu_fragmentation': 0.4, 'memory_fragmentation': 0.35},
                    'fragmentation_attribution': {
                        'large_request_pods': [],
                        'constraint_blockers': [],
                        'daemonset_overhead': {
                            'cpu_percent': 5.0,
                            'memory_percent': 4.0,
                            'exceeds_threshold': False,
                            'contributing_daemonsets': []
                        },
                        'scale_down_blockers': []
                    }
                }]
            },
            None
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Should show "No X detected" messages
        assert b'No large request pods detected' in response.data or b'No constraint blockers detected' in response.data


class TestInsightsTabUI:
    """Tests for Insights (LLM) tab display"""
    
    @patch('ui.load_json')
    def test_dashboard_renders_new_insights_format(self, mock_load, client):
        """Dashboard should render new concise insights format"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 2, 'hpa_count': 1, 'node_count': 2},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': []
            },
            {
                'summary': '2 deployments, 2 nodes. One fragmented node.',
                'deployment_review': {
                    'bursty': ['api-server'],
                    'underutilized': ['web-frontend'],
                    'memory_pressure': [],
                    'unsafe_to_resize': ['background-worker']
                },
                'hpa_review': {
                    'at_threshold': ['api-server'],
                    'scaling_blocked': [],
                    'scaling_down': []
                },
                'node_fragmentation_review': {
                    'fragmented_nodes': ['node-1'],
                    'large_request_pods': ['payments-api'],
                    'constraint_blockers': ['orders-api (podAntiAffinity)'],
                    'daemonset_overhead': ['node-1'],
                    'scale_down_blockers': []
                },
                'cross_layer_risks': {
                    'high': ['background-worker'],
                    'medium': ['api-server']
                },
                'limitations': ['Limited observation window']
            }
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Check insights tab content
        assert b'Insights (LLM)' in response.data
        assert b'LLM-Generated Summary' in response.data
        assert b'Deployment Review' in response.data
        assert b'HPA Review' in response.data
        assert b'Node Fragmentation Review' in response.data
        assert b'Cross-Layer Risks' in response.data
        assert b'api-server' in response.data
    
    @patch('ui.load_json')
    def test_dashboard_handles_legacy_insights_format(self, mock_load, client):
        """Dashboard should handle legacy insights format (patterns/warnings)"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 1, 'hpa_count': 0, 'node_count': 1},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': []
            },
            {
                'cluster_summary': 'Legacy cluster summary',
                'patterns': [
                    {'description': 'CPU burstiness pattern', 'affected_objects': ['api-server'], 'evidence': ['P99 high']}
                ],
                'warnings': [
                    {'description': 'Memory warning', 'severity': 'High', 'scope': 'Deployment', 'confidence': 'High', 'evidence': ['OOM detected']}
                ],
                'limitations': []
            }
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Should render legacy patterns/warnings
        assert b'Patterns Detected' in response.data
        assert b'CPU burstiness pattern' in response.data
        assert b'Warnings' in response.data
    
    @patch('ui.load_json')
    def test_dashboard_works_without_insights(self, mock_load, client):
        """Dashboard should work when Phase 2 is disabled (no insights)"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 1, 'hpa_count': 0, 'node_count': 1},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': []
            },
            None  # No insights
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Should NOT have insights tab
        assert b'Facts &amp; Evidence' in response.data or b'Facts' in response.data
        # Insights tab button should not appear
        assert b'insights-tab' not in response.data or b'Insights (LLM)' not in response.data
    
    @patch('ui.load_json')
    def test_dashboard_renders_empty_review_sections(self, mock_load, client):
        """Dashboard should handle insights with all empty review sections"""
        mock_load.side_effect = [
            {
                'cluster_summary': {'deployment_count': 0, 'hpa_count': 0, 'node_count': 0},
                'deployment_analysis': [],
                'hpa_analysis': [],
                'node_analysis': []
            },
            {
                'summary': 'Empty cluster',
                'deployment_review': {
                    'bursty': [],
                    'underutilized': [],
                    'memory_pressure': [],
                    'unsafe_to_resize': []
                },
                'hpa_review': {
                    'at_threshold': [],
                    'scaling_blocked': [],
                    'scaling_down': []
                },
                'node_fragmentation_review': {
                    'fragmented_nodes': [],
                    'large_request_pods': [],
                    'constraint_blockers': [],
                    'daemonset_overhead': [],
                    'scale_down_blockers': []
                },
                'cross_layer_risks': {
                    'high': [],
                    'medium': []
                },
                'limitations': []
            }
        ]
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Should show "no issues flagged" messages
        assert b'No deployment issues flagged' in response.data or b'Empty cluster' in response.data
