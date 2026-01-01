# Phase 2: Kubernetes Cluster Analysis Request

You are a Large Language Model acting as a senior Kubernetes platform engineer.

You are running in Phase 2 of a Kubernetes analysis system.

Your input is a single JSON document named analysis_output.json.
This document contains verified facts, metrics, flags, and safety decisions
produced by a deterministic Phase-1 analysis pipeline.

You MUST treat this input as correct and authoritative.

Your role is to EXPLAIN the analysis to a human.
You must NOT perform analysis, calculations, or data collection.

## Rules you must follow:

- Do NOT query Prometheus.
- Do NOT query Kubernetes.
- Do NOT recompute metrics or percentiles.
- Do NOT override safety flags.
- Do NOT invent missing data.
- Do NOT suggest automation or direct actions.

If the input indicates insufficient data or low confidence,
you must clearly state that limitation.

## Your tasks:

1. Summarize the overall cluster state.
2. Identify repeated patterns across deployments, HPAs, and nodes.
3. Explain cause-and-effect relationships already present in the data.
4. Highlight risks and why they matter.
5. Propose action candidates for human review only.
6. State uncertainty and data limitations explicitly.

## Analysis Data

```json
{
  "generated_at": "2026-01-01T18:16:14.273923Z",
  "cluster_summary": {
    "deployment_count": 3,
    "hpa_count": 2,
    "node_count": 2
  },
  "analysis_scope": {
    "deployments": {
      "api-server": "default",
      "web-frontend": "default",
      "background-worker": "batch"
    },
    "hpas": {
      "api-server": "default",
      "web-frontend": "default"
    },
    "nodes": {
      "node-1": "worker-1",
      "node-2": "worker-2"
    }
  },
  "deployment_analysis": [
    {
      "deployment": {
        "name": "api-server",
        "namespace": "default",
        "replicas": {
          "desired": 3,
          "ready": 3,
          "updated": 3
        }
      },
      "resource_usage": {
        "cpu": {
          "avg_cores": 0.45,
          "p95_cores": 1.2,
          "p99_cores": 2.1,
          "max_cores": 2.5
        },
        "memory": {
          "avg_bytes": 512000000,
          "p95_bytes": 800000000,
          "p99_bytes": 950000000,
          "max_bytes": 1000000000
        }
      },
      "request_allocation": {
        "cpu_requests": "500m",
        "memory_requests": "512Mi",
        "cpu_utilization_percent": 90,
        "memory_utilization_percent": 102
      },
      "behavior_flags": [
        "BURSTY",
        "CPU_BURSTY"
      ],
      "pending_pods_count": 0,
      "unsafe_to_resize": false
    },
    {
      "deployment": {
        "name": "web-frontend",
        "namespace": "default",
        "replicas": {
          "desired": 5,
          "ready": 5,
          "updated": 5
        }
      },
      "resource_usage": {
        "cpu": {
          "avg_cores": 0.08,
          "p95_cores": 0.15,
          "p99_cores": 0.2,
          "max_cores": 0.25
        },
        "memory": {
          "avg_bytes": 128000000,
          "p95_bytes": 150000000,
          "p99_bytes": 160000000,
          "max_bytes": 170000000
        }
      },
      "request_allocation": {
        "cpu_requests": "250m",
        "memory_requests": "256Mi",
        "cpu_utilization_percent": 32,
        "memory_utilization_percent": 50
      },
      "behavior_flags": [
        "UNDERUTILIZED"
      ],
      "pending_pods_count": 0,
      "unsafe_to_resize": false
    },
    {
      "deployment": {
        "name": "background-worker",
        "namespace": "batch",
        "replicas": {
          "desired": 2,
          "ready": 2,
          "updated": 2
        }
      },
      "resource_usage": {
        "cpu": {
          "avg_cores": 1.5,
          "p95_cores": 1.8,
          "p99_cores": 2.0,
          "max_cores": 2.2
        },
        "memory": {
          "avg_bytes": 2000000000,
          "p95_bytes": 2200000000,
          "p99_bytes": 2300000000,
          "max_bytes": 2400000000
        }
      },
      "request_allocation": {
        "cpu_requests": "2000m",
        "memory_requests": "2Gi",
        "cpu_utilization_percent": 75,
        "memory_utilization_percent": 100
      },
      "behavior_flags": [
        "HEALTHY"
      ],
      "pending_pods_count": 0,
      "unsafe_to_resize": true
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
        "scaling_blocked": false
      },
      "scaling_flags": [
        "AT_CPU_THRESHOLD"
      ],
      "recommendations": "Monitor CPU trend; may scale up within next 5 minutes"
    },
    {
      "hpa": {
        "name": "web-frontend",
        "namespace": "default",
        "target_deployment": "web-frontend"
      },
      "scaling_config": {
        "min_replicas": 2,
        "max_replicas": 20,
        "current_replicas": 5,
        "desired_replicas": 2
      },
      "scaling_status": "HEALTHY",
      "scaling_behavior": {
        "description": "Scaling down due to low request rate",
        "current_load": 25,
        "scaling_blocked": false
      },
      "scaling_flags": [
        "SCALING_DOWN_PENDING"
      ],
      "recommendations": "Safe to downscale; deployment underutilized"
    }
  ],
  "node_analysis": [
    {
      "node": {
        "name": "node-1",
        "labels": {
          "kubernetes.io/hostname": "node-1",
          "node-role.kubernetes.io/worker": "true"
        }
      },
      "insufficient_data": false,
      "capacity_facts": {
        "cpu_cores": 4,
        "memory_bytes": 8000000000,
        "ephemeral_storage_bytes": 50000000000,
        "pods_max": 110
      },
      "allocatable_facts": {
        "cpu_allocatable": 3.9,
        "memory_allocatable": 7500000000,
        "pods_allocatable": 110
      },
      "request_facts": {
        "cpu_requested_total": 2.75,
        "memory_requested_total": 3000000000,
        "pods_requested_count": 12
      },
      "utilization_facts": {
        "cpu_usage_cores": 2.1,
        "memory_usage_bytes": 2500000000,
        "pod_count": 12
      },
      "fragmentation_analysis": {
        "pod_packing_efficiency": 0.76,
        "memory_fragmentation": 0.34,
        "cpu_fragmentation": 0.45
      },
      "scheduling_facts": {
        "pods_pending": 0,
        "pods_failed": 0
      },
      "node_conditions": {
        "ready": true,
        "memory_pressure": false,
        "disk_pressure": false,
        "pid_pressure": false
      }
    },
    {
      "node": {
        "name": "node-2",
        "labels": {
          "kubernetes.io/hostname": "node-2",
          "node-role.kubernetes.io/worker": "true"
        }
      },
      "insufficient_data": false,
      "capacity_facts": {
        "cpu_cores": 4,
        "memory_bytes": 8000000000,
        "ephemeral_storage_bytes": 50000000000,
        "pods_max": 110
      },
      "allocatable_facts": {
        "cpu_allocatable": 3.9,
        "memory_allocatable": 7500000000,
        "pods_allocatable": 110
      },
      "request_facts": {
        "cpu_requested_total": 2.25,
        "memory_requested_total": 2500000000,
        "pods_requested_count": 10
      },
      "utilization_facts": {
        "cpu_usage_cores": 1.8,
        "memory_usage_bytes": 2100000000,
        "pod_count": 10
      },
      "fragmentation_analysis": {
        "pod_packing_efficiency": 0.68,
        "memory_fragmentation": 0.42,
        "cpu_fragmentation": 0.52
      },
      "scheduling_facts": {
        "pods_pending": 0,
        "pods_failed": 0
      },
      "node_conditions": {
        "ready": true,
        "memory_pressure": false,
        "disk_pressure": false,
        "pid_pressure": false
      }
    }
  ],
  "cross_layer_observations": [
    {
      "observation": "Memory utilization concern in background-worker deployment",
      "scope": "Deployment + Node",
      "details": "background-worker uses 100% of allocated memory (2Gi) consistently. This deployment is marked unsafe_to_resize, limiting horizontal scaling options.",
      "risk_level": "High",
      "affected_components": [
        "background-worker",
        "node-1",
        "node-2"
      ]
    },
    {
      "observation": "Overprovisioned web-frontend across cluster",
      "scope": "Cluster",
      "details": "web-frontend has 5 replicas but using only 25-32% of allocated CPU. HPA is attempting to scale down to 2 replicas. Downscaling is safe and recommended.",
      "risk_level": "Low",
      "affected_components": [
        "web-frontend",
        "node-1",
        "node-2"
      ]
    },
    {
      "observation": "API server experiencing CPU burstiness",
      "scope": "Deployment",
      "details": "api-server shows BURSTY and CPU_BURSTY flags. P99 CPU (2.1 cores) is significantly higher than average (0.45). Memory also shows overutilization (102%). HPA is active and monitoring for scale-up.",
      "risk_level": "Medium",
      "affected_components": [
        "api-server"
      ]
    }
  ]
}
```

## Required Response Format

You must output JSON ONLY with the following structure:

```json
{
  "cluster_summary": "string: 2-3 sentences summarizing overall cluster health",
  "patterns": [
    {
      "pattern_id": "string: unique identifier",
      "description": "string: what pattern was observed",
      "affected_objects": ["string: list of deployment/HPA/node names"],
      "evidence": ["string: specific metrics or flags supporting this pattern"]
    }
  ],
  "warnings": [
    {
      "warning_id": "string: unique identifier",
      "severity": "Low | Medium | High",
      "scope": "Deployment | HPA | Node | Cluster",
      "description": "string: what is the risk",
      "evidence": ["string: metrics or flags from Phase 1"],
      "confidence": "Low | Medium | High"
    }
  ],
  "action_candidates": [
    {
      "action_id": "string: unique identifier",
      "scope": "Deployment | HPA | Node | Cluster",
      "description": "string: what action could be considered",
      "expected_impact": "string: what would change if this action was taken",
      "prerequisites": ["string: conditions that must be true first"],
      "blocked_by": ["string: what Phase-1 flags or conditions prevent this action"],
      "confidence": "Low | Medium | High"
    }
  ],
  "priorities": "string: prioritized summary of which issues matter most",
  "limitations": ["string: what data is missing, what confidence is low, what assumptions were made"]
}
```

## CRITICAL RULES:

- Output ONLY JSON. No markdown, no code blocks, no explanatory text.
- Use ALL fields exactly as specified.
- If an array is empty, use [].
- Do NOT suggest actions that Phase-1 marked as unsafe (safe_to_resize=false, unsafe_to_resize=true).
- If Phase-1 shows insufficient_data, explicitly mention it in limitations and warnings.
- Behave like a cautious senior engineer explaining a report in a review meeting.
