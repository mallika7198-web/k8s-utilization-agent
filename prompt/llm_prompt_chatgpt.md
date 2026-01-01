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
  "generated_at": "2026-01-01T18:00:56.291217+00:00",
  "cluster_summary": {
    "deployment_count": 0,
    "hpa_count": 0,
    "node_count": 1
  },
  "analysis_scope": {
    "deployments": {},
    "hpas": {},
    "nodes": {}
  },
  "deployment_analysis": [],
  "hpa_analysis": [],
  "node_analysis": [
    {
      "node": {
        "name": "demo-control-plane",
        "labels": {
          "__name__": "node_uname_info",
          "app_kubernetes_io_component": "metrics",
          "app_kubernetes_io_instance": "prom",
          "app_kubernetes_io_managed_by": "Helm",
          "app_kubernetes_io_name": "prometheus-node-exporter",
          "app_kubernetes_io_part_of": "prometheus-node-exporter",
          "app_kubernetes_io_version": "1.10.2",
          "domainname": "(none)",
          "helm_sh_chart": "prometheus-node-exporter-4.49.2",
          "instance": "172.18.0.2:9100",
          "job": "kubernetes-service-endpoints",
          "machine": "aarch64",
          "namespace": "monitoring",
          "node": "demo-control-plane",
          "nodename": "demo-control-plane",
          "release": "6.10.14-linuxkit",
          "service": "prom-prometheus-node-exporter",
          "sysname": "Linux",
          "version": "#1 SMP Sat May 17 08:28:57 UTC 2025"
        }
      },
      "insufficient_data": false,
      "evidence": [
        "Node demo-control-plane has 20.0 pods scheduled"
      ],
      "capacity_facts": {
        "cpu_cores": null,
        "memory_bytes": null,
        "ephemeral_storage_bytes": null,
        "pods_max": 110
      },
      "allocatable_facts": {
        "cpu_allocatable": null,
        "memory_allocatable": null,
        "pods_allocatable": 110
      },
      "request_facts": {
        "cpu_requested_total": null,
        "memory_requested_total": null,
        "pods_requested_count": 20.0
      },
      "utilization_facts": {
        "cpu_usage_cores": 0.12575745501334604,
        "memory_available_bytes": null,
        "pod_count": 20.0
      },
      "fragmentation_analysis": {
        "pod_packing_efficiency": null,
        "memory_fragmentation": null,
        "cpu_fragmentation": null
      },
      "scheduling_facts": {},
      "node_conditions": {
        "ready": true,
        "memory_pressure": false,
        "disk_pressure": false,
        "pid_pressure": false
      }
    }
  ],
  "cross_layer_observations": []
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
- Do NOT suggest actions that Phase-1 marked as unsafe (safe_to_resize=false).
- If Phase-1 shows insufficient_data, explicitly mention it in limitations and warnings.
- Behave like a cautious senior engineer explaining a report in a review meeting.

