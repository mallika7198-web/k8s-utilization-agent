import os
import logging
import sys
from typing import Optional
from urllib.parse import urlparse


# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT: str = os.getenv(
    "LOG_FORMAT", 
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def setup_logging():
    """Configure application-wide logging"""
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


PROMETHEUS_URL: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
PROMETHEUS_TIMEOUT_SECONDS: int = int(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "30"))
METRICS_WINDOW_MINUTES: int = int(os.getenv("METRICS_WINDOW_MINUTES", "15"))
MIN_OBSERVATION_WINDOW_MINUTES: int = int(os.getenv("MIN_OBSERVATION_WINDOW_MINUTES", "10"))
CPU_BURST_RATIO_THRESHOLD: float = float(os.getenv("CPU_BURST_RATIO_THRESHOLD", "2.0"))
MEMORY_GROWTH_THRESHOLD_PERCENT: float = float(os.getenv("MEMORY_GROWTH_THRESHOLD_PERCENT", "10"))
MAX_ACCEPTABLE_OVERPROVISION_RATIO: float = float(os.getenv("MAX_ACCEPTABLE_OVERPROVISION_RATIO", "5.0"))
ENABLE_LOAD_GENERATION: bool = _env_bool("ENABLE_LOAD_GENERATION", False)
LOAD_GENERATION_TARGET_URL: Optional[str] = os.getenv("LOAD_GENERATION_TARGET_URL")
LOAD_GENERATION_DURATION_SECONDS: int = int(os.getenv("LOAD_GENERATION_DURATION_SECONDS", "300"))
LOAD_GENERATION_CONCURRENCY: int = int(os.getenv("LOAD_GENERATION_CONCURRENCY", "5"))
EXCLUDED_NAMESPACES: str = os.getenv("EXCLUDED_NAMESPACES", "kube-system,kube-public,istio-system")
ANALYSIS_OUTPUT_PATH: str = os.getenv("ANALYSIS_OUTPUT_PATH", "output/analysis_output.json")

# Phase 2: LLM Insights Configuration
PHASE2_ENABLED: bool = _env_bool("PHASE2_ENABLED", False)
INSIGHTS_OUTPUT_PATH: str = os.getenv("INSIGHTS_OUTPUT_PATH", "output/insights_output.json")
LLM_MODE: str = os.getenv("LLM_MODE", "local")
LLM_ENDPOINT_URL: str = os.getenv("LLM_ENDPOINT_URL", "http://localhost:11434")
LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "llama3:8b")
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")  # For remote LLM authentication

# Phase 2: LLM Prompt Template (user-configurable)
# Instruction: review and modify this prompt as needed before enabling Phase 2
PHASE2_LLM_PROMPT: str = os.getenv("PHASE2_LLM_PROMPT", """You are a Large Language Model acting as a senior Kubernetes platform engineer.

You are running in Phase 2 of a Kubernetes analysis system.

Your input is a single JSON document named analysis_output.json.
This document contains verified facts, metrics, flags, and safety decisions
produced by a deterministic Phase-1 analysis pipeline.

You MUST treat this input as correct and authoritative.

Your role is to EXPLAIN the analysis to a human.
You must NOT perform analysis, calculations, or data collection.

Rules you must follow:

- Do NOT query Prometheus.
- Do NOT query Kubernetes.
- Do NOT recompute metrics or percentiles.
- Do NOT override safety flags.
- Do NOT invent missing data.
- Do NOT suggest automation or direct actions.

If the input indicates insufficient data or low confidence,
you must clearly state that limitation.

Your tasks:

1. Summarize the overall cluster state.
2. Identify repeated patterns across deployments, HPAs, and nodes.
3. Explain cause-and-effect relationships already present in the data.
4. Highlight risks and why they matter.
5. Propose action candidates for human review only.
6. State uncertainty and data limitations explicitly.

You must output JSON ONLY with the following structure:

{
  "cluster_summary": "string: 2-3 sentences summarizing overall cluster health",
  "patterns": [
    {
      "pattern_id": "string: unique identifier",
      "description": "string: what pattern was observed",
      "affected_objects": ["string: list of deployment/HPA/node names"],
      "evidence": ["string: specific metrics or flags supporting this pattern"]
    }
  ],
  "warnings": [
    {
      "warning_id": "string: unique identifier",
      "severity": "Low | Medium | High",
      "scope": "Deployment | HPA | Node | Cluster",
      "description": "string: what is the risk",
      "evidence": ["string: metrics or flags from Phase 1"],
      "confidence": "Low | Medium | High"
    }
  ],
  "action_candidates": [
    {
      "action_id": "string: unique identifier",
      "scope": "Deployment | HPA | Node | Cluster",
      "description": "string: what action could be considered",
      "expected_impact": "string: what would change if this action was taken",
      "prerequisites": ["string: conditions that must be true first"],
      "blocked_by": ["string: what Phase-1 flags or conditions prevent this action"],
      "confidence": "Low | Medium | High"
    }
  ],
  "priorities": "string: prioritized summary of which issues matter most",
  "limitations": ["string: what data is missing, what confidence is low, what assumptions were made"]
}

CRITICAL RULES:

- Output ONLY JSON. No markdown, no code blocks, no explanatory text.
- Use ALL fields exactly as specified.
- If an array is empty, use [].
- Do NOT suggest actions that Phase-1 marked as unsafe (safe_to_resize=false).
- If Phase-1 shows insufficient_data, explicitly mention it in limitations and warnings.
- Behave like a cautious senior engineer explaining a report in a review meeting.
""")


__all__ = [
    "PROMETHEUS_URL",
    "PROMETHEUS_TIMEOUT_SECONDS",
    "METRICS_WINDOW_MINUTES",
    "MIN_OBSERVATION_WINDOW_MINUTES",
    "CPU_BURST_RATIO_THRESHOLD",
    "MEMORY_GROWTH_THRESHOLD_PERCENT",
    "MAX_ACCEPTABLE_OVERPROVISION_RATIO",
    "ENABLE_LOAD_GENERATION",
    "LOAD_GENERATION_TARGET_URL",
    "LOAD_GENERATION_DURATION_SECONDS",
    "LOAD_GENERATION_CONCURRENCY",
    "EXCLUDED_NAMESPACES",
    "ANALYSIS_OUTPUT_PATH",
    "PHASE2_ENABLED",
    "INSIGHTS_OUTPUT_PATH",
    "LLM_MODE",
    "LLM_ENDPOINT_URL",
    "LLM_MODEL_NAME",
    "LLM_TIMEOUT_SECONDS",
    "LLM_API_KEY",
    "PHASE2_LLM_PROMPT",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "setup_logging",
    "validate_config",
]


# =============================================================================
# Configuration Validation
# =============================================================================
class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""
    pass


def _validate_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise ConfigValidationError(f"{name} must be positive, got {value}")


def _validate_url(name: str, value: str) -> None:
    try:
        result = urlparse(value)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Missing scheme or netloc")
        if result.scheme not in ('http', 'https'):
            raise ValueError(f"Invalid scheme: {result.scheme}")
    except Exception as e:
        raise ConfigValidationError(f"{name} is not a valid URL: {value} ({e})")


def _validate_llm_mode(value: str) -> None:
    if value not in ('local', 'remote'):
        raise ConfigValidationError(
            f"LLM_MODE must be 'local' or 'remote', got '{value}'"
        )


def validate_config() -> None:
    """Validate all configuration values on startup
    
    Raises:
        ConfigValidationError: If any configuration value is invalid
    """
    errors = []
    
    # Validate timeouts are positive
    try:
        _validate_positive_int("PROMETHEUS_TIMEOUT_SECONDS", PROMETHEUS_TIMEOUT_SECONDS)
    except ConfigValidationError as e:
        errors.append(str(e))
    
    try:
        _validate_positive_int("METRICS_WINDOW_MINUTES", METRICS_WINDOW_MINUTES)
    except ConfigValidationError as e:
        errors.append(str(e))
    
    try:
        _validate_positive_int("LLM_TIMEOUT_SECONDS", LLM_TIMEOUT_SECONDS)
    except ConfigValidationError as e:
        errors.append(str(e))
    
    # Validate URLs
    try:
        _validate_url("PROMETHEUS_URL", PROMETHEUS_URL)
    except ConfigValidationError as e:
        errors.append(str(e))
    
    try:
        _validate_url("LLM_ENDPOINT_URL", LLM_ENDPOINT_URL)
    except ConfigValidationError as e:
        errors.append(str(e))
    
    # Validate LLM mode
    try:
        _validate_llm_mode(LLM_MODE)
    except ConfigValidationError as e:
        errors.append(str(e))
    
    # Validate API key for remote mode
    if LLM_MODE == 'remote' and PHASE2_ENABLED and not LLM_API_KEY:
        errors.append("LLM_API_KEY is required when LLM_MODE='remote' and PHASE2_ENABLED=true")
    
    if errors:
        raise ConfigValidationError(
            "Configuration validation failed:\n  - " + "\n  - ".join(errors)
        )

