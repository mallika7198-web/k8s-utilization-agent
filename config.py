import os
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


# Prometheus Configuration
PROMETHEUS_URL: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
PROMETHEUS_TIMEOUT_SECONDS: int = int(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "30"))

# Metrics Collection Window
METRICS_WINDOW_MINUTES: int = int(os.getenv("METRICS_WINDOW_MINUTES", "15"))
MIN_OBSERVATION_WINDOW_MINUTES: int = int(os.getenv("MIN_OBSERVATION_WINDOW_MINUTES", "10"))

# Analysis Thresholds
CPU_BURST_RATIO_THRESHOLD: float = float(os.getenv("CPU_BURST_RATIO_THRESHOLD", "2.0"))
MEMORY_GROWTH_THRESHOLD_PERCENT: float = float(os.getenv("MEMORY_GROWTH_THRESHOLD_PERCENT", "10"))
MAX_ACCEPTABLE_OVERPROVISION_RATIO: float = float(os.getenv("MAX_ACCEPTABLE_OVERPROVISION_RATIO", "5.0"))

# Load Generation (Optional)
ENABLE_LOAD_GENERATION: bool = _env_bool("ENABLE_LOAD_GENERATION", False)
LOAD_GENERATION_TARGET_URL: Optional[str] = os.getenv("LOAD_GENERATION_TARGET_URL")
LOAD_GENERATION_DURATION_SECONDS: int = int(os.getenv("LOAD_GENERATION_DURATION_SECONDS", "300"))
LOAD_GENERATION_CONCURRENCY: int = int(os.getenv("LOAD_GENERATION_CONCURRENCY", "5"))

# Kubernetes Configuration
EXCLUDED_NAMESPACES: str = os.getenv("EXCLUDED_NAMESPACES", "kube-system,kube-public,istio-system")

# Output
ANALYSIS_OUTPUT_PATH: str = os.getenv("ANALYSIS_OUTPUT_PATH", "output/analysis_output.json")


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
]
