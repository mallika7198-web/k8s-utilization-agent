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
import os
from pathlib import Path
from flask import Flask, render_template, jsonify
from datetime import datetime

# Get the directory where ui.py is located
BASE_DIR = Path(__file__).parent.resolve()

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))

# Configuration - use paths from output directory
ANALYSIS_FILE = BASE_DIR / 'output' / 'analysis_output.json'
INSIGHTS_FILE = BASE_DIR / 'output' / 'insights_output.json'


def load_json(filepath):
    """Load JSON file safely"""
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            return None
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None


@app.route('/')
def index():
    """Main dashboard"""
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
    data = load_json(ANALYSIS_FILE)
    if data:
        return jsonify(data)
    return jsonify({"error": "Not found"}), 404


@app.route('/api/insights')
def get_insights():
    """API endpoint for insights data"""
    data = load_json(INSIGHTS_FILE)
    if data:
        return jsonify(data)
    return jsonify({"error": "Insights not available"}), 404


if __name__ == '__main__':
    print("🎯 Kubernetes Utilization Analysis UI")
    print("📊 Dashboard: http://127.0.0.1:8080")
    print("🛑 Stop with: Ctrl+C")
    app.run(debug=False, host='127.0.0.1', port=8080)
