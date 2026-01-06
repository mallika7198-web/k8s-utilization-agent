"""
Prometheus client for K8s metric queries
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import requests
import urllib3

# Suppress InsecureRequestWarning when using verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from config import (
    PROMETHEUS_URL, 
    PROMETHEUS_TIMEOUT_SECONDS, 
    METRICS_WINDOW_MINUTES,
    METRICS_STEP,
    PROMETHEUS_RETRY_COUNT,
    PROMETHEUS_RETRY_BACKOFF_BASE
)

# Configure logging
logger = logging.getLogger(__name__)


class PrometheusError(Exception):
    """Base exception for Prometheus client errors"""
    pass


class PrometheusConnectionError(PrometheusError):
    """Raised when connection to Prometheus fails"""
    pass


class PrometheusQueryError(PrometheusError):
    """Raised when a Prometheus query fails"""
    pass


def _retry_with_backoff(func):
    """Decorator to add retry logic with exponential backoff
    
    Uses configurable PROMETHEUS_RETRY_COUNT and PROMETHEUS_RETRY_BACKOFF_BASE
    """
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(PROMETHEUS_RETRY_COUNT):
            try:
                return func(*args, **kwargs)
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout) as e:
                last_exception = e
                wait_time = PROMETHEUS_RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"Prometheus request failed (attempt {attempt + 1}/{PROMETHEUS_RETRY_COUNT}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
        # All retries exhausted
        raise PrometheusConnectionError(
            f"Failed after {PROMETHEUS_RETRY_COUNT} retries: {last_exception}"
        )
    return wrapper


@_retry_with_backoff
def query_range(query: str, minutes: int = None) -> List[Dict[str, Any]]:
    """Query Prometheus for a range of metrics
    
    Args:
        query: PromQL query string
        minutes: Time window in minutes (default from config)
    
    Returns:
        List of result dictionaries from Prometheus
    
    Raises:
        PrometheusConnectionError: If connection fails after retries
        PrometheusQueryError: If query returns non-200 status
    """
    if minutes is None:
        minutes = METRICS_WINDOW_MINUTES
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    
    # Use Unix timestamps for Prometheus (most reliable format)
    params = {
        'query': query,
        'start': start_time.timestamp(),
        'end': end_time.timestamp(),
        'step': METRICS_STEP
    }
    
    logger.debug(f"Prometheus range query: {query[:100]}...")
    
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query_range",
        params=params,
        timeout=PROMETHEUS_TIMEOUT_SECONDS,
        verify=False
    )
    
    if response.status_code == 200:
        return response.json().get('data', {}).get('result', [])
    else:
        raise PrometheusQueryError(
            f"Query failed with status {response.status_code}: {response.text}"
        )


@_retry_with_backoff
def query_instant(query: str) -> List[Dict[str, Any]]:
    """Query Prometheus for instant metrics
    
    Args:
        query: PromQL query string
    
    Returns:
        List of result dictionaries from Prometheus
    
    Raises:
        PrometheusConnectionError: If connection fails after retries
        PrometheusQueryError: If query returns non-200 status
    """
    logger.debug(f"Prometheus instant query: {query[:100]}...")
    
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={'query': query},
        timeout=PROMETHEUS_TIMEOUT_SECONDS,
        verify=False
    )
    
    if response.status_code == 200:
        return response.json().get('data', {}).get('result', [])
    else:
        raise PrometheusQueryError(
            f"Query failed with status {response.status_code}: {response.text}"
        )


# Cache for repeated queries within same analysis run
_query_cache: Dict[str, Any] = {}


def query_instant_cached(query: str) -> List[Dict[str, Any]]:
    """Query Prometheus with caching for repeated queries
    
    Cache is cleared between analysis runs via clear_cache()
    """
    if query in _query_cache:
        logger.debug(f"Cache hit for query: {query[:50]}...")
        return _query_cache[query]
    
    result = query_instant(query)
    _query_cache[query] = result
    return result


def query_range_cached(query: str, minutes: int = None) -> List[Dict[str, Any]]:
    """Query Prometheus range with caching for repeated queries"""
    cache_key = f"range:{query}:{minutes or METRICS_WINDOW_MINUTES}"
    if cache_key in _query_cache:
        logger.debug(f"Cache hit for range query: {query[:50]}...")
        return _query_cache[cache_key]
    
    result = query_range(query, minutes)
    _query_cache[cache_key] = result
    return result


def clear_cache():
    """Clear the query cache between analysis runs"""
    global _query_cache
    _query_cache = {}
    logger.debug("Prometheus query cache cleared")
