#!/usr/bin/env python3
"""
Phase 3: Web UI for Kubernetes Utilization Analysis
Displays Phase 1 facts and Phase 2 LLM insights side-by-side

Tab Structure:
- Facts & Evidence (Phase 1): Authoritative data from Prometheus
- Insights (LLM) (Phase 2): Advisory interpretations for human review
- Raw JSON: Read-only display of both output files
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, jsonify, Response
from datetime import datetime

from config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Get the directory where ui.py is located
BASE_DIR = Path(__file__).parent.resolve()

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))

# Configuration - use paths from output directory
ANALYSIS_FILE = BASE_DIR / 'output' / 'analysis_output.json'
INSIGHTS_FILE = BASE_DIR / 'output' / 'insights_output.json'

# Metrics for observability
_metrics = {
    'requests_total': 0,
    'requests_by_endpoint': {},
    'errors_total': 0,
    'start_time': time.time()
}


def _record_request(endpoint: str):
    """Record request metrics"""
    _metrics['requests_total'] += 1
    _metrics['requests_by_endpoint'][endpoint] = _metrics['requests_by_endpoint'].get(endpoint, 0) + 1


def load_json(filepath):
    """Load JSON file safely"""
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            return None
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        _metrics['errors_total'] += 1
        return None


@app.route('/')
def index():
    """Main dashboard"""
    _record_request('/')
    analysis = load_json(ANALYSIS_FILE)
    insights = load_json(INSIGHTS_FILE)
    
    if not analysis:
        return render_template('error.html', 
                             message="Phase 1 analysis not found. Run: python orchestrator.py")
    
    return render_template('dashboard.html',
                         analysis=analysis,
                         insights=insights,
                         has_insights=insights is not None)


@app.route('/api/analysis')
def get_analysis():
    """API endpoint for analysis data"""
    _record_request('/api/analysis')
    data = load_json(ANALYSIS_FILE)
    if data:
        return jsonify(data)
    return jsonify({"error": "Not found"}), 404


@app.route('/api/insights')
def get_insights():
    """API endpoint for insights data"""
    _record_request('/api/insights')
    data = load_json(INSIGHTS_FILE)
    if data:
        return jsonify(data)
    return jsonify({"error": "Insights not available"}), 404


@app.route('/health')
def health():
    """Health check endpoint for liveness probes"""
    _record_request('/health')
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    })


@app.route('/ready')
def ready():
    """Readiness check endpoint - verifies analysis file exists"""
    _record_request('/ready')
    analysis = load_json(ANALYSIS_FILE)
    if analysis:
        return jsonify({
            "status": "ready",
            "analysis_available": True,
            "insights_available": load_json(INSIGHTS_FILE) is not None,
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        })
    return jsonify({
        "status": "not_ready",
        "reason": "Analysis file not found",
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }), 503


@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint for self-monitoring"""
    _record_request('/metrics')
    uptime = time.time() - _metrics['start_time']
    
    # Generate Prometheus-format metrics
    lines = [
        "# HELP k8s_ui_requests_total Total number of HTTP requests",
        "# TYPE k8s_ui_requests_total counter",
        f"k8s_ui_requests_total {_metrics['requests_total']}",
        "",
        "# HELP k8s_ui_errors_total Total number of errors",
        "# TYPE k8s_ui_errors_total counter",
        f"k8s_ui_errors_total {_metrics['errors_total']}",
        "",
        "# HELP k8s_ui_uptime_seconds UI uptime in seconds",
        "# TYPE k8s_ui_uptime_seconds gauge",
        f"k8s_ui_uptime_seconds {uptime:.2f}",
        "",
        "# HELP k8s_ui_analysis_available Whether analysis file exists",
        "# TYPE k8s_ui_analysis_available gauge",
        f"k8s_ui_analysis_available {1 if load_json(ANALYSIS_FILE) else 0}",
        "",
        "# HELP k8s_ui_insights_available Whether insights file exists",
        "# TYPE k8s_ui_insights_available gauge",
        f"k8s_ui_insights_available {1 if load_json(INSIGHTS_FILE) else 0}",
    ]
    
    # Add per-endpoint metrics
    lines.append("")
    lines.append("# HELP k8s_ui_requests_by_endpoint Requests per endpoint")
    lines.append("# TYPE k8s_ui_requests_by_endpoint counter")
    for endpoint, count in _metrics['requests_by_endpoint'].items():
        safe_endpoint = endpoint.replace('/', '_').strip('_') or 'root'
        lines.append(f'k8s_ui_requests_by_endpoint{{endpoint="{endpoint}"}} {count}')
    
    return Response('\n'.join(lines), mimetype='text/plain')


if __name__ == '__main__':
    logger.info("🎯 Kubernetes Utilization Analysis UI")
    logger.info("📊 Dashboard: http://127.0.0.1:8080")
    logger.info("❤️  Health: http://127.0.0.1:8080/health")
    logger.info("✅ Ready: http://127.0.0.1:8080/ready")
    logger.info("📈 Metrics: http://127.0.0.1:8080/metrics")
    logger.info("🛑 Stop with: Ctrl+C")
    app.run(debug=False, host='127.0.0.1', port=8080)
