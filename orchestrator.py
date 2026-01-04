"""Orchestrator: run discovery -> analysis -> aggregate -> atomic write.
Copilot: Phase-1 Analysis only. No LLM. No suggestions. Deterministic facts and flags only. Prometheus is the source of truth. All configuration from config.py. Update tracker.json for every change.
"""
import logging
from datetime import datetime, timezone
import json
import os
import tempfile
from typing import List, Dict, Any

from config import (
    setup_logging, validate_config, ConfigValidationError,
    PROMETHEUS_ENDPOINTS, get_clusters_to_run, get_analysis_output_path,
    RUN_MODE, OUTPUT_DIR
)
from metrics import discovery as discovery_mod
from metrics import prometheus_client as prom
from metrics.prometheus_client import PrometheusError, clear_cache
from analysis import deployment_analysis as dep_analysis
from analysis import hpa_analysis as hpa_analysis_mod
from analysis import node_analysis as node_analysis_mod
from tracker import append_change

# Configure logging
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, data: str) -> None:
    dirp = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.tmp_analysis_', dir=dirp)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(data)
        # Atomic replace
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


# use tracker.append_change for append-only updates (best-effort)


def run_once_for_cluster(cluster_info: Dict[str, Any]) -> Dict[str, Any]:
    """Run analysis for a single cluster
    
    Args:
        cluster_info: Dict with cluster_name, url, project, environment, owner
        
    Returns:
        Analysis output dict
    """
    cluster_name = cluster_info.get('cluster_name', 'unknown')
    prometheus_url = cluster_info.get('url', 'http://localhost:9090')
    
    logger.info(f"Analyzing cluster: {cluster_name}")
    logger.info(f"Prometheus URL: {prometheus_url}")
    
    # Clear prometheus cache for fresh run
    clear_cache()
    
    # Set the Prometheus URL for this cluster
    prom.PROMETHEUS_URL = prometheus_url
    
    # 1) Check Prometheus connectivity first
    prometheus_available = False
    try:
        prom.query_range('up')
        prometheus_available = True
        logger.info(f"[{cluster_name}] Prometheus connection verified")
    except PrometheusError as e:
        logger.warning(f"[{cluster_name}] PROMETHEUS NOT REACHABLE: {e}")
        logger.warning(f"[{cluster_name}] Expected URL: {prometheus_url}")
        logger.warning(f"[{cluster_name}] Proceeding with empty metrics...")
    except Exception as e:
        logger.warning(f"[{cluster_name}] PROMETHEUS CONNECTION ERROR: {e}")
        logger.warning(f"[{cluster_name}] Proceeding with empty metrics...")

    # 2) Discovery
    deps = discovery_mod.discover_deployments()
    hpas = discovery_mod.discover_hpas()
    nodes = discovery_mod.discover_nodes()

    discovery_filters = {
        'deployments': deps.get('discovery_filters'),
        'hpas': {},
        'nodes': {},
    }

    # 3) Analyze deployments
    deployment_results: List[Dict[str, Any]] = dep_analysis.analyze_deployments(
        deps.get('deployments', [])
    )

    # 4) HPA analysis
    hpa_results: List[Dict[str, Any]] = hpa_analysis_mod.analyze_hpas(
        hpas.get('hpas', [])
    )

    # 5) Node analysis
    node_result = node_analysis_mod.analyze_nodes(
        nodes.get('nodes', [])
    )

    # 6) Aggregate
    output: Dict[str, Any] = {
        'generated_at': _now_iso(),
        'cluster_info': {
            'cluster_name': cluster_name,
            'project': cluster_info.get('project', ''),
            'environment': cluster_info.get('environment', ''),
            'owner': cluster_info.get('owner', ''),
            'prometheus_url': prometheus_url,
        },
        'cluster_summary': {
            'deployment_count': len(deployment_results),
            'hpa_count': len(hpa_results),
            'node_count': len(nodes.get('nodes', [])),
        },
        'analysis_scope': discovery_filters,
        'deployment_analysis': deployment_results,
        'hpa_analysis': hpa_results,
        'node_analysis': node_result,
        'cross_layer_observations': [],
    }

    return output


def run_once() -> Dict[str, Any]:
    """Legacy single-cluster run (uses active cluster)
    
    Kept for backward compatibility. Prefer run_all_clusters() for multi-cluster.
    """
    from config import get_active_cluster_info
    return run_once_for_cluster(get_active_cluster_info())


def main() -> int:
    # Setup logging first
    setup_logging()
    
    # Validate configuration
    try:
        validate_config()
        logger.info("Configuration validated successfully")
    except ConfigValidationError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Get clusters to process
    clusters = get_clusters_to_run()
    logger.info(f"Starting Kubernetes Utilization Analysis (mode={RUN_MODE})")
    logger.info(f"Processing {len(clusters)} cluster(s)...")
    
    success_count = 0
    failed_count = 0
    output_files = []
    
    # Loop through clusters one by one
    for cluster_info in clusters:
        cluster_name = cluster_info.get('cluster_name', 'unknown')
        output_path = get_analysis_output_path(cluster_name)
        
        logger.info("=" * 60)
        logger.info(f"Processing cluster: {cluster_name}")
        logger.info("=" * 60)
        
        try:
            out = run_once_for_cluster(cluster_info)
            
            # Write atomically
            _atomic_write(output_path, json.dumps(out, indent=2))
            logger.info(f"[{cluster_name}] Wrote analysis to {output_path}")
            
            output_files.append(output_path)
            success_count += 1
            
        except Exception as e:
            logger.error(f"[{cluster_name}] Analysis failed: {e}")
            failed_count += 1
            continue

    # Update tracker.json best-effort using append-only utility
    if output_files:
        try:
            append_change({
                'files_modified': output_files,
                'type': 'analysis',
                'description': f'Orchestrator run: {success_count} cluster(s) analyzed (mode={RUN_MODE})'
            })
        except Exception as e:
            logger.warning(f"Failed to update tracker: {e}")

    logger.info("=" * 60)
    logger.info(f"Analysis complete: {success_count} succeeded, {failed_count} failed")
    logger.info(f"Output files: {output_files}")
    logger.info("=" * 60)
    
    return 0 if failed_count == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
