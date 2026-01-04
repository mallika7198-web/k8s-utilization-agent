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
PROMETHEUS_RETRY_COUNT: int = int(os.getenv("PROMETHEUS_RETRY_COUNT", "3"))
PROMETHEUS_RETRY_BACKOFF_BASE: int = int(os.getenv("PROMETHEUS_RETRY_BACKOFF_BASE", "1"))
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

# =============================================================================
# Node Fragmentation Attribution Configuration
# =============================================================================
# Threshold for DaemonSet overhead (percentage of allocatable resources)
DAEMONSET_OVERHEAD_THRESHOLD_PERCENT: float = float(os.getenv("DAEMONSET_OVERHEAD_THRESHOLD_PERCENT", "15.0"))
# Threshold for considering a pod as "large request" (percentage of node allocatable)
LARGE_POD_REQUEST_THRESHOLD_PERCENT: float = float(os.getenv("LARGE_POD_REQUEST_THRESHOLD_PERCENT", "25.0"))
# Fragmentation threshold to trigger attribution analysis
FRAGMENTATION_THRESHOLD: float = float(os.getenv("FRAGMENTATION_THRESHOLD", "0.3"))

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
PHASE2_LLM_PROMPT: str = os.getenv("PHASE2_LLM_PROMPT", """You are a summarization engine for Kubernetes cluster analysis data.

INPUT: JSON document (analysis_output.json) containing Phase-1 facts.
OUTPUT: JSON document grouping those facts into concise categories.

STRICT RULES:
- Do NOT analyze, compute, or infer anything new.
- Do NOT suggest actions, numbers, or automation.
- Do NOT override Phase-1 safety flags (unsafe_to_resize, insufficient_data).
- Do NOT write narrative prose or long explanations.
- ONLY group and label existing Phase-1 data.

OUTPUT FORMAT (JSON only, no markdown):

{
  "summary": "One sentence cluster state from Phase-1 data",
  
  "deployment_review": {
    "bursty": ["deployment names with BURSTY flag"],
    "underutilized": ["deployment names with UNDERUTILIZED flag"],
    "memory_pressure": ["deployment names with memory_utilization > 90%"],
    "unsafe_to_resize": ["deployment names where unsafe_to_resize=true"]
  },
  
  "hpa_review": {
    "at_threshold": ["HPA names with AT_CPU_THRESHOLD or AT_MEMORY_THRESHOLD"],
    "scaling_blocked": ["HPA names where scaling_blocked=true"],
    "scaling_down": ["HPA names with SCALING_DOWN_PENDING"]
  },
  
  "node_fragmentation_review": {
    "fragmented_nodes": ["node names where cpu_fragmentation > 0.3 OR memory_fragmentation > 0.3"],
    "large_request_pods": ["pod names from fragmentation_attribution.large_request_pods"],
    "constraint_blockers": ["pod names from fragmentation_attribution.constraint_blockers with constraint type"],
    "daemonset_overhead": ["node pool names where daemonset_overhead.exceeds_threshold=true"],
    "scale_down_blockers": ["pod names from fragmentation_attribution.scale_down_blockers with reason"]
  },
  
  "cross_layer_risks": {
    "high": ["component names from cross_layer_observations where risk_level=High"],
    "medium": ["component names from cross_layer_observations where risk_level=Medium"]
  },
  
  "limitations": ["insufficient_data flags", "low confidence items", "missing metrics"]
}

RULES FOR EACH CATEGORY:
- If category is empty, use empty array [].
- Only include items that exist in Phase-1 data.
- Do not invent items or relationships.
- Keep entries short: "pod-name (reason)" format max.
- For unsafe_to_resize deployments, do NOT suggest resize actions.
- If insufficient_data=true on any node, list it in limitations.

OUTPUT ONLY THE JSON OBJECT. NO OTHER TEXT.
""")


__all__ = [
    "PROMETHEUS_URL",
    "PROMETHEUS_TIMEOUT_SECONDS",
    "PROMETHEUS_RETRY_COUNT",
    "PROMETHEUS_RETRY_BACKOFF_BASE",
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
    "DAEMONSET_OVERHEAD_THRESHOLD_PERCENT",
    "LARGE_POD_REQUEST_THRESHOLD_PERCENT",
    "FRAGMENTATION_THRESHOLD",
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

