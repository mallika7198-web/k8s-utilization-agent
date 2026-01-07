# Copilot Instructions for K8s Capacity Analyzer

## Project Overview

This is a **Kubernetes Capacity Analysis Tool** that provides read-only, deterministic analysis for:
- Node CPU & memory fragmentation
- Pod CPU & memory request/limit recommendations
- Node sizing direction (up/down/right-size)
- HPA misalignment detection

## Architecture

Single-file Python script (`capacity_analyzer.py`) with:
- YAML config input (`clusters.yaml`)
- JSON output per cluster (`output/<project>/<env>/analysis.json`)
- Prometheus as the only data source
- Static HTML/JS/CSS viewer (`viewer/`)

## Key Design Constraints

### 1. Environment Model
```python
env == "prod" → production
everything else → nonprod
```
- Environment affects safety factors only
- **Do NOT** infer env from Prometheus or Kubernetes

### 2. Percentile Calculation
- **All percentiles MUST come from Prometheus** (not calculated in Python)
- Use `quantile_over_time()` and `max_over_time()` PromQL functions
- Query window configured via `QUERY_WINDOW` constant (default: 7d)
- PromQL syntax: wrap `quantile_over_time` with `sum by (namespace, pod)()` for label grouping

### 3. Recommendation Types (ONLY 3)
1. `POD_RESIZE` - CPU/memory request & limit recommendations with savings calculation
2. `NODE_RIGHTSIZE` - Node sizing direction
3. `HPA_MISALIGNMENT` - Autoscaler configuration issues

### 4. Node-Scoped Calculations (CRITICAL)
- Use `kube_pod_info` to map pods → nodes
- **Never use cluster-wide totals** for node metrics
- Sum only pods scheduled on the target node

## Formulas

### POD_RESIZE
```
cpu_request_new = max(cpu_p99 × 1.20, cpu_floor)
cpu_limit_new = max(cpu_request_new × 1.50, cpu_p100 × 1.25)
memory_request_new = memory_p99 × safety_factor
memory_limit_new = max(memory_request_new × 1.50, memory_p100 × 1.25)

cpu_floor: 100m (prod), 50m (nonprod)
safety_factor: 1.15 (prod), 1.10 (nonprod)

# Savings calculation (positive = save, negative = need more)
cpu_savings = current_cpu_request - recommended_cpu_request
memory_savings = current_memory_request - recommended_memory_request
```

### NODE_RIGHTSIZE (node-scoped)
```
cpu_fragmentation = 1 - (Σ pod_cpu_p95_on_node / Σ pod_cpu_request_on_node)
node_efficiency = 0.5 × (Σ pod_cpu_p95_on_node / node_cpu_capacity)
                + 0.5 × (node_memory_usage / node_memory_capacity)
```

### HPA_MISALIGNMENT Detection Rules
1. CPU-based HPA with low CPU usage (`avg_cpu << cpu_request`)
2. Memory-bound workload with CPU HPA
3. High `minReplicas` blocking consolidation with low utilization

## Known Limitations

Document in output when:
- CPU fragmentation undefined (no CPU requests on node)
- HPA-to-pod matching is heuristic (substring-based)
- CPU reductions don't account for node memory pressure

## Code Style

- **Prefer functions over classes**
- Keep code minimal and readable
- Use type hints
- Include docstrings explaining WHY, not just WHAT
- Add inline comments for non-obvious logic

## Configuration

```yaml
clusters:
  cluster-name:
    env: prod|stage|dev  # Only "prod" = production
    project: project-name
    prom_url: http://prometheus.example
    owner_email:
      - owner@example.com
    exclude_namespaces:  # Optional: namespaces to skip
      - kube-system
      - kube-public
```

## Testing Locally

```bash
# With local Prometheus on port 9090
python capacity_analyzer.py clusters.yaml

# Run the viewer UI
python3 -m http.server 8000
# Open http://localhost:8000/viewer/
```

## Constants to Know

| Constant | Default | Purpose |
|----------|---------|---------|
| `QUERY_WINDOW` | `7d` | Percentile calculation window |
| `PROMETHEUS_VERIFY_TLS` | `False` | TLS verification |
| `LOW_EFFICIENCY_THRESHOLD` | `0.3` | Node efficiency threshold |
| `HIGH_FRAGMENTATION_THRESHOLD` | `0.5` | CPU fragmentation threshold |
| `LOW_CPU_USAGE_RATIO` | `0.2` | HPA misalignment threshold |

## When Modifying Code

1. Ensure percentiles still come from Prometheus
2. Maintain node-scoped calculations (never cluster-wide for node metrics)
3. Add limitations to output for edge cases
4. Keep the 3 recommendation types only
5. Test with `python -m py_compile capacity_analyzer.py`

## Output JSON Format

### Top-Level Fields
```json
{
  "cluster": "cluster-name",
  "env": "prod|nonprod",
  "project": "project-name",
  "generated_at": "2026-01-07T12:00:00Z",
  "analysis_window": "7d",
  "recommendations": [...],
  "limitations": [...],
  "summary": {...}
}
```

### Summary Section (Human-Readable)
```json
"summary": {
  "total_recommendations": N,
  "pods": { "affected": X, "total": Y, "text": "X out of Y pods need resizing" },
  "nodes": { "affected": A, "total": B, "text": "A out of B nodes show inefficiency" },
  "hpa": { "affected": C, "total": D, "text": "C out of D HPAs are misaligned" },
  "potential_savings": {
    "cpu_cores": -2.5,
    "memory_bytes": 1073741824,
    "memory_mb": 1024,
    "memory_gb": 1.0,
    "text": "Need 2.50 more CPU cores; Save 1.0GB memory"
  },
  "pod_resize_count": X,
  "node_rightsize_count": A,
  "hpa_misalignment_count": C
}
```

### POD_RESIZE Recommendation
```json
{
  "type": "POD_RESIZE",
  "namespace": "default",
  "pod": "myapp-abc123",
  "current": { "cpu_request": 0.5, "memory_request": 536870912 },
  "recommended": { "cpu_request": 0.25, "memory_request": 268435456 },
  "savings": {
    "cpu_cores": 0.25,
    "memory_bytes": 268435456,
    "memory_mb": 256
  },
  "usage_percentiles": { "cpu_p95": 0.15, "cpu_p99": 0.18, ... },
  "explanation": "CPU request decrease by 50%..."
}
```

### Node Recommendation Actions (Standardized)
| Action | Meaning |
|--------|---------|
| `DOWNSIZE_NODE` | Node is underutilized, replace with smaller instance |
| `RIGHT_SIZE_NODE` | High fragmentation, consider rebalancing or different instance type |
| `CONSOLIDATE_NODE` | Workloads can move, node may be removable |
| `NO_ACTION` | Node is healthy |

### Memory Values (Dual Format)
```json
"memory_allocatable": { "bytes": 34359738368, "gb": 32 }
```
Always include both raw bytes and human-readable GB.

## Viewer UI

Static HTML/JS/CSS viewer in `viewer/` directory:
- No backend required - loads JSON via fetch()
- Shows summary cards with counts and potential savings
- Per-pod recommendations with impact display (↑↓ arrows)
- Color coding: green = savings, red = needs more resources

## Common 
 - move common configurable constanst to config.yaml


Pod Shape Normalization (Memory only)

Apply shape normalization to memory requests only

Do NOT normalize CPU requests

Use fixed memory buckets with 2% buffer (to prevent tight node packing):

| Bucket | With 2% Buffer |
|--------|---------------|
| 256Mi  | 251Mi         |
| 512Mi  | 502Mi         |
| 1Gi    | 1003Mi        |
| 2Gi    | 2007Mi        |
| 4Gi    | 4014Mi        |
| 8Gi    | 8028Mi        |

If the recommended memory request is not exactly one of the buckets:

Round up to the next bucket

Never round down

Normalization rule

```
bucket_with_buffer = bucket × 0.98
normalized_memory_request = next_bucket_with_buffer >= memory_request_new
```

Example:

780Mi → 1003Mi (1Gi bucket with 2% buffer)

1300Mi → 2007Mi (2Gi bucket with 2% buffer)

IMPORTANT

Apply shape normalization after usage-based memory calculation

Use normalized value for:

Final recommendation

Fragmentation math

Savings calculation

Memory & CPU Limits (Include in Recommendation)

For every pod, compute and expose:

CPU limit

cpu_limit_new =
max(
  cpu_request_new × 1.50,
  cpu_p100 × 1.25
)


Memory limit

memory_limit_new =
max(
  normalized_memory_request × 1.50,
  memory_p100 × 1.25
)

UI / Output Requirements (MANDATORY)

For each pod recommendation, include both current and recommended values:

current:
  cpu_request
  cpu_limit
  memory_request
  memory_limit

recommended:
  cpu_request
  cpu_limit
  memory_request
  memory_limit


UI expectation

Always show:

Current request vs recommended request

Current limit vs recommended limit

Clearly label normalized memory requests

Example UI text:

“Memory request normalized from 780Mi → 1Gi for better node packing.”

Do NOT

Normalize CPU requests

Compute savings from limits

Hide current limits in output

Limits are shown for visibility only, not savings.



HPA Recommendation Output Rules

HPA recommendations are heuristic and advisory

Do NOT attempt exact ownership resolution

Use simple, direct statements

Avoid technical explanations in UI text

HPA Recommendation Statements (USE EXACT WORDING)

When conditions are met, generate one or more of the following statements:

Min replicas

“Consider reducing the minimum replica count if sustained usage remains low.”

Max replicas

“Consider lowering the maximum replica count if peak scaling is rarely reached.”

CPU-based HPA

“HPA may be scaling based on CPU requests that are higher than actual usage.”

Memory-bound workload

“Workload appears memory-bound, but HPA is configured to scale on CPU.”

Consumer workload

“If this workload consumes from a topic or queue, ensure replica count aligns with the partition count.”

HPA Mapping Rule

Map HPA to pods heuristically

A pod is considered associated with an HPA if:

hpa_target_name is a substring of pod_name


If no pods match, do not generate HPA recommendations

Limitations (ALWAYS INCLUDE)

Add the following limitations text verbatim in output:

Limitations

HPA analysis is heuristic and based on naming conventions.

HPA evaluation considers only CPU and memory metrics.

Custom or external metrics are not analyzed.

For consumer workloads, scaling recommendations do not account for topic or queue partition counts.

Validate HPA changes with application owners before applying.

Output Rules

HPA recommendations must:

Use soft language (“may”, “consider”)

Avoid definitive instructions

Be advisory only

Do NOT:

Recommend automatic HPA changes

Suggest disabling HPA

Infer behavior from custom metrics

Generate code and output text that follows these rules exactly.