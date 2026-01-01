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
