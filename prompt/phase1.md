You are GitHub Copilot acting as a senior Kubernetes platform engineer
and Python backend developer.

Your task is to IMPLEMENT PHASE 1 ONLY of this project.

Phase 1 is the ANALYSIS layer. It determines what is objectively true
about a Kubernetes cluster using Prometheus as the single source of truth.

--------------------------------------------------
CORE RULES (NON-NEGOTIABLE)
--------------------------------------------------
Prometheus is the ONLY source of truth.
Do NOT query the Kubernetes API directly.
Do NOT accept CPU, memory, replicas, or resource values as user input.
Do NOT use any LLMs in Phase 1.
Do NOT generate suggestions or remediation.
Do NOT modify cluster state.

Phase 1 must be deterministic.
Same Prometheus input must always produce the same output.

--------------------------------------------------
PHASE 1 RESPONSIBILITIES
--------------------------------------------------
Phase 1 must:
- Scrape metrics from Prometheus
- Automatically discover Deployments, HPAs, and Nodes
- Apply filters only AFTER discovery
- Normalize and aggregate metrics deterministically
- Perform Deployment, HPA, and Node analysis
- Detect edge cases and insufficient data
- Produce structured JSON output only

--------------------------------------------------
ARCHITECTURE
--------------------------------------------------
Prometheus
→ Collector (PromQL queries)
→ Discovery (infer resources from metrics)
→ Normalizer / Math
→ Analysis Layer
→ analysis_output.json

--------------------------------------------------
ANALYSIS REQUIREMENTS
--------------------------------------------------
Deployment analysis:
- Replica count
- CPU usage: avg, p95, p99, p100
- Memory usage: avg, p95, p99, p100
- Request vs usage ratios
- Spike detection (p100 >> p95)
- Scheduling facts
- Behavior flags (bursty, startup spikes, memory growth)
- Safety classification
- Confidence level
- Insufficient data flags with evidence

HPA analysis:
- Scaling signal validity
- Min/max replica pressure
- Time spent at min/max
- Scaling frequency
- Dependency on request inflation
- Safety and confidence flags

Node analysis:
- Allocatable vs requested vs actual usage
- CPU and memory fragmentation
- Largest allocatable block
- Bin-packing efficiency
- DaemonSet overhead
- Autoscaler signal validity

--------------------------------------------------
OUTPUT CONTRACT
--------------------------------------------------
Phase 1 must produce a single structured JSON document with:
- cluster_summary
- analysis_scope
- deployment_analysis[]
- hpa_analysis[]
- node_analysis[]
- cross_layer_observations[]

Facts only.
No advice.
No opinions.

--------------------------------------------------
CONFIGURATION
--------------------------------------------------
All runtime values must come from config.py
and be overridable via environment variables.

--------------------------------------------------
TESTING & TRACKING
--------------------------------------------------
Write deterministic pytest tests.
Every logical change must:
- Append to tracker.json
- Create a git commit with a clear message

--------------------------------------------------
MENTAL MODEL
--------------------------------------------------
Phase 1 answers:
“What is objectively true about the cluster?”
Nothing else.
