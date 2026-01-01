
Scope Lock (Strict)
This project is Phase 1 only.
Do NOT implement any LLM usage.
Do NOT generate suggestions, recommendations, or advice.
Do NOT automate actions.
The system must output facts, metrics, flags, and evidence only.
Humans will manually interpret and decide actions.
If a task involves opinions or “what should be done”, do not implement it.

Architecture Rules
Python is the Analysis Layer.
The Analysis Layer must be deterministic, testable, and compute all math and thresholds.
The Presentation Layer is render-only and must not contain business logic.
A future LLM will consume the output unchanged, but must not be referenced or implemented now.

Source of Truth Rules
Prometheus is the single source of truth for metrics and state.
Do NOT rely on direct Kubernetes API access for analysis.
Kubernetes metadata may be used only if it is already exposed via Prometheus metrics.
If data is not available in Prometheus, it must be treated as missing.

Configuration Rules
All runtime values must come from a central config.py file.
No hard-coded values are allowed outside config.py.
Every config value must have a default and be overridable via environment variables.
Example pattern:
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090
")

Change Tracking (Mandatory)
A file named tracker.json must exist at the repository root.
Every code change must update tracker.json.
tracker.json must record:

Timestamp of change

File(s) modified

Type of change (config, analysis, normalization, presentation, test)

Short factual description of what changed
tracker.json is append-only and acts as a lightweight audit log.

Required Module Structure
config.py contains all configuration.
collector module queries Prometheus using PromQL only.
normalizer module converts raw metrics into normalized domain objects.
analysis module computes facts, ratios, flags, and safety classification.
presentation module renders output only.
tests module contains pytest-based deterministic tests.

Metrics and Math Rules
Python must compute average, P95, P99, and P100 (maximum).
Percentiles must never be computed in UI or any AI layer.
All formulas must be explicit and testable.
Same input must always produce the same output.

Observation and Safety Rules
The system must detect missing metrics.
The system must detect lack of traffic.
The system must detect insufficient observation window.
If data is insufficient, analysis must be blocked and clearly flagged.
No guessing or assumptions are allowed.

Edge Case Handling (Mandatory)
Python must explicitly detect and flag:
Bursty workloads (P100 much greater than P95)
Startup spikes
Memory growth trends
InitContainer spikes
Strict PodDisruptionBudgets
JVM or cache-heavy behavior (flag only)
Node fragmentation conditions
Do not infer or guess these conditions.

Output Contract
Output must be structured JSON only.
The output must match the defined schemas:
deployment_analysis
hpa_analysis
node_analysis
Do not use advisory language such as “should”, “recommend”, or “fix”.
Use factual fields like risk_level, confidence_level, and safe_to_resize.

Presentation Layer Rules (Basic UI Required)
Provide a simple, readable UI for humans.
The UI must:

Improve readability of analysis output

Group facts, metrics, and flags clearly

Display cross-layer relationships
The UI must NOT:

Perform analysis

Contain business logic

Modify data
The UI is a pure rendering layer on top of structured JSON.

Testing Rules
Use pytest.
Tests must cover percentile calculations, burst detection, fragmentation logic, safety classification, and config overrides.
Use deterministic mock datasets.
No tests should depend on live clusters.

Coding Style Guidance
Prefer small, pure functions.
Avoid side effects.
Use clear and descriptive variable names.
Comments should explain why a computation exists, not what it does.
Docstrings must describe facts computed, not actions suggested.

Explicit Don’ts
Do not import or reference any LLM.
Do not write Kubernetes resources.
Do not trigger autoscaling or remediation.
Do not call cloud provider SDKs.
Do not put logic in the UI layer.

Definition of Done for Phase 1
The output matches the agreed JSON shape and meaning.
A senior platform engineer can trust the output immediately.
tracker.json reflects all changes made.
The UI presents data clearly without altering it.
The output can be consumed by a future LLM without modification.

Recommended Header Comment for All Python Files
Copilot: Phase-1 Analysis only. No LLM. No suggestions. Deterministic facts and flags only. Prometheus is the source of truth. All configuration from config.py. Update tracker.json for every change. Human decision required

Always cleanup unnecessary code and files immediately after the scope changes.

Dont modify prompt.md or prompt-v1.md.