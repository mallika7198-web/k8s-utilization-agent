You are a senior Kubernetes platform engineer and backend architect.

Your task is to DESIGN and IMPLEMENT **PHASE 1 ONLY** of a Kubernetes
capacity and efficiency analysis application.

PHASE 1 SCOPE IS STRICT.
There is NO LLM usage, NO suggestions, NO automation.
The system produces FACTS, FLAGS, and EVIDENCE only.

Humans will manually review the output.
A suggestion/LLM layer will be added later in Phase 2.

------------------------------------
PHASE 1 GOAL
------------------------------------
Build a deterministic analysis system that:
- Collects metrics from Prometheus
- Analyzes Deployments, HPAs, and Nodes
- Determines what is objectively true
- Detects inefficiencies, risks, and edge cases
- Produces structured, explainable JSON output
- Is human-readable and future LLM-ready

------------------------------------
CONFIGURATION (MANDATORY)
------------------------------------
The system MUST use a centralized configuration file.

Create a `config.py` module that contains all runtime-configurable values.
No hard-coded values are allowed outside `config.py`.

`config.py` MUST support:

- PROMETHEUS_URL
  (default: "http://localhost:9090")

- PROMETHEUS_TIMEOUT_SECONDS
  (default: 30)

- METRICS_WINDOW_MINUTES
  (default: 15)

- MIN_OBSERVATION_WINDOW_MINUTES
  (default: 10)

- CPU_BURST_RATIO_THRESHOLD
  (default: 2.0)   # P100 / P95

- MEMORY_GROWTH_THRESHOLD_PERCENT
  (default: 10)

- MAX_ACCEPTABLE_OVERPROVISION_RATIO
  (default: 5.0)

- ENABLE_LOAD_GENERATION (true/false)
  (default: false)

- LOAD_GENERATION_TARGET_URL
  (optional, used only when enabled)

- LOAD_GENERATION_DURATION_SECONDS
  (default: 300)

- LOAD_GENERATION_CONCURRENCY
  (default: 5)

Configuration values MUST be:
- Readable from `config.py`
- Overridable via environment variables
- Imported by all modules that need them

------------------------------------
ENVIRONMENT ASSUMPTIONS
------------------------------------
- Kubernetes cluster is local kind
- Prometheus runs inside the cluster
- Prometheus is accessed via kubectl port-forward
  (default: http://localhost:9090)
- Metrics may be absent until load is generated

------------------------------------
ARCHITECTURE (MANDATORY)
------------------------------------
Prometheus
 → Python Metrics Collector
 → Python Normalization & Aggregation
 → Python Analysis Layer (core)
 → Presentation Layer (CLI / UI / API)
 → Human Review

------------------------------------
STRICT CONSTRAINTS
------------------------------------
- Python ONLY
- No LLM calls
- No recommendations or advice
- No words like: "should", "recommend", "suggest"
- No auto-actions
- No guessing if data is missing
- Same input MUST produce same output
- All math must be explicit and testable

------------------------------------
ANALYSIS LAYER (CORE OF PHASE 1)
------------------------------------
This layer determines **what is objectively true**.

It MUST compute the following analyses.

========================
1) DEPLOYMENT ANALYSIS
========================
Compute:

RESOURCE FACTS
- Replicas
- CPU request vs usage using:
  - Avg
  - P95
  - P99
  - P100 (max)
- Memory request vs usage using:
  - Avg
  - P95
  - P99
  - P100

DERIVED METRICS
- CPU overprovision ratio (request / P95)
- Memory overprovision ratio (request / P95)
- Spike ratio (P100 / P95)

BEHAVIOR FLAGS
- Bursty workload (based on CPU_BURST_RATIO_THRESHOLD)
- Startup spikes
- Memory growth trend
- InitContainer spikes

SCHEDULING FACTS
- Nodes used
- Pods per node distribution
- Pending pods

EDGE CASE DETECTION
- Bursty workloads
- Memory growth trends
- JVM / cache-heavy patterns
- Strict PodDisruptionBudgets
- InitContainer spikes
- Insufficient observation window
- Missing metrics

SAFETY CLASSIFICATION
- risk_level: Low | Medium | High
- confidence_level: High | Medium | Low
- safe_to_resize: true | false | partial_only

OUTPUT:
Produce a structured JSON object named `deployment_analysis`.

========================
2) HPA ANALYSIS
========================
Compute:

HPA CONFIG FACTS
- Enabled or not
- Metric type (CPU / Memory / Custom)
- Target utilization
- Min replicas
- Max replicas

SCALING BEHAVIOR
- Scale-up events (24h)
- Scale-down events (24h)
- % time at min replicas
- % time at max replicas

LINKED RESOURCE FACTS
- Deployment CPU request
- Deployment CPU P95 usage
- Average replica utilization

ANALYSIS FLAGS
- Scaling signal validity
- Utilization misleading due to inflated requests
- Min replica pressure
- Ineffective autoscaling

SAFETY CLASSIFICATION
- risk_level
- confidence_level

OUTPUT:
Produce a structured JSON object named `hpa_analysis`.

========================
3) NODE ANALYSIS
========================
Compute:

NODE CAPACITY
- Allocatable CPU
- Allocatable memory

REQUESTED VS ACTUAL
- Total requested CPU and memory
- Actual average CPU and memory usage

FRAGMENTATION METRICS
- Largest free CPU block
- Largest free memory block
- Fragmentation type (CPU / Memory / Both / None)

BIN PACKING
- Pods per node
- Packing efficiency indicator

DAEMONSET OVERHEAD
- CPU and memory consumed by DaemonSets

AUTOSCALER FACTS
- Scale-up events
- Scale-down blocked or not
- New node utilization after scale-up

ANALYSIS FLAGS
- Bin-packing efficiency
- Autoscaler signal validity

SAFETY CLASSIFICATION
- risk_level
- confidence_level

OUTPUT:
Produce a structured JSON object named `node_analysis`.

------------------------------------
OBSERVATION QUALITY (MANDATORY)
------------------------------------
For every analysis:
- Detect if metrics exist
- Detect if traffic is active
- Detect insufficient observation window
- Explicitly block analysis when data is insufficient

------------------------------------
PRESENTATION LAYER
------------------------------------
- Render facts, numbers, and flags only
- No business logic
- No inference
- Consume structured JSON output

------------------------------------
TESTING & ACCEPTANCE
------------------------------------
- Unit tests for:
  - Avg / P95 / P99 / P100 calculations
  - Burst detection
  - Fragmentation math
  - Safety classification
- Deterministic test datasets
- Missing data must block analysis explicitly
- Config overrides must be testable

------------------------------------
FINAL EXPECTATION
------------------------------------
The system should behave like a senior platform engineer
reviewing a Kubernetes cluster and presenting
clear, defensible FACTS for human decision-making.

DO NOT implement suggestions.
DO NOT implement automation.
DO NOT implement LLM logic.


