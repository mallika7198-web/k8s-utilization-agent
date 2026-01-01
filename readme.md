# Kubernetes Utilization Analysis — Phase 1

Deterministic analysis of Kubernetes resource utilization via Prometheus metrics.

**Prometheus is the single source of truth.** No Kubernetes API access. No LLM. No suggestions. Facts and flags only.

## Quick Start

### Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### Run Tests (30 passing)
```bash
pytest -q
```

### Generate Analysis
```bash
python orchestrator.py
```

Output: `output/analysis_output.json` (facts, metrics, flags)

**Prerequisite:** Prometheus at `http://localhost:9090`

## Architecture

### Core Modules

- **`metrics/discovery.py`** — Discover deployments, nodes, HPAs via PromQL
- **`metrics/prometheus_client.py`** — Query Prometheus (timeout-aware)
- **`normalize/math.py`** — Compute percentiles (P50, P95, P99, P100), burst detection, memory growth
- **`normalize/fragmentation.py`** — Detect node fragmentation patterns
- **`normalize/series.py`** — Time-series operations (interpolation, filtering)
- **`analysis/deployment_analysis.py`** — Per-deployment safety classification, burst flags, over-provisioning detection
- **`analysis/hpa_analysis.py`** — HPA safety classification, scaling readiness
- **`analysis/node_analysis.py`** — Node fragmentation, pressure detection, cluster-wide cross-layer observations

### Analysis Output

[output/analysis_output.json](output/analysis_output.json) contains:

- **`deployment_analysis[]`** — Per deployment:
  - Resource usage (avg, P95, P99, P100) for CPU and memory
  - Burst detection (P100/P95 ratio) and memory growth trends
  - Over-provisioning ratio (request vs actual usage)
  - Safety classification: `SAFE`, `CAUTION`, `RESTRICTED`
  - Confidence scores for each flag

- **`hpa_analysis[]`** — Per HPA:
  - Current replicas, min/max configuration
  - Scaling readiness and safety status

- **`node_analysis[]`** — Per node:
  - CPU/memory fragmentation (unused slots that can't fit pending pods)
  - Pressure indicators (DiskPressure, MemoryPressure, etc.)
  - Capacity and allocatable resources

- **`cross_layer_observations[]`** — Cluster-wide patterns:
  - Overprovisioned deployments vs fragmented nodes
  - HPA scaling blockages due to node fragmentation
  - Workload distribution imbalances

## Configuration

All runtime values in `config.py` (overridable via environment variables):

| Setting | Default | Override Env Var |
|---------|---------|------------------|
| Prometheus URL | `http://localhost:9090` | `PROMETHEUS_URL` |
| Timeout (seconds) | 30 | `PROMETHEUS_TIMEOUT_SECONDS` |
| Metrics window | 15 minutes | `METRICS_WINDOW_MINUTES` |
| Min observation window | 10 minutes | `MIN_OBSERVATION_WINDOW_MINUTES` |
| CPU burst threshold | 2.0 (P100/P95 ratio) | `CPU_BURST_RATIO_THRESHOLD` |
| Memory growth threshold | 10% | `MEMORY_GROWTH_THRESHOLD_PERCENT` |
| Max overprovision ratio | 5.0x | `MAX_ACCEPTABLE_OVERPROVISION_RATIO` |
| Excluded namespaces | kube-system, kube-public, istio-system | `EXCLUDED_NAMESPACES` |
| Output path | `output/analysis_output.json` | `ANALYSIS_OUTPUT_PATH` |

Example:
```bash
PROMETHEUS_URL=http://my-prometheus:9090 METRICS_WINDOW_MINUTES=30 python orchestrator.py
```

## Testing

- **30 tests** covering percentile calculations, burst detection, fragmentation logic, safety classification, edge cases
- Deterministic mock datasets (no live Prometheus needed for tests)
- 88% code coverage

Run tests:
```bash
pytest -q          # Quick summary
pytest -v          # Verbose
pytest --cov       # With coverage
```

## Output Files

- **[output/analysis_output.json](output/analysis_output.json)** — Real analysis from Prometheus
- **[examples/sample_analysis.json](examples/sample_analysis.json)** — Reference for development/testing
- **[output/README.md](output/README.md)** — Detailed output format documentation
- **[examples/README.md](examples/README.md)** — Using sample files in development

## Project Structure

```
.
├── config.py                          # All configuration (environment-variable-overridable)
├── orchestrator.py                    # Orchestration: discovery → analysis → atomic write
├── tracker.py                         # Change tracking (append-only audit log)
├── requirements.txt                   # Dependencies
├── metrics/
│   ├── discovery.py                   # Kubernetes discovery via PromQL
│   └── prometheus_client.py            # Prometheus HTTP client
├── normalize/
│   ├── math.py                        # Math operations (percentiles, burst, growth)
│   ├── fragmentation.py                # Fragmentation detection
│   └── series.py                      # Time-series utilities
├── analysis/
│   ├── deployment_analysis.py          # Deployment analysis & safety
│   ├── hpa_analysis.py                 # HPA analysis & safety
│   └── node_analysis.py                # Node analysis & observations
├── tests/
│   ├── test_deployment_analysis.py     # 10 tests
│   ├── test_hpa_analysis.py            # 5 tests
│   ├── test_node_analysis.py           # 5 tests
│   ├── test_math_py.py                 # 5 tests
│   └── ...                              # (30 total)
├── output/
│   ├── analysis_output.json            # Generated analysis
│   └── README.md                       # Output documentation
└── examples/
    ├── sample_analysis.json             # Reference for development
    └── README.md                        # Examples documentation
```

## Edge Cases Handled

- **Missing metrics** → Flagged as `insufficient_data`, analysis blocked
- **Lack of traffic** → Detected and reported
- **Bursty workloads** → P100/P95 ratio > threshold → CAUTION or RESTRICTED
- **Memory growth** → Trend detection over collection window
- **InitContainer spikes** → Flagged separately
- **JVM/cache behavior** → Flagged as observed pattern
- **Node fragmentation** → Explicit detection with blocked pod count
- **Strict PDBs** → Flagged if preventing scaling

## Change Tracking

All code changes logged in [tracker.json](tracker.json) (append-only):
- Timestamp
- Files modified
- Change type (config, analysis, normalization, presentation, test)
- Factual description

## How to Extend

1. **New threshold** → Add to `config.py` (with `os.getenv()` override)
2. **New metric** → Add query to `metrics/prometheus_client.py`
3. **New analysis** → Create function in `analysis/*.py`, add tests
4. **New flag type** → Extend analysis output schema and tests

All code must:
- Be deterministic (same input → same output)
- Be testable (include mock data in test)
- Reference `config.py` for all runtime values
- Update `tracker.json` on change
- Include docstrings explaining what facts are computed

## License

Internal use.

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
