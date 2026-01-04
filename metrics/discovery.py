"""
Kubernetes discovery from Prometheus
"""
from metrics import prometheus_client as prom


def discover_deployments():
    """Discover deployments from Prometheus
    
    Tries multiple metric sources for maximum compatibility
    """
    deployments_dict = {}
    
    # Try multiple metric sources - prioritize kube-state-metrics
    for metric_name in [
        'kube_deployment_spec_replicas',
        'kube_deployment_status_replicas',
        'kube_deployment_labels', 
        'kube_deployment_info'
    ]:
        try:
            metrics = prom.query_instant(metric_name)
            for metric in metrics:
                labels = metric.get('metric', {})
                deployment = labels.get('deployment')
                namespace = labels.get('namespace') or 'default'
                
                if deployment:
                    key = f"{namespace}/{deployment}"
                    if key not in deployments_dict:
                        # Get replicas from the metric value if this is a replicas metric
                        replicas = 1
                        if 'replicas' in metric_name:
                            value = metric.get('value', [None, None])[1]
                            replicas = int(float(value)) if value else 1
                        else:
                            replicas = _get_deployment_replicas(deployment, namespace)
                        
                        deployments_dict[key] = {
                            'name': deployment,
                            'namespace': namespace,
                            'replicas': replicas
                        }
        except Exception:
            continue
    
    return {
        'discovery_filters': {},
        'deployments': list(deployments_dict.values())
    }


def discover_hpas():
    """Discover HPAs from Prometheus
    
    Tries multiple metric sources for maximum compatibility
    """
    hpas = {}
    
    # Try multiple metric sources - prioritize kube-state-metrics
    for metric_name in [
        'kube_horizontalpodautoscaler_spec_max_replicas',
        'kube_horizontalpodautoscaler_info',
        'kube_hpa_labels', 
        'kube_hpa_info'
    ]:
        try:
            metrics = prom.query_instant(metric_name)
            for metric in metrics:
                labels = metric.get('metric', {})
                # HPA name can be under different keys
                hpa_name = labels.get('horizontalpodautoscaler') or labels.get('hpa')
                namespace = labels.get('namespace') or 'default'
                
                if hpa_name:
                    key = f"{namespace}/{hpa_name}"
                    if key not in hpas:
                        # Get min/max replicas from Prometheus
                        min_replicas = _get_hpa_min_replicas(hpa_name, namespace)
                        max_replicas = _get_hpa_max_replicas(hpa_name, namespace)
                        
                        hpas[key] = {
                            'name': hpa_name,
                            'namespace': namespace,
                            'min_replicas': min_replicas,
                            'max_replicas': max_replicas
                        }
        except Exception:
            continue
    
    return {
        'hpas': list(hpas.values())
    }


def discover_nodes():
    """Discover nodes from Prometheus"""
    nodes = []
    
    # Primary: node_uname_info (most reliable)
    try:
        metrics = prom.query_instant('node_uname_info')
        for metric in metrics:
            labels = metric.get('metric', {})
            node_name = labels.get('node') or labels.get('nodename')
            
            if node_name:
                nodes.append({
                    'name': node_name,
                    'labels': labels
                })
    except Exception:
        pass
    
    # Fallback: kube_node_info
    if not nodes:
        try:
            metrics = prom.query_instant('kube_node_info')
            for metric in metrics:
                labels = metric.get('metric', {})
                node_name = labels.get('node')
                
                if node_name:
                    nodes.append({
                        'name': node_name,
                        'labels': labels
                    })
        except Exception:
            pass
    
    return {
        'nodes': nodes
    }


def _get_deployment_replicas(deployment: str, namespace: str):
    """Get desired replicas for deployment"""
    try:
        query = f'kube_deployment_spec_replicas{{deployment="{deployment}",namespace="{namespace}"}}'
        result = prom.query_instant(query)
        if result:
            value = result[0].get('value', [None, None])[1]
            return int(float(value)) if value else 1
    except Exception:
        pass
    
    return 1


def _get_hpa_min_replicas(hpa_name: str, namespace: str):
    """Get min replicas for HPA"""
    try:
        query = f'kube_horizontalpodautoscaler_spec_min_replicas{{horizontalpodautoscaler="{hpa_name}",namespace="{namespace}"}}'
        result = prom.query_instant(query)
        if result:
            value = result[0].get('value', [None, None])[1]
            return int(float(value)) if value else 1
    except Exception:
        pass
    
    return 1


def _get_hpa_max_replicas(hpa_name: str, namespace: str):
    """Get max replicas for HPA"""
    try:
        query = f'kube_horizontalpodautoscaler_spec_max_replicas{{horizontalpodautoscaler="{hpa_name}",namespace="{namespace}"}}'
        result = prom.query_instant(query)
        if result:
            value = result[0].get('value', [None, None])[1]
            return int(float(value)) if value else 10
    except Exception:
        pass
    
    return 10
