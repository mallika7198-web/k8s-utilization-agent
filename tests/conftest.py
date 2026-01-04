"""
Test fixtures and configuration for pytest
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def sample_analysis_output():
    """Sample Phase 1 analysis output for testing"""
    return {
        "generated_at": "2026-01-04T10:00:00Z",
        "cluster_summary": {
            "deployment_count": 3,
            "hpa_count": 2,
            "node_count": 2
        },
        "deployment_analysis": [
            {
                "deployment": {
                    "name": "api-server",
                    "namespace": "default",
                    "replicas": {"desired": 3, "ready": 3, "updated": 3}
                },
                "resource_usage": {
                    "cpu": {"avg_cores": 0.45, "p95_cores": 1.2, "p99_cores": 2.1, "max_cores": 2.5},
                    "memory": {"avg_bytes": 512000000, "p95_bytes": 800000000, "p99_bytes": 950000000, "max_bytes": 1000000000}
                },
                "request_allocation": {
                    "cpu_requests": "500m",
                    "memory_requests": "512Mi",
                    "cpu_utilization_percent": 90,
                    "memory_utilization_percent": 102
                },
                "behavior_flags": ["BURSTY", "CPU_BURSTY"],
                "pending_pods_count": 0,
                "unsafe_to_resize": False
            },
            {
                "deployment": {
                    "name": "background-worker",
                    "namespace": "batch",
                    "replicas": {"desired": 2, "ready": 2, "updated": 2}
                },
                "resource_usage": {
                    "cpu": {"avg_cores": 1.5, "p95_cores": 1.8, "p99_cores": 2.0, "max_cores": 2.2},
                    "memory": {"avg_bytes": 2000000000, "p95_bytes": 2200000000, "p99_bytes": 2300000000, "max_bytes": 2400000000}
                },
                "request_allocation": {
                    "cpu_requests": "2000m",
                    "memory_requests": "2Gi",
                    "cpu_utilization_percent": 75,
                    "memory_utilization_percent": 100
                },
                "behavior_flags": ["HEALTHY"],
                "pending_pods_count": 0,
                "unsafe_to_resize": True
            }
        ],
        "hpa_analysis": [],
        "node_analysis": []
    }


@pytest.fixture
def sample_insights_output():
    """Sample valid LLM insights output for testing"""
    return {
        "cluster_summary": "The cluster is healthy with 3 deployments running.",
        "patterns": [
            {
                "pattern_id": "PATTERN-1",
                "description": "CPU burstiness in API server",
                "affected_objects": ["api-server"],
                "evidence": ["P99 CPU 2.1 vs avg 0.45"]
            }
        ],
        "warnings": [
            {
                "warning_id": "WARN-1",
                "severity": "Medium",
                "scope": "Deployment",
                "description": "API server shows bursty CPU usage",
                "evidence": ["behavior_flags include BURSTY"],
                "confidence": "High"
            }
        ],
        "action_candidates": [
            {
                "action_id": "ACT-1",
                "scope": "Deployment",
                "description": "Review API server CPU requests",
                "expected_impact": "Better resource allocation",
                "prerequisites": [],
                "blocked_by": [],
                "confidence": "Medium"
            }
        ],
        "priorities": "Focus on API server CPU allocation first",
        "limitations": ["Limited traffic data available"]
    }


@pytest.fixture
def mock_prometheus_response():
    """Mock Prometheus API response"""
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"pod": "api-server-abc123"},
                    "values": [[1704355200, "0.5"], [1704355260, "0.6"]]
                }
            ]
        }
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM API response"""
    return json.dumps({
        "cluster_summary": "Test cluster summary",
        "patterns": [],
        "warnings": [],
        "action_candidates": [],
        "priorities": "No immediate priorities",
        "limitations": []
    })


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary directory for test output files"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir
