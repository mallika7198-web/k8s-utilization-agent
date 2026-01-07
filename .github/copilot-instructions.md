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
- Query window configured via `QUERY_WINDOW` constant

### 3. Recommendation Types (ONLY 3)
1. `POD_RESIZE` - CPU/memory request & limit recommendations
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
```

## Testing Locally

```bash
# With local Prometheus on port 9090
python capacity_analyzer.py clusters.yaml
```

## Constants to Know

| Constant | Default | Purpose |
|----------|---------|---------|
| `QUERY_WINDOW` | `7d` | Percentile calculation window |
| `PROMETHEUS_VERIFY_TLS` | `False` | TLS verification |
| `LOW_EFFICIENCY_THRESHOLD` | `0.3` | Node efficiency threshold |
| `HIGH_FRAGMENTATION_THRESHOLD` | `0.5` | CPU fragmentation threshold |

## When Modifying Code

1. Ensure percentiles still come from Prometheus
2. Maintain node-scoped calculations (never cluster-wide for node metrics)
3. Add limitations to output for edge cases
4. Keep the 3 recommendation types only
5. Test with `python -m py_compile capacity_analyzer.py`

## Output JSON Format

### Summary Section (Human-Readable)
```json
"summary": {
  "pods": { "affected": X, "total": Y, "text": "X out of Y pods need resizing" },
  "nodes": { "affected": A, "total": B, "text": "A out of B nodes show inefficiency" },
  "hpa": { "affected": C, "total": D, "text": "C out of D HPAs are misaligned" },
  "pod_resize_count": X,  // Legacy - kept for backward compatibility
  "node_rightsize_count": A,
  "hpa_misalignment_count": C
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
```
