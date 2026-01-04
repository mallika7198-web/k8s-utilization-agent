k8s-utilization-agent — Phases 1 & 2

## Phase 1: Deterministic Analysis (COMPLETE)

This repository implements Phase 1: deterministic collection and analysis of Kubernetes metrics via Prometheus.
Prometheus is the single source of truth. No Kubernetes API access. All configuration via `config.py`.

### Quick Start

Run all tests (60 passing):
```bash
python -m pip install -r requirements.txt
pytest -q
```

Run orchestrator (generates `analysis_output.json`):
```bash
python orchestrator.py
```

**Requirements:** Local Prometheus at http://localhost:9090

### Phase 1 Architecture

- **Analysis Layer** (Python): Deterministic, testable, config-driven
  - `metrics/discovery.py` — find deployments, nodes, HPAs via PromQL
  - `metrics/prometheus_client.py` — query Prometheus
  - `normalize/` — convert raw metrics to domain objects
  - `analysis/` — compute facts, ratios, flags, safety classification
  - `normalize/math.py` — percentiles, burst detection, fragmentation logic

- **Output** (`analysis_output.json`):
  - `deployment_analysis[]` — per-deployment resource usage, burst flags, safety classification
  - `hpa_analysis[]` — HPA utilization, safety flags
  - `node_analysis[]` — per-node fragmentation, pressure

### Configuration

All runtime values controlled via `config.py`:
- `PROMETHEUS_URL` (default: `http://localhost:9090`)
- `PROMETHEUS_TIMEOUT_SECONDS` (default: 30)
- `OBSERVATION_WINDOW_MINUTES` (default: 15)
- `PERCENTILE_THRESHOLDS` (burst detection)
- `PHASE2_ENABLED` (default: False)

Override via environment variables:
```bash
PROMETHEUS_URL=http://my-prometheus:9090 PHASE2_ENABLED=true python orchestrator.py
```

---

## Phase 2: LLM-Based Insights (IN PROGRESS)

LLM analysis layer using local Ollama (llama3:8b).
Validates all output against Phase 1 facts. No recomputation. No overrides.

### Phase 2 Architecture

- **LLM Client** (`phase2/llm_client.py`): HTTP client for Ollama `/api/generate`
- **Validator** (`phase2/validator.py`): 8-layer validation with Phase 1 safety cross-checks
  - Structural: 6 exact top-level keys required
  - Type: string/array/object enforcement
  - Warnings: 6 required fields per warning (warning_id, severity, scope, description, evidence, confidence)
  - Action Candidates: 7 required fields (action_id, scope, description, expected_impact, prerequisites, blocked_by, confidence)
  - Safety: Prevent unsafe actions, require insufficient_data mentions
- **Runner** (`phase2/runner.py`): Orchestrates LLM analysis → validation → insights output

### Phase 2 Output Schema

`insights_output.json`:
```json
{
  "generated_at": "ISO8601",
  "phase2_enabled": true,
  "analysis_reference": "path to analysis_output.json",
  "insights": {
    "cluster_summary": "string",
    "patterns": [{"pattern": "value"}],
    "warnings": [
      {
        "warning_id": "string",
        "severity": "Low|Medium|High",
        "scope": "Deployment|HPA|Node|Cluster",
        "description": "string",
        "evidence": ["metric1", "metric2"],
        "confidence": "Low|Medium|High"
      }
    ],
    "action_candidates": [
      {
        "action_id": "string",
        "scope": "Deployment|HPA|Node|Cluster",
        "description": "string",
        "expected_impact": "string",
        "prerequisites": ["req1"],
        "blocked_by": ["block1"],
        "confidence": "Low|Medium|High"
      }
    ],
    "priorities": "string",
    "limitations": ["limit1", "limit2"]
  }
}
```

### Enable Phase 2

```bash
PHASE2_ENABLED=true python orchestrator.py
```

Requires local Ollama:
```bash
ollama run llama3:8b
```

### Manual LLM Prompt (ChatGPT/Claude Alternative)

If Phase 2 fails or you want to use ChatGPT/Claude UI instead:

**Step 1:** Copy this prompt into ChatGPT/Claude:

```
OUTPUT ONLY THIS JSON STRUCTURE (replace placeholders with actual data from input):

{"summary":"Cluster status summary here","deployment_review":{"bursty":[],"underutilized":["coredns (CPU and memory underutilized)"],"memory_pressure":[],"unsafe_to_resize":[]},"hpa_review":{"at_threshold":[],"scaling_blocked":[],"scaling_down":[]},"node_fragmentation_review":{"fragmented_nodes":["demo-control-plane (87% CPU, 90% memory fragmentation)"],"large_request_pods":[],"constraint_blockers":[],"daemonset_overhead":[],"scale_down_blockers":[]},"cross_layer_risks":{"high":[],"medium":[]},"limitations":[]}

RULES:
- Replace example values with actual data from input
- Keep the EXACT structure and key names
- Use [] for empty arrays
- NO markdown, NO explanation, ONLY the JSON object
- Start with { and end with }

INPUT DATA:
```

**Step 2:** Append the simplified analysis data (from `output/{cluster}_analysis_output.json`):

```json
{
  "cluster_summary": { "deployment_count": 6, "hpa_count": 4, "node_count": 1 },
  "deployments": [
    { "name": "coredns", "namespace": "kube-system", "replicas": 2, "flags": ["CPU_UNDERUTILIZED", "MEMORY_UNDERUTILIZED"] },
    { "name": "web-b", "namespace": "metrics-demo", "replicas": 2, "flags": [] }
  ],
  "hpas": [
    { "name": "web-a-hpa", "namespace": "metrics-demo", "current_replicas": 1, "min_replicas": 1, "max_replicas": 5, "at_min": true, "flags": ["AT_MIN_REPLICAS"] }
  ],
  "nodes": [
    { "name": "demo-control-plane", "cpu_fragmentation": 0.87, "memory_fragmentation": 0.90, "pod_packing_efficiency": 0.14 }
  ]
}
```

**Step 3:** Copy the JSON response and save to `output/{cluster}_insights_output.json`:

```json
{
  "generated_at": "2026-01-04T14:00:00Z",
  "analysis_reference": "output/local-kind_analysis_output.json",
  "phase2_enabled": true,
  "llm_mode": "manual",
  "llm_model": "chatgpt-4",
  "insights": {
    // paste LLM response here
  }
}
```

### Remote LLM Configuration (oss-gpt-120b)

For production with remote LLM:

```bash
export LLM_MODE=remote
export LLM_MODEL_NAME=oss-gpt-120b
export LLM_ENDPOINT_URL=https://your-llm-endpoint.example.com
export LLM_API_KEY=your-api-key-here
export LLM_TIMEOUT_SECONDS=180
export PHASE2_ENABLED=true

python phase2/runner.py
```

---

### Test Coverage

- **Phase 1**: 30 tests (math, percentiles, burst detection, fragmentation, analysis)
- **Phase 2**: 30 tests (LLM client, validator layers, safety checks, schema enforcement)
- **Total**: 60 passing tests

Run specific tests:
```bash
pytest tests/test_phase2.py -v          # Phase 2 only
pytest tests/test_math.py tests/test_deployment_analysis.py -v  # Phase 1 specific
```

---

### Source of Truth & Safety Rules

**Prometheus is immutable source of truth.**

Phase 2 validator enforces:
1. Cannot override Phase 1 safety flags (safe_to_resize, insufficient_data)
2. Cannot suggest resize actions on unsafe deployments
3. Must mention insufficient_data in limitations if Phase 1 indicates missing data
4. JSON schema strictly enforced (no extra fields, all required fields present)
5. All actions blocked if confidence is Low and prerequisites unmet

**File:** `tracker.json` (append-only audit log of all changes)

---

## Analysis Output Explained

### Why are Requests/Limits missing?

The current analysis focuses on **actual usage** from Prometheus, not Kubernetes resource specifications:

| Field | Source | Status |
|-------|--------|--------|
| `cpu_avg_cores`, `memory_avg_bytes` | `container_cpu_usage_seconds_total`, `container_memory_usage_bytes` | ✅ Collected |
| `cpu_requests`, `memory_requests` | `kube_pod_container_resource_requests` | ⚠️ Not yet in deployment_analysis |
| `cpu_limits`, `memory_limits` | `kube_pod_container_resource_limits` | ⚠️ Not yet in deployment_analysis |

**Why this matters:**
- Current data shows **what the pods actually use**
- Requests/limits show **what the pods are configured to use**
- Comparing both reveals over-provisioning (requests >> usage) or under-provisioning (usage >> requests)

**To add requests/limits**, the deployment analysis needs to query:
```promql
kube_pod_container_resource_requests{resource="cpu", pod=~".*deployment-name.*"}
kube_pod_container_resource_limits{resource="memory", pod=~".*deployment-name.*"}
```

### Why do CPU and Memory metric counts differ?

Example from analysis:
```
"evidence": [
  "1 pod(s) found for deployment prom-prometheus-server",
  "4 CPU metric points collected",    # Different!
  "4 memory metric points collected"  # Same
]
```

vs:
```
"evidence": [
  "1 pod(s) found for deployment prom-kube-state-metrics",
  "3 CPU metric points collected",    # Different!
  "3 memory metric points collected"
]
```

**Explanation:**

1. **Scrape timing**: Prometheus scrapes CPU and memory at regular intervals, but if a pod just started or restarted, it may have fewer data points

2. **Multiple containers**: A pod with 2 containers = 2x metric series. `prom-prometheus-server` has more containers than `prom-kube-state-metrics`

3. **Query window**: The 15-minute window (`METRICS_WINDOW_MINUTES`) captures different amounts of data based on when the pod started

4. **Counter resets**: CPU is a counter (`rate()`), memory is a gauge. Counter resets on restart affect available data points

**What the numbers mean:**
- `3 CPU metric points` = 3 time-series samples in the 15-min window (at 1-min step = ~3 minutes of data)
- `6 CPU metric points` for `web-b` = 2 pods × 3 samples each, or 1 pod with 6 samples

**For `web-b` (2 replicas):**
```
"6 CPU metric points collected"    # 2 pods × ~3 samples each
"6 memory metric points collected" # 2 pods × ~3 samples each
```

This is expected - more pods = more metric points.

