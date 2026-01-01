"""
Prometheus client for K8s metric queries
"""
from datetime import datetime, timedelta
import requests
from config import PROMETHEUS_URL, PROMETHEUS_TIMEOUT_SECONDS, METRICS_WINDOW_MINUTES


def query_range(query: str, minutes: int = None):
    """Query Prometheus for a range of metrics"""
    if minutes is None:
        minutes = METRICS_WINDOW_MINUTES
    
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=minutes)
        
        params = {
            'query': query,
            'start': start_time.isoformat() + 'Z',
            'end': end_time.isoformat() + 'Z',
            'step': '1m'
        }
        
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params=params,
            timeout=PROMETHEUS_TIMEOUT_SECONDS
        )
        
        if response.status_code == 200:
            return response.json().get('data', {}).get('result', [])
        else:
            return []
    except Exception as e:
        print(f"Prometheus query failed: {e}")
        return []


def query_instant(query: str):
    """Query Prometheus for instant metrics"""
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={'query': query},
            timeout=PROMETHEUS_TIMEOUT_SECONDS
        )
        
        if response.status_code == 200:
            return response.json().get('data', {}).get('result', [])
        else:
            return []
    except Exception as e:
        print(f"Prometheus instant query failed: {e}")
        return []
