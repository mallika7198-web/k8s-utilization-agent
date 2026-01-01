You are GitHub Copilot acting as a senior Python backend and minimal UI engineer.

Phase 1 of this project is already implemented and produces a holistic,
cluster-wide analysis_output.json derived only from Prometheus.

Your task is to implement PHASE 2 and update the UI presentation,
without modifying Phase-1 logic or outputs.

Core architectural rules (non-negotiable):
Phase 1 represents facts and is authoritative.
Phase 2 represents interpretation using an LLM and is advisory only.
Phase-1 and Phase-2 must never be mixed in code, data, or UI.
Prometheus remains the single source of truth.

Phase 2 overview:
Phase 2 is a read-only reasoning layer.
It reads analysis_output.json, sends it to an LLM, receives explanations,
patterns, warnings, and candidate actions, and writes insights_output.json.
Phase 2 must not query Prometheus or Kubernetes, must not recompute metrics,
must not override safety flags, must not modify Phase-1 output, and must not
automate or apply changes.

Input and output contract:
Input file is analysis_output.json and must be treated as read-only.
Output file is insights_output.json and must contain LLM output only.
These two files must remain fully independent.

Configuration (mandatory):
All Phase-2 configuration must live in config.py and be overridable via
environment variables.

Required configuration keys:
PHASE2_ENABLED
ANALYSIS_OUTPUT_PATH
INSIGHTS_OUTPUT_PATH
LLM_MODE (local or remote)
LLM_ENDPOINT_URL
LLM_MODEL_NAME
LLM_TIMEOUT_SECONDS
PHASE2_LLM_PROMPT

The LLM prompt must be defined only in config.py.
The LLM endpoint must be defined only in config.py.
No hard-coded prompts, endpoints, model names, or timeouts are allowed.

Phase 2 components to implement:

Phase-2 runner:
Read analysis_output.json.
Exit cleanly if PHASE2_ENABLED is false.
Load PHASE2_LLM_PROMPT and LLM_ENDPOINT_URL from config.py.
Call the LLM using a client adapter.
Validate the LLM response strictly.
Write insights_output.json atomically.
Never modify Phase-1 output.

LLM client adapter:
Generic HTTP client.
Endpoint, model name, and timeout must come from config.py.
Support local Ollama for development and a remote LLM at runtime.
No prompt logic and no analysis logic inside the adapter.

LLM output validation:
Treat LLM output as untrusted input.
Validate that the response is valid JSON.
Validate required top-level keys:
cluster_summary, patterns, warnings, action_candidates, priorities, limitations.
Validate schema for warnings and action_candidates.
Respect Phase-1 safety flags.
If safe_to_resize is false, no resize-related actions are allowed.
If confidence is Low, actions must be empty or explicitly blocked.
If insufficient data is present, limitations must explicitly mention it.
On validation failure, do not overwrite an existing valid insights_output.json.
Write an error object instead and do not crash the application.

UI presentation update (mandatory):
The UI must clearly separate Phase-1 facts from Phase-2 insights.
Top-level UI tabs must be:
Facts & Evidence, Insights (LLM), Raw JSON.

Facts & Evidence tab:
Shows Phase-1 data only.
No changes to Phase-1 logic.
This tab answers what is objectively true.

Insights (LLM) tab:
Visible only if insights_output.json exists and is valid.
Clearly labeled as LLM-generated insights.
Based on Phase-1 analysis and for human review only.
Render cluster narrative, patterns, warnings, candidate areas for review,
prioritization, and limitations.
No buttons, no automation, no editable fields.
Evidence must reference Phase-1 objects and link back to Phase-1 views.

Raw JSON tab:
Read-only display of analysis_output.json and insights_output.json.

Testing requirements:
Add pytest tests for LLM validation, failure scenarios, and Phase-2 disabled paths.
Mock LLM responses and keep tests deterministic.

Tracking and Git discipline:
After every logical change, create a git commit.
One logical change equals one commit.
Do not combine unrelated changes in a single commit.

Commit message format:
<scope>: <short description>

Details:
- <what changed>
- <why it was changed>

Example commit messages:
phase2: add LLM runner for insights generation
ui: add Insights (LLM) tab with read-only rendering
config: add Phase-2 LLM prompt and endpoint settings

Every commit must also append an entry to tracker.json with timestamp,
files changed, change type, and a short factual description.

Absolute prohibitions:
Do not recompute metrics.
Do not mix Phase-1 and Phase-2 data.
Do not hard-code prompts or endpoints.
Do not let the LLM override safety flags.
Do not skip commits.

Success criteria:
Phase 1 works independently.
Phase 2 is optional and safe.
UI clearly separates facts from insights.
Git history is clean and reviewable.
tracker.json matches commit history.

Mental model:
Phase 1 determines what is true.
Phase 2 explains what is true.
Humans decide what to do.
Git records every step.
