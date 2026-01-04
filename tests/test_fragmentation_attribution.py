"""
Tests for Node Fragmentation Attribution
"""
import pytest
from unittest.mock import patch, MagicMock
from analysis.fragmentation_attribution import (
    analyze_fragmentation_attribution,
    _find_large_request_pods,
    _find_constraint_blockers,
    _calculate_daemonset_overhead,
    _find_scale_down_blockers
)


class TestFragmentationAttribution:
    """Tests for the main fragmentation attribution function"""
    
    def test_returns_none_for_non_fragmented_node(self):
        """Should return None when node is not fragmented"""
        node_analysis = {
            'node': {'name': 'test-node'},
            'fragmentation_analysis': {
                'cpu_fragmentation': 0.1,
                'memory_fragmentation': 0.1
            },
            'allocatable_facts': {
                'cpu_allocatable': 4.0,
                'memory_allocatable': 8 * 1024**3
            }
        }
        
        result = analyze_fragmentation_attribution(
            'test-node',
            node_analysis,
            [node_analysis]
        )
        
        assert result is None
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_returns_attribution_for_fragmented_node(self, mock_prom):
        """Should return attribution dict when node is fragmented"""
        mock_prom.query_instant.return_value = []
        
        node_analysis = {
            'node': {'name': 'test-node'},
            'fragmentation_analysis': {
                'cpu_fragmentation': 0.5,  # Above threshold
                'memory_fragmentation': 0.4
            },
            'allocatable_facts': {
                'cpu_allocatable': 4.0,
                'memory_allocatable': 8 * 1024**3
            }
        }
        
        result = analyze_fragmentation_attribution(
            'test-node',
            node_analysis,
            [node_analysis]
        )
        
        assert result is not None
        assert 'large_request_pods' in result
        assert 'constraint_blockers' in result
        assert 'daemonset_overhead' in result
        assert 'scale_down_blockers' in result


class TestLargeRequestPods:
    """Tests for large request pod detection"""
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_detects_large_cpu_pod(self, mock_prom):
        """Should detect pods with large CPU requests"""
        # Mock pod with 2 cores on a 4-core node (50% > 25% threshold)
        mock_prom.query_instant.side_effect = [
            # CPU requests query
            [{
                'metric': {
                    'pod': 'large-pod',
                    'namespace': 'default',
                    'created_by_kind': 'Deployment',
                    'created_by_name': 'large-app'
                },
                'value': [0, '2.0']  # 2 cores
            }],
            # Memory requests query
            [{
                'metric': {'pod': 'large-pod'},
                'value': [0, str(1 * 1024**3)]  # 1GB
            }]
        ]
        
        other_nodes = [{
            'node': {'name': 'other-node'},
            'allocatable_facts': {'cpu_allocatable': 4.0, 'memory_allocatable': 8 * 1024**3},
            'request_facts': {'cpu_requested_total': 3.5, 'memory_requested_total': 6 * 1024**3}
        }]
        
        result = _find_large_request_pods(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3,
            all_nodes_analysis=other_nodes
        )
        
        assert len(result) == 1
        assert result[0]['pod_name'] == 'large-pod'
        assert result[0]['request_cpu'] == 2.0
        assert 'CPU request' in result[0]['reason']
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_detects_pod_that_cannot_fit_elsewhere(self, mock_prom):
        """Should detect pods that cannot fit on any other node"""
        mock_prom.query_instant.side_effect = [
            # CPU requests
            [{
                'metric': {
                    'pod': 'unmovable-pod',
                    'namespace': 'default',
                    'created_by_kind': 'Deployment',
                    'created_by_name': 'unmovable-app'
                },
                'value': [0, '3.0']
            }],
            # Memory requests
            [{
                'metric': {'pod': 'unmovable-pod'},
                'value': [0, str(6 * 1024**3)]
            }]
        ]
        
        # Other node has very little free capacity
        other_nodes = [{
            'node': {'name': 'other-node'},
            'allocatable_facts': {'cpu_allocatable': 4.0, 'memory_allocatable': 8 * 1024**3},
            'request_facts': {'cpu_requested_total': 3.9, 'memory_requested_total': 7.5 * 1024**3}
        }]
        
        result = _find_large_request_pods(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3,
            all_nodes_analysis=other_nodes
        )
        
        assert len(result) == 1
        assert result[0]['can_fit_elsewhere'] is False
        assert 'Cannot fit on any other node' in result[0]['reason']
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_ignores_small_pods(self, mock_prom):
        """Should not flag pods below the threshold"""
        mock_prom.query_instant.side_effect = [
            # Small CPU request
            [{
                'metric': {'pod': 'small-pod', 'namespace': 'default'},
                'value': [0, '0.1']  # 0.1 cores (2.5% of 4 cores)
            }],
            # Small memory request
            [{
                'metric': {'pod': 'small-pod'},
                'value': [0, str(256 * 1024**2)]  # 256MB
            }]
        ]
        
        result = _find_large_request_pods(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3,
            all_nodes_analysis=[]
        )
        
        assert len(result) == 0


class TestDaemonSetOverhead:
    """Tests for DaemonSet overhead calculation"""
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_calculates_overhead_percentage(self, mock_prom):
        """Should correctly calculate DaemonSet overhead percentage"""
        mock_prom.query_instant.side_effect = [
            # CPU requests from DaemonSets
            [
                {
                    'metric': {'created_by_name': 'node-exporter'},
                    'value': [0, '0.5']  # 0.5 cores
                },
                {
                    'metric': {'created_by_name': 'fluentd'},
                    'value': [0, '0.3']  # 0.3 cores
                }
            ],
            # Memory requests from DaemonSets
            [
                {
                    'metric': {'created_by_name': 'node-exporter'},
                    'value': [0, str(256 * 1024**2)]
                },
                {
                    'metric': {'created_by_name': 'fluentd'},
                    'value': [0, str(512 * 1024**2)]
                }
            ]
        ]
        
        result = _calculate_daemonset_overhead(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3
        )
        
        # 0.8 / 4.0 = 20% CPU
        assert result['cpu_percent'] == 20.0
        assert result['exceeds_threshold'] is True  # Default threshold is 15%
        assert 'node-exporter' in result['contributing_daemonsets']
        assert 'fluentd' in result['contributing_daemonsets']
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_below_threshold_not_flagged(self, mock_prom):
        """Should not flag overhead below threshold"""
        mock_prom.query_instant.side_effect = [
            # Small CPU usage
            [{'metric': {'created_by_name': 'ds1'}, 'value': [0, '0.1']}],
            # Small memory usage
            [{'metric': {'created_by_name': 'ds1'}, 'value': [0, str(100 * 1024**2)]}]
        ]
        
        result = _calculate_daemonset_overhead(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3
        )
        
        assert result['exceeds_threshold'] is False
        assert result['contributing_daemonsets'] == []
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_handles_empty_results(self, mock_prom):
        """Should handle nodes with no DaemonSet pods"""
        mock_prom.query_instant.return_value = []
        
        result = _calculate_daemonset_overhead(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3
        )
        
        assert result['cpu_percent'] == 0.0
        assert result['memory_percent'] == 0.0
        assert result['exceeds_threshold'] is False


class TestConstraintBlockers:
    """Tests for constraint blocker detection"""
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_detects_topology_constraints(self, mock_prom):
        """Should detect pods with topology spread constraints"""
        mock_prom.query_instant.side_effect = [
            # Pods on node
            [{
                'metric': {
                    'pod': 'constrained-pod',
                    'namespace': 'default',
                    'created_by_kind': 'Deployment',
                    'created_by_name': 'constrained-app'
                }
            }],
            # Pod labels with topology indicator
            [{
                'metric': {
                    'pod': 'constrained-pod',
                    'label_topology_kubernetes_io_zone': 'us-east-1a'
                }
            }]
        ]
        
        result = _find_constraint_blockers('test-node')
        
        assert len(result) >= 1
        # Check that topology constraint was detected
        constrained = [b for b in result if b['pod_name'] == 'constrained-pod']
        assert len(constrained) > 0
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_records_unknown_visibility_when_no_data(self, mock_prom):
        """Should record constraint_visibility: unknown when data unavailable"""
        mock_prom.query_instant.side_effect = [
            # Pod exists
            [{
                'metric': {
                    'pod': 'mystery-pod',
                    'namespace': 'default',
                    'created_by_kind': 'Deployment',
                    'created_by_name': 'mystery-app'
                }
            }],
            # No label data
            []
        ]
        
        result = _find_constraint_blockers('test-node')
        
        # Should have recorded with unknown visibility
        mystery_pods = [b for b in result if b['pod_name'] == 'mystery-pod']
        assert len(mystery_pods) >= 1
        assert mystery_pods[0]['constraint_visibility'] == 'unknown'


class TestScaleDownBlockers:
    """Tests for scale-down blocker detection"""
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_detects_unmovable_pod(self, mock_prom):
        """Should detect pods that cannot move to any other node"""
        mock_prom.query_instant.side_effect = [
            # Pod info
            [{
                'metric': {
                    'pod': 'blocker-pod',
                    'namespace': 'default',
                    'created_by_kind': 'Deployment',
                    'created_by_name': 'blocker-app'
                }
            }],
            # CPU requests
            [{
                'metric': {'pod': 'blocker-pod', 'namespace': 'default'},
                'value': [0, '3.5']
            }],
            # Memory requests
            [{
                'metric': {'pod': 'blocker-pod', 'namespace': 'default'},
                'value': [0, str(7 * 1024**3)]
            }],
            # PDB query (empty)
            []
        ]
        
        # Other node has very little capacity
        other_nodes = [{
            'node': {'name': 'other-node'},
            'allocatable_facts': {'cpu_allocatable': 4.0, 'memory_allocatable': 8 * 1024**3},
            'request_facts': {'cpu_requested_total': 3.8, 'memory_requested_total': 7.5 * 1024**3}
        }]
        
        result = _find_scale_down_blockers(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3,
            all_nodes_analysis=other_nodes
        )
        
        assert len(result) >= 1
        blocker = [b for b in result if b['pod_name'] == 'blocker-pod'][0]
        assert 'cannot fit on any other node' in blocker['blocking_reason']
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_detects_pdb_protected_pod(self, mock_prom):
        """Should detect pods protected by PDB with 0 disruptions allowed"""
        mock_prom.query_instant.side_effect = [
            # Pod info
            [{
                'metric': {
                    'pod': 'protected-pod',
                    'namespace': 'critical',
                    'created_by_kind': 'Deployment',
                    'created_by_name': 'critical-app'
                }
            }],
            # CPU requests
            [{
                'metric': {'pod': 'protected-pod', 'namespace': 'critical'},
                'value': [0, '0.5']
            }],
            # Memory requests
            [{
                'metric': {'pod': 'protected-pod', 'namespace': 'critical'},
                'value': [0, str(512 * 1024**2)]
            }],
            # PDB with 0 disruptions allowed
            [{
                'metric': {
                    'namespace': 'critical',
                    'poddisruptionbudget': 'critical-pdb'
                },
                'value': [0, '0']
            }]
        ]
        
        # Other node has plenty of capacity (pod could fit)
        other_nodes = [{
            'node': {'name': 'other-node'},
            'allocatable_facts': {'cpu_allocatable': 4.0, 'memory_allocatable': 8 * 1024**3},
            'request_facts': {'cpu_requested_total': 1.0, 'memory_requested_total': 2 * 1024**3}
        }]
        
        result = _find_scale_down_blockers(
            'test-node',
            cpu_allocatable=4.0,
            mem_allocatable=8 * 1024**3,
            all_nodes_analysis=other_nodes
        )
        
        # Should have detected the PDB blocker
        pdb_blockers = [b for b in result if 'PDB' in b.get('blocking_reason', '')]
        assert len(pdb_blockers) >= 1


class TestIntegration:
    """Integration tests for fragmentation attribution"""
    
    @patch('analysis.fragmentation_attribution.prom')
    def test_full_attribution_flow_fragmented_node(self, mock_prom):
        """Test complete attribution for a fragmented node with multiple causes"""
        # Set up mock to return different data for different queries
        mock_prom.query_instant.return_value = []
        
        node_analysis = {
            'node': {'name': 'fragmented-node'},
            'fragmentation_analysis': {
                'cpu_fragmentation': 0.45,  # Above 0.3 threshold
                'memory_fragmentation': 0.38
            },
            'allocatable_facts': {
                'cpu_allocatable': 8.0,
                'memory_allocatable': 16 * 1024**3
            },
            'request_facts': {
                'cpu_requested_total': 6.0,
                'memory_requested_total': 12 * 1024**3
            }
        }
        
        all_nodes = [
            node_analysis,
            {
                'node': {'name': 'other-node'},
                'allocatable_facts': {'cpu_allocatable': 8.0, 'memory_allocatable': 16 * 1024**3},
                'request_facts': {'cpu_requested_total': 7.5, 'memory_requested_total': 15 * 1024**3}
            }
        ]
        
        result = analyze_fragmentation_attribution(
            'fragmented-node',
            node_analysis,
            all_nodes
        )
        
        # Should return attribution structure
        assert result is not None
        assert isinstance(result['large_request_pods'], list)
        assert isinstance(result['constraint_blockers'], list)
        assert isinstance(result['daemonset_overhead'], dict)
        assert isinstance(result['scale_down_blockers'], list)
        
        # DaemonSet overhead should have required keys
        assert 'cpu_percent' in result['daemonset_overhead']
        assert 'memory_percent' in result['daemonset_overhead']
        assert 'exceeds_threshold' in result['daemonset_overhead']
