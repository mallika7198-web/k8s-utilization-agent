# K8s Utilization Agent - Implementation Summary

## Overview
Complete implementation of a two-phase Kubernetes utilization analysis system with deterministic Phase 1 analysis and LLM-based Phase 2 insights generation.

## Architecture

### Phase 1: Deterministic Analysis (Prometheus-based)
**Objective**: Extract objective facts from Prometheus metrics

**Components**:
- `metrics/prometheus_client.py`: Prometheus HTTP API client
- `metrics/discovery.py`: K8s resource discovery (Deployments, HPAs, Nodes)
- `analysis/deployment_analysis.py`: Deployment resource and behavior analysis
- `analysis/hpa_analysis.py`: HPA scaling configuration and status
- `analysis/node_analysis.py`: Node capacity and scheduling facts
- `orchestrator.py`: Orchestration pipeline (discovery → analysis → output)

**Output**: `analysis_output.json`
- Cluster summary (resource counts)
- Deployment analysis (CPU/memory percentiles, behavior flags, edge cases)
- HPA analysis (scaling status, config, safety classification)
- Node analysis (capacity, utilization, scheduling)
- Cross-layer observations

### Phase 2: LLM-based Insights (Read-only reasoning)
**Objective**: Generate interpretative insights from Phase 1 facts

**Components**:
- `phase2/runner.py`: Main Phase 2 orchestrator
- `phase2/llm_client.py`: Generic HTTP client (Ollama, remote APIs)
- `phase2/validator.py`: Flexible insights validation
- `config.py`: Centralized configuration (env var overrides)

**Features**:
- Reads Phase 1 output (read-only, never modified)
- Calls LLM with structured context
- Supports local Ollama and remote LLM APIs
- Flexible JSON validation respecting Phase 1 safety flags
- Atomic output writing (no partial files)

**Output**: `insights_output.json`
- Cluster narrative summary
- Detected patterns (with evidence)
- Warnings (with severity/scope)
- Action candidates (with impact/confidence)
- Limitations and caveats

## Integration Points

### Orchestrator Pipeline
```
orchestrator.py
├── Prometheus discovery
│   ├── discover_deployments()
│   ├── discover_hpas()
│   └── discover_nodes()
│
├── Phase 1 analysis
│   ├── analyze_deployments()
│   ├── analyze_hpas()
│   └── analyze_nodes()
│
└── Write analysis_output.json (atomic)
    └── Updates tracker.json
```

### Phase 2 Pipeline
```
phase2/runner.py
├── Load analysis_output.json (read-only)
├── Prepare LLM input (structured JSON)
├── Call LLM (Ollama or remote)
├── Parse response (handles markdown, raw JSON)
├── Validate insights
├── Write insights_output.json (atomic)
└── Update tracker.json
```

## Configuration

All configuration in `config.py`, environment variable overrides:

**Phase 1**:
- `PROMETHEUS_URL`: Prometheus endpoint (default: http://localhost:9090)
- `METRICS_WINDOW_MINUTES`: Analysis window (default: 15)
- `PROMETHEUS_TIMEOUT_SECONDS`: Query timeout (default: 30)

**Phase 2**:
- `PHASE2_ENABLED`: Enable/disable Phase 2 (env var only, default: false)
- `LLM_MODE`: 'local' for Ollama or 'remote' for other APIs
- `LLM_ENDPOINT_URL`: Full endpoint URL
- `LLM_MODEL_NAME`: Model name (e.g., 'llama3:8b')
- `LLM_TIMEOUT_SECONDS`: LLM request timeout (default: 120)
- `PHASE2_LLM_PROMPT`: System prompt for LLM (defined in config.py)

## Testing

### Phase 1 Validation
```bash
# Run orchestrator (produces analysis_output.json)
python orchestrator.py

# Verify outputs
cat analysis_output.json | jq '.cluster_summary'
```

### Phase 2 Validation
```bash
# Enable Phase 2 and run (requires Ollama running on localhost:11434)
PHASE2_ENABLED=true python phase2/runner.py

# Check generated insights
cat insights_output.json | jq '.insights.patterns'
```

### Complete System Test
```bash
# Run both phases
python orchestrator.py && PHASE2_ENABLED=true python phase2/runner.py

# Validate outputs
python -c "
import json
with open('analysis_output.json') as f: a = json.load(f)
with open('insights_output.json') as f: i = json.load(f)
print(f'Phase 1: {len(a[\"deployment_analysis\"])} deployments analyzed')
print(f'Phase 2: {len(i[\"insights\"][\"patterns\"])} patterns found')
"
```

## Design Principles

### Separation of Concerns
- **Phase 1**: Facts only, deterministic, Prometheus-authoritative
- **Phase 2**: Interpretation only, advisory, never modifies facts

### Safety
- Phase 2 respects Phase 1 safety flags (safe_to_resize, confidence levels)
- No LLM hallucinations about resource names (validated)
- Read-only access to Phase 1 data
- Atomic file writes (temp file → rename)

### Reliability
- Graceful degradation on Prometheus unavailability
- Flexible LLM response parsing (handles markdown, wrapped JSON)
- Validation prevents invalid insights from overwriting valid ones
- Tracker.json for audit trail of all changes

### Flexibility
- Generic LLM client supports Ollama, OpenAI-compatible APIs
- Configuration via environment variables
- Modular analysis (discovery, deployment, HPA, node)
- Extensible validation rules

## Performance Notes

- **Prometheus queries**: 5-minute range by default, configurable
- **LLM calls**: 120s timeout (configurable), non-streaming
- **Orchestrator**: Full pipeline takes ~5-30s depending on metric volume
- **Phase 2**: LLM response time depends on model (llama3:8b ~30-60s)

## Future Enhancements

1. **Real K8s Integration**: Deploy against live clusters
2. **Advanced Metrics**: Pod QoS, resource requests/limits from API
3. **Multi-cluster**: Federated analysis across clusters
4. **Alerting**: Integration with Prometheus AlertManager
5. **Action Execution**: Safe, gated execution of recommended actions
6. **UI Dashboard**: Real-time visualization (Phase 1/Phase 2 tabs)
7. **Streaming LLM**: Non-blocking insight generation for large clusters

## Files Modified/Created

**New Files**:
- `phase2/runner.py` - Phase 2 main orchestrator
- `phase2/llm_client.py` - Generic LLM client
- `phase2/validator.py` - Insights validator
- `analysis/deployment_analysis.py` - Enhanced
- `analysis/hpa_analysis.py` - Enhanced
- `analysis/node_analysis.py` - Enhanced
- `metrics/discovery.py` - Enhanced
- `orchestrator.py` - Fixed function signatures

**Configuration**:
- `config.py` - All settings

**Outputs**:
- `analysis_output.json` - Phase 1 facts
- `insights_output.json` - Phase 2 insights
- `tracker.json` - Audit trail

## Testing Status

✅ **Phase 1**:
- Prometheus connectivity verified
- Discovery functions tested
- Analysis modules functional
- Orchestrator pipeline working

✅ **Phase 2**:
- LLM client tested with local Ollama
- JSON response parsing tested
- Validation working
- Atomic output working

✅ **Integration**:
- End-to-end pipeline tested
- Phase 1 and Phase 2 independent
- Tracker.json updated
- All 5 core modules functional

## Next Steps

1. **Deploy UI**: Run Flask dashboard
   ```bash
   python ui.py  # Visit http://127.0.0.1:8080
   ```

2. **Monitor Real Cluster**: Point at actual Prometheus
   ```bash
   export PROMETHEUS_URL=http://your-prometheus:9090
   python orchestrator.py
   ```

3. **Use Remote LLM**: Configure for production
   ```bash
   export LLM_MODE=remote
   export LLM_ENDPOINT_URL=https://api.openai.com/v1
   export LLM_MODEL_NAME=gpt-4
   PHASE2_ENABLED=true python phase2/runner.py
   ```

---

**Last Updated**: 2026-01-01  
**Status**: ✅ Complete and Tested
