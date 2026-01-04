import os
import json
import logging
import sys
from typing import Optional, List, Dict, Any
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


# =============================================================================
# Prometheus Endpoints Configuration
# =============================================================================
# Multi-cluster Prometheus endpoints with metadata
# Can be overridden via PROMETHEUS_ENDPOINTS_JSON environment variable
_DEFAULT_PROMETHEUS_ENDPOINTS: List[Dict[str, Any]] = [
    {

        "cluster_name": "local-kind",
        "project": "local",
        "environment": "local",
        "url": "http://localhost:9090",
        "owner": "test"
    }
]

def _load_prometheus_endpoints() -> List[Dict[str, Any]]:
    """Load Prometheus endpoints from env var or use defaults"""
    env_json = os.getenv("PROMETHEUS_ENDPOINTS_JSON")
    if env_json:
        try:
            return json.loads(env_json)
        except json.JSONDecodeError:
            logging.warning("Invalid PROMETHEUS_ENDPOINTS_JSON, using defaults")
    return _DEFAULT_PROMETHEUS_ENDPOINTS

PROMETHEUS_ENDPOINTS: List[Dict[str, Any]] = _load_prometheus_endpoints()

# Active cluster selection (by cluster_name or index)
ACTIVE_CLUSTER: str = os.getenv("ACTIVE_CLUSTER", "local-kind")

def get_active_prometheus_url() -> str:
    """Get the URL for the currently active cluster"""
    for endpoint in PROMETHEUS_ENDPOINTS:
        if endpoint.get("cluster_name") == ACTIVE_CLUSTER:
            return endpoint["url"]
    # Fallback to first endpoint
    if PROMETHEUS_ENDPOINTS:
        return PROMETHEUS_ENDPOINTS[0]["url"]
    return "http://localhost:9090"

def get_active_cluster_info() -> Dict[str, Any]:
    """Get full info for the currently active cluster"""
    for endpoint in PROMETHEUS_ENDPOINTS:
        if endpoint.get("cluster_name") == ACTIVE_CLUSTER:
            return endpoint
    if PROMETHEUS_ENDPOINTS:
        return PROMETHEUS_ENDPOINTS[0]
    return {"cluster_name": "unknown", "url": "http://localhost:9090"}

# Legacy compatibility
PROMETHEUS_URL: str = get_active_prometheus_url()

PROMETHEUS_TIMEOUT_SECONDS: int = int(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "30"))
PROMETHEUS_RETRY_COUNT: int = int(os.getenv("PROMETHEUS_RETRY_COUNT", "3"))
PROMETHEUS_RETRY_BACKOFF_BASE: int = int(os.getenv("PROMETHEUS_RETRY_BACKOFF_BASE", "1"))
METRICS_WINDOW_MINUTES: int = int(os.getenv("METRICS_WINDOW_MINUTES", "7200"))
MIN_OBSERVATION_WINDOW_MINUTES: int = int(os.getenv("MIN_OBSERVATION_WINDOW_MINUTES", "10"))
CPU_BURST_RATIO_THRESHOLD: float = float(os.getenv("CPU_BURST_RATIO_THRESHOLD", "2.0"))
MEMORY_GROWTH_THRESHOLD_PERCENT: float = float(os.getenv("MEMORY_GROWTH_THRESHOLD_PERCENT", "10"))
MAX_ACCEPTABLE_OVERPROVISION_RATIO: float = float(os.getenv("MAX_ACCEPTABLE_OVERPROVISION_RATIO", "5.0"))
ENABLE_LOAD_GENERATION: bool = _env_bool("ENABLE_LOAD_GENERATION", False)
LOAD_GENERATION_TARGET_URL: Optional[str] = os.getenv("LOAD_GENERATION_TARGET_URL")
LOAD_GENERATION_DURATION_SECONDS: int = int(os.getenv("LOAD_GENERATION_DURATION_SECONDS", "300"))
LOAD_GENERATION_CONCURRENCY: int = int(os.getenv("LOAD_GENERATION_CONCURRENCY", "5"))
EXCLUDED_NAMESPACES: str = os.getenv("EXCLUDED_NAMESPACES", "kube-system,kube-public,istio-system")

# Output directory for cluster-specific files
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")

# Legacy single-file paths (deprecated, use get_analysis_output_path/get_insights_output_path instead)
ANALYSIS_OUTPUT_PATH: str = os.getenv("ANALYSIS_OUTPUT_PATH", "output/analysis_output.json")

# Multi-cluster run mode: "all" runs all clusters, "active" runs only ACTIVE_CLUSTER
RUN_MODE: str = os.getenv("RUN_MODE", "active")  # "all" or "active"


def get_analysis_output_path(cluster_name: str) -> str:
    """Get cluster-specific analysis output path: {cluster_name}_analysis_output.json"""
    return os.path.join(OUTPUT_DIR, f"{cluster_name}_analysis_output.json")


def get_insights_output_path(cluster_name: str) -> str:
    """Get cluster-specific insights output path: {cluster_name}_insights_output.json"""
    return os.path.join(OUTPUT_DIR, f"{cluster_name}_insights_output.json")


def get_clusters_to_run() -> List[Dict[str, Any]]:
    """Get list of clusters to run based on RUN_MODE"""
    if RUN_MODE == "all":
        return PROMETHEUS_ENDPOINTS
    else:
        # Return only the active cluster
        return [get_active_cluster_info()]

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
# Legacy single-file path (deprecated, use get_insights_output_path instead)
INSIGHTS_OUTPUT_PATH: str = os.getenv("INSIGHTS_OUTPUT_PATH", "output/insights_output.json")
LLM_MODE: str = os.getenv("LLM_MODE", "local")
LLM_ENDPOINT_URL: str = os.getenv("LLM_ENDPOINT_URL", "http://localhost:11434")
LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "llama3:8b")
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")  # For remote LLM authentication

# Phase 2: LLM Prompt Template (user-configurable)
# Instruction: review and modify this prompt as needed before enabling Phase 2
PHASE2_LLM_PROMPT: str = os.getenv("PHASE2_LLM_PROMPT", """OUTPUT ONLY THIS JSON STRUCTURE (replace placeholders with actual data from input):

{"summary":"Cluster status summary here","deployment_review":{"bursty":[],"underutilized":["coredns (CPU and memory underutilized)"],"memory_pressure":[],"unsafe_to_resize":[]},"hpa_review":{"at_threshold":[],"scaling_blocked":[],"scaling_down":[]},"node_fragmentation_review":{"fragmented_nodes":["demo-control-plane (87% CPU, 90% memory fragmentation)"],"large_request_pods":[],"constraint_blockers":[],"daemonset_overhead":[],"scale_down_blockers":[]},"cross_layer_risks":{"high":[],"medium":[]},"limitations":[]}

RULES:
- Replace example values with actual data from input
- Keep the EXACT structure and key names
- Use [] for empty arrays
- NO markdown, NO explanation, ONLY the JSON object
- Start with { and end with }

INPUT DATA:
""")


__all__ = [
    "PROMETHEUS_ENDPOINTS",
    "ACTIVE_CLUSTER",
    "get_active_prometheus_url",
    "get_active_cluster_info",
    "PROMETHEUS_URL",  # Legacy compatibility
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
    "OUTPUT_DIR",
    "RUN_MODE",
    "get_analysis_output_path",
    "get_insights_output_path",
    "get_clusters_to_run",
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
    
    # Validate Prometheus endpoints
    for i, endpoint in enumerate(PROMETHEUS_ENDPOINTS):
        url = endpoint.get("url", "")
        cluster_name = endpoint.get("cluster_name", f"endpoint[{i}]")
        try:
            _validate_url(f"PROMETHEUS_ENDPOINTS[{cluster_name}].url", url)
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

