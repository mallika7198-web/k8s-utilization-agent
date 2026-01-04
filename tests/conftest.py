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
            },
            {
                "deployment": {
                    "name": "web-frontend",
                    "namespace": "default",
                    "replicas": {"desired": 5, "ready": 5, "updated": 5}
                },
                "resource_usage": {
                    "cpu": {"avg_cores": 0.08, "p95_cores": 0.15, "p99_cores": 0.2, "max_cores": 0.25},
                    "memory": {"avg_bytes": 128000000, "p95_bytes": 150000000, "p99_bytes": 160000000, "max_bytes": 170000000}
                },
                "request_allocation": {
                    "cpu_requests": "250m",
                    "memory_requests": "256Mi",
                    "cpu_utilization_percent": 32,
                    "memory_utilization_percent": 50
                },
                "behavior_flags": ["UNDERUTILIZED"],
                "pending_pods_count": 0,
                "unsafe_to_resize": False
            }
        ],
        "hpa_analysis": [
            {
                "hpa": {
                    "name": "api-server",
                    "namespace": "default",
                    "target_deployment": "api-server"
                },
                "scaling_config": {
                    "min_replicas": 2,
                    "max_replicas": 10,
                    "current_replicas": 3,
                    "desired_replicas": 3
                },
                "scaling_status": "CAUTION",
                "scaling_behavior": {
                    "description": "Scaling based on CPU at 80% target",
                    "current_load": 75,
                    "scaling_blocked": False
                },
                "scaling_flags": ["AT_CPU_THRESHOLD"],
                "recommendations": "Monitor CPU trend"
            }
        ],
        "node_analysis": [
            {
                "node": {
                    "name": "node-1",
                    "labels": {"kubernetes.io/hostname": "node-1"}
                },
                "insufficient_data": False,
                "allocatable_facts": {
                    "cpu_allocatable": 3.9,
                    "memory_allocatable": 7500000000
                },
                "fragmentation_analysis": {
                    "cpu_fragmentation": 0.45,
                    "memory_fragmentation": 0.34
                },
                "fragmentation_attribution": {
                    "large_request_pods": [
                        {"pod_name": "background-worker-abc", "reason": "CPU request 50% of node"}
                    ],
                    "constraint_blockers": [
                        {"pod_name": "api-server-xyz", "constraint_type": "podAntiAffinity"}
                    ],
                    "daemonset_overhead": {
                        "cpu_percent": 18.0,
                        "memory_percent": 12.0,
                        "exceeds_threshold": True,
                        "contributing_daemonsets": ["node-exporter", "fluentd"]
                    },
                    "scale_down_blockers": []
                }
            },
            {
                "node": {
                    "name": "node-2",
                    "labels": {"kubernetes.io/hostname": "node-2"}
                },
                "insufficient_data": False,
                "allocatable_facts": {
                    "cpu_allocatable": 3.9,
                    "memory_allocatable": 7500000000
                },
                "fragmentation_analysis": {
                    "cpu_fragmentation": 0.25,
                    "memory_fragmentation": 0.20
                }
            }
        ],
        "cross_layer_observations": [
            {
                "observation": "Memory pressure in background-worker",
                "scope": "Deployment",
                "details": "Uses 100% of allocated memory",
                "risk_level": "High",
                "affected_components": ["background-worker"]
            },
            {
                "observation": "Overprovisioned web-frontend",
                "scope": "Cluster",
                "details": "Only 32% CPU utilization",
                "risk_level": "Medium",
                "affected_components": ["web-frontend"]
            }
        ]
    }


@pytest.fixture
def sample_insights_output():
    """Sample valid LLM insights output for testing (new concise format)"""
    return {
        "summary": "3 deployments, 2 nodes. One fragmented node, one bursty deployment.",
        "deployment_review": {
            "bursty": ["api-server"],
            "underutilized": ["web-frontend"],
            "memory_pressure": ["background-worker"],
            "unsafe_to_resize": ["background-worker"]
        },
        "hpa_review": {
            "at_threshold": ["api-server"],
            "scaling_blocked": [],
            "scaling_down": []
        },
        "node_fragmentation_review": {
            "fragmented_nodes": ["node-1"],
            "large_request_pods": ["background-worker-abc"],
            "constraint_blockers": ["api-server-xyz (podAntiAffinity)"],
            "daemonset_overhead": ["node-1"],
            "scale_down_blockers": []
        },
        "cross_layer_risks": {
            "high": ["background-worker"],
            "medium": ["web-frontend"]
        },
        "limitations": []
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
    """Mock LLM API response (new concise format)"""
    return json.dumps({
        "summary": "Test cluster summary",
        "deployment_review": {
            "bursty": [],
            "underutilized": [],
            "memory_pressure": [],
            "unsafe_to_resize": []
        },
        "hpa_review": {
            "at_threshold": [],
            "scaling_blocked": [],
            "scaling_down": []
        },
        "node_fragmentation_review": {
            "fragmented_nodes": [],
            "large_request_pods": [],
            "constraint_blockers": [],
            "daemonset_overhead": [],
            "scale_down_blockers": []
        },
        "cross_layer_risks": {
            "high": [],
            "medium": []
        },
        "limitations": []
    })


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary directory for test output files"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir
