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
```
Create gitignore and add the following lines to ignore Python cache files:

```__pycache__/
*.pyc
```
and others as needed.
```

Create discussion tracker  file for our chat tracker:


UI 

You are an expert frontend engineer building internal developer tools for SRE and platform teams.

Build a simple, static, human-readable HTML viewer to visualize Kubernetes capacity analysis output stored as JSON files.

🎯 Objective

Convert a machine-generated analysis.json into a clear, readable, sectioned UI for humans.

No backend

No frameworks

No charts

Text-first, explanation-driven UI

This viewer is read-only and must work by serving static files using:

python3 -m http.server

📂 Input File (STRICT CONTRACT)

The viewer must read:

/output/<project>/<env>/analysis.json


Example:

/output/project1/prod/analysis.json


The JSON contains:

cluster

env

project

generated_at

summary

recommendations[]

type ∈ POD_RESIZE | NODE_RIGHTSIZE | HPA_MISALIGNMENT

limitations[]

Do NOT invent new fields.

🖥️ UI REQUIREMENTS
Page Structure

Header

Title: Kubernetes Capacity Analysis

Cluster name

Environment (prod / nonprod)

Project

Generated timestamp

Summary Section

Pod resize count

Node right-size count

HPA misalignment count

Pod Resize Section

Render only type === "POD_RESIZE"

For each item show:

Namespace

Pod name

Current CPU / Memory requests

Recommended CPU / Memory requests

Usage percentiles (P95 / P99)

Explanation text

Node Right-Size Section

Render only type === "NODE_RIGHTSIZE"

For each item show:

Node name

Direction (down / right-size)

CPU fragmentation

Node efficiency

Pods on node

Explanation

HPA Misalignment Section

Render only type === "HPA_MISALIGNMENT"

For each item show:

Namespace

HPA name

Target workload

Min / Max / Current replicas

Reasons (bullet list)

Limitation text

Limitations Section (IMPORTANT)

Always visible

Render all items from limitations[]

Never hidden or collapsible

🎨 UI STYLE GUIDELINES

Plain HTML + vanilla JavaScript only

Use headings, cards, and tables where helpful

No charts, no animations

Professional, minimal, readable

Optimized for SRE / DevOps users

⚙️ TECHNICAL CONSTRAINTS

Use fetch() to load JSON

JSON path must be absolute, e.g.:

fetch("/output/project1/prod/analysis.json")


Do not assume any backend

Do not use React / Vue / libraries

📁 OUTPUT FILES (GENERATE ALL)
viewer/
  index.html
  app.js
  styles.css

🚨 IMPORTANT RULES

Do NOT show raw JSON blobs except for debugging

Do NOT modify JSON structure

Keep code readable and commented

Viewer must fail gracefully if JSON is missing

Start now and generate all three files.

Focus on clarity over visual polish.