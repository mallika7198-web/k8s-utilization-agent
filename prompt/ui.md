You are GitHub Copilot acting as a minimal UI engineer.

Your task is to IMPLEMENT A READ-ONLY UI
to present Phase-1 and Phase-2 outputs safely.

--------------------------------------------------
CORE UI RULES (NON-NEGOTIABLE)
--------------------------------------------------
The UI must NEVER:
- Perform analysis
- Modify data
- Accept resource inputs
- Trigger automation
- Mix Phase-1 and Phase-2 data

--------------------------------------------------
DATA SOURCES
--------------------------------------------------
Phase 1:
- analysis_output.json (authoritative facts)

Phase 2:
- insights_output.json (optional, advisory)

--------------------------------------------------
UI STRUCTURE
--------------------------------------------------
Top-level tabs:
Facts & Evidence | Insights (LLM) | Raw JSON

Facts & Evidence tab:
- Default view
- Shows Phase-1 data only
- Cluster overview
- Deployment table + drill-down
- HPA table
- Node / node-pool table
- Answers: “What is objectively true?”

Insights (LLM) tab:
- Visible only if insights_output.json exists and is valid
- Clearly labeled as LLM-generated
- Shows:
  - Cluster narrative
  - Patterns
  - Warnings
  - Candidate areas for review
  - Prioritization
  - Limitations
- No buttons
- No automation
- Evidence must link back to Phase-1 views

Raw JSON tab:
- Read-only rendering of analysis_output.json
- Read-only rendering of insights_output.json

--------------------------------------------------
VISUAL PRINCIPLES
--------------------------------------------------
Neutral colors
Clear separation between facts and interpretation
Dense but readable tables
No charts invented by LLM

--------------------------------------------------
TRACKING
--------------------------------------------------
Every UI change must:
- Append to tracker.json
- Create a git commit with a clear message

--------------------------------------------------
MENTAL MODEL
--------------------------------------------------
The UI behaves like a report viewer.
It explains nothing and decides nothing.
