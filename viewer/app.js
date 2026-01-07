/**
 * Kubernetes Capacity Analysis Viewer
 * 
 * Static JavaScript application to view K8s capacity analysis JSON files.
 * No backend required - loads JSON via fetch() from /output/ directory.
 */

// =============================================================================
// State
// =============================================================================
let currentData = null;

// =============================================================================
// DOM Elements
// =============================================================================
const projectSelect = document.getElementById('project-select');
const envSelect = document.getElementById('env-select');
const loadBtn = document.getElementById('load-btn');
const errorDisplay = document.getElementById('error-display');
const errorMessage = document.getElementById('error-message');

// Header elements
const clusterName = document.getElementById('cluster-name');
const envBadge = document.getElementById('env-badge');
const projectName = document.getElementById('project-name');
const generatedAt = document.getElementById('generated-at');

// Summary elements
const podResizeCount = document.getElementById('pod-resize-count');
const nodeRightsizeCount = document.getElementById('node-rightsize-count');
const hpaMisalignmentCount = document.getElementById('hpa-misalignment-count');

// Content areas
const podResizeContent = document.getElementById('pod-resize-content');
const nodeRightsizeContent = document.getElementById('node-rightsize-content');
const hpaMisalignmentContent = document.getElementById('hpa-misalignment-content');
const limitationsContent = document.getElementById('limitations-content');

// =============================================================================
// Initialization
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    initControls();
    discoverProjects();
});

/**
 * Initialize control event listeners
 */
function initControls() {
    loadBtn.addEventListener('click', loadAnalysis);
    projectSelect.addEventListener('change', updateLoadButton);
    envSelect.addEventListener('change', updateLoadButton);
}

/**
 * Update load button state
 */
function updateLoadButton() {
    const projectValue = projectSelect.value || 
                         document.getElementById('project-input')?.value;
    loadBtn.disabled = !projectValue || !envSelect.value;
}

// =============================================================================
// Project Discovery
// =============================================================================

/**
 * Attempt to discover available projects
 */
async function discoverProjects() {
    // Try loading manifest first
    try {
        const response = await fetch('/output/manifest.json');
        if (response.ok) {
            const manifest = await response.json();
            populateProjects(manifest.projects || []);
            return;
        }
    } catch (e) {
        // Continue to probing
    }

    // Probe for common project names
    const potentialProjects = [
        'local-kind',
        'local',
        'default',
        'production',
        'staging',
        'development'
    ];

    const foundProjects = [];
    for (const project of potentialProjects) {
        try {
            const prodResp = await fetch(`/output/${project}/prod/analysis.json`, { method: 'HEAD' });
            const nonprodResp = await fetch(`/output/${project}/nonprod/analysis.json`, { method: 'HEAD' });
            if (prodResp.ok || nonprodResp.ok) {
                foundProjects.push(project);
            }
        } catch (e) {
            // Project not found
        }
    }

    if (foundProjects.length > 0) {
        populateProjects(foundProjects);
    } else {
        // Fall back to text input
        enableManualInput();
    }
}

/**
 * Populate project dropdown
 */
function populateProjects(projects) {
    projectSelect.innerHTML = '<option value="">-- Select --</option>';
    projects.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p;
        projectSelect.appendChild(opt);
    });
}

/**
 * Enable manual project input
 */
function enableManualInput() {
    const container = projectSelect.parentElement;
    container.innerHTML = `
        <label for="project-input">Project:</label>
        <input type="text" id="project-input" placeholder="Enter project name">
    `;
    document.getElementById('project-input').addEventListener('input', updateLoadButton);
}

// =============================================================================
// Data Loading
// =============================================================================

/**
 * Load analysis JSON for selected project/environment
 */
async function loadAnalysis() {
    const project = projectSelect?.value || document.getElementById('project-input')?.value;
    const env = envSelect.value;

    if (!project || !env) {
        showError('Please select both project and environment.');
        return;
    }

    const url = `/output/${project}/${env}/analysis.json`;

    try {
        hideError();
        loadBtn.disabled = true;
        loadBtn.textContent = 'Loading...';

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`File not found: ${url}`);
        }

        currentData = await response.json();
        renderAll();

    } catch (error) {
        showError(`Failed to load analysis: ${error.message}`);
    } finally {
        loadBtn.disabled = false;
        loadBtn.textContent = 'Load Analysis';
        updateLoadButton();
    }
}

// =============================================================================
// Rendering
// =============================================================================

/**
 * Render all sections
 */
function renderAll() {
    if (!currentData) return;

    renderHeader();
    renderSummary();
    renderPodResize();
    renderNodeRightsize();
    renderHPAMisalignment();
    renderLimitations();
}

/**
 * Render header metadata
 */
function renderHeader() {
    clusterName.textContent = currentData.cluster || '--';
    projectName.textContent = currentData.project || '--';
    generatedAt.textContent = formatTimestamp(currentData.generated_at);

    const env = currentData.env || 'unknown';
    envBadge.textContent = env;
    envBadge.className = env === 'prod' ? 'prod' : 'nonprod';
}

/**
 * Render summary counts
 */
function renderSummary() {
    const summary = currentData.summary || {};
    
    // Support both new format (pods.affected) and legacy format (pod_resize_count)
    const podAffected = summary.pods?.affected ?? summary.pod_resize_count ?? 0;
    const nodeAffected = summary.nodes?.affected ?? summary.node_rightsize_count ?? 0;
    const hpaAffected = summary.hpa?.affected ?? summary.hpa_misalignment_count ?? 0;
    
    podResizeCount.textContent = podAffected;
    nodeRightsizeCount.textContent = nodeAffected;
    hpaMisalignmentCount.textContent = hpaAffected;
    
    // Update summary text if available (new format)
    const podSummaryText = document.getElementById('pod-summary-text');
    const nodeSummaryText = document.getElementById('node-summary-text');
    const hpaSummaryText = document.getElementById('hpa-summary-text');
    
    if (podSummaryText && summary.pods?.text) {
        podSummaryText.textContent = summary.pods.text;
    }
    if (nodeSummaryText && summary.nodes?.text) {
        nodeSummaryText.textContent = summary.nodes.text;
    }
    if (hpaSummaryText && summary.hpa?.text) {
        hpaSummaryText.textContent = summary.hpa.text;
    }
    
    // Render potential savings
    const savingsCount = document.getElementById('savings-count');
    const savingsSummaryText = document.getElementById('savings-summary-text');
    const savingsCard = document.querySelector('.savings-card');
    
    if (summary.potential_savings) {
        const cpuSavings = summary.potential_savings.cpu_cores || 0;
        const memSavingsGb = summary.potential_savings.memory_gb || 0;
        const memSavingsMb = summary.potential_savings.memory_mb || 0;
        
        // Build display parts
        let displayParts = [];
        
        if (cpuSavings > 0.01) {
            displayParts.push(`↓${cpuSavings.toFixed(2)} cores`);
        } else if (cpuSavings < -0.01) {
            displayParts.push(`↑${Math.abs(cpuSavings).toFixed(2)} cores`);
        }
        
        if (memSavingsGb >= 1) {
            displayParts.push(`↓${memSavingsGb.toFixed(1)}GB`);
        } else if (memSavingsGb <= -1) {
            displayParts.push(`↑${Math.abs(memSavingsGb).toFixed(1)}GB`);
        } else if (memSavingsMb > 10) {
            displayParts.push(`↓${Math.abs(memSavingsMb).toFixed(0)}MB`);
        } else if (memSavingsMb < -10) {
            displayParts.push(`↑${Math.abs(memSavingsMb).toFixed(0)}MB`);
        }
        
        savingsCount.textContent = displayParts.length > 0 ? displayParts.join(' ') : '--';
        savingsSummaryText.textContent = summary.potential_savings.text || '';
        
        // Color the card based on net savings direction
        // If we save more than we need, it's positive overall
        const netPositive = cpuSavings > 0 || (cpuSavings === 0 && memSavingsGb > 0);
        const netNegative = cpuSavings < 0 || (cpuSavings === 0 && memSavingsGb < 0);
        
        if (netPositive) {
            savingsCard?.classList.add('positive');
            savingsCard?.classList.remove('negative');
        } else if (netNegative) {
            savingsCard?.classList.add('negative');
            savingsCard?.classList.remove('positive');
        }
    }
}

/**
 * Render POD_RESIZE recommendations
 */
function renderPodResize() {
    const recs = (currentData.recommendations || []).filter(r => r.type === 'POD_RESIZE');

    if (recs.length === 0) {
        podResizeContent.innerHTML = '<p class="empty-state">No pod resize recommendations.</p>';
        return;
    }

    let html = '';
    for (const rec of recs) {
        // Calculate savings display
        const cpuSavings = rec.savings?.cpu_cores || 0;
        const memSavingsMb = rec.savings?.memory_mb || 0;
        const hasSavings = Math.abs(cpuSavings) > 0.001 || Math.abs(memSavingsMb) > 0.1;
        
        let savingsHtml = '';
        if (hasSavings) {
            // Positive = we can save (reduce), Negative = we need more (increase)
            const cpuIcon = cpuSavings > 0 ? '↓' : '↑';
            const cpuClass = cpuSavings > 0 ? 'savings-positive' : 'savings-negative';
            const cpuText = `${cpuIcon}${Math.abs(cpuSavings).toFixed(3)} cores`;
            
            const memIcon = memSavingsMb > 0 ? '↓' : '↑';
            const memClass = memSavingsMb > 0 ? 'savings-positive' : 'savings-negative';
            const memText = `${memIcon}${Math.abs(memSavingsMb).toFixed(0)} MB`;
            
            savingsHtml = `
                <div class="savings-row">
                    <span class="savings-label">Impact:</span>
                    <span class="${cpuClass}">${cpuText}</span>
                    <span class="savings-sep">|</span>
                    <span class="${memClass}">${memText}</span>
                </div>
            `;
        }
        
        html += `
            <div class="rec-card">
                <div class="rec-card-header">
                    <div>
                        <div class="rec-card-title">${esc(rec.pod)}</div>
                        <div class="rec-card-subtitle">${esc(rec.namespace)}</div>
                    </div>
                </div>
                ${savingsHtml}
                <div class="data-grid">
                    <div class="data-item">
                        <span class="data-label">Current CPU Req</span>
                        <span class="data-value">${formatCPU(rec.current?.cpu_request)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Recommended CPU Req</span>
                        <span class="data-value">${formatCPU(rec.recommended?.cpu_request)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Current Mem Req</span>
                        <span class="data-value">${formatMemory(rec.current?.memory_request)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Recommended Mem Req</span>
                        <span class="data-value">${formatMemory(rec.recommended?.memory_request)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">CPU P95</span>
                        <span class="data-value">${formatCPU(rec.usage_percentiles?.cpu_p95)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">CPU P99</span>
                        <span class="data-value">${formatCPU(rec.usage_percentiles?.cpu_p99)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Mem P95</span>
                        <span class="data-value">${formatMemory(rec.usage_percentiles?.memory_p95)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Mem P99</span>
                        <span class="data-value">${formatMemory(rec.usage_percentiles?.memory_p99)}</span>
                    </div>
                </div>
                <div class="explanation">${esc(rec.explanation)}</div>
            </div>
        `;
    }

    podResizeContent.innerHTML = html;
}

/**
 * Render NODE_RIGHTSIZE recommendations
 */
function renderNodeRightsize() {
    const recs = (currentData.recommendations || []).filter(r => r.type === 'NODE_RIGHTSIZE');

    if (recs.length === 0) {
        nodeRightsizeContent.innerHTML = '<p class="empty-state">No node right-size recommendations.</p>';
        return;
    }

    let html = '';
    for (const rec of recs) {
        const badgeClass = rec.direction === 'down' ? 'down' : 'right-size';
        const fragmentation = rec.metrics?.cpu_fragmentation_undefined 
            ? 'N/A' 
            : formatPercent(rec.metrics?.cpu_fragmentation);
        
        // Support both new format (memory_allocatable.gb) and legacy (memory_allocatable_bytes)
        const memAllocatable = rec.metrics?.memory_allocatable?.gb 
            ? `${rec.metrics.memory_allocatable.gb} GB`
            : formatMemory(rec.metrics?.memory_allocatable_bytes);
        
        // Get recommendation action/meaning if available (new format)
        const action = rec.recommendation?.action || rec.direction?.toUpperCase();
        const meaning = rec.recommendation?.meaning || '';

        html += `
            <div class="rec-card">
                <div class="rec-card-header">
                    <div>
                        <div class="rec-card-title">${esc(rec.node)}</div>
                        <div class="rec-card-subtitle">Node</div>
                    </div>
                    <span class="rec-badge ${badgeClass}">${esc(action)}</span>
                </div>
                ${meaning ? `<div class="rec-meaning">${esc(meaning)}</div>` : ''}
                <div class="data-grid">
                    <div class="data-item">
                        <span class="data-label">CPU Fragmentation</span>
                        <span class="data-value">${fragmentation}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Node Efficiency</span>
                        <span class="data-value">${formatPercent(rec.metrics?.node_efficiency)}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Pods on Node</span>
                        <span class="data-value">${rec.metrics?.pods_on_node ?? '--'}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">CPU Allocatable</span>
                        <span class="data-value">${rec.metrics?.cpu_allocatable ?? '--'} cores</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Memory Allocatable</span>
                        <span class="data-value">${memAllocatable}</span>
                    </div>
                </div>
                <div class="explanation">${esc(rec.explanation)}</div>
                ${rec.limitation ? `<div class="limitation-text">${esc(rec.limitation)}</div>` : ''}
            </div>
        `;
    }

    nodeRightsizeContent.innerHTML = html;
}

/**
 * Render HPA_MISALIGNMENT recommendations
 */
function renderHPAMisalignment() {
    const recs = (currentData.recommendations || []).filter(r => r.type === 'HPA_MISALIGNMENT');

    if (recs.length === 0) {
        hpaMisalignmentContent.innerHTML = '<p class="empty-state">No HPA misalignment detected.</p>';
        return;
    }

    let html = '';
    for (const rec of recs) {
        const reasons = rec.reasons || [];
        const reasonsHtml = reasons.length > 0 
            ? `<ul class="reasons-list">${reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`
            : '';

        html += `
            <div class="rec-card">
                <div class="rec-card-header">
                    <div>
                        <div class="rec-card-title">${esc(rec.hpa)}</div>
                        <div class="rec-card-subtitle">${esc(rec.namespace)} | Target: ${esc(rec.target?.target_kind)}/${esc(rec.target?.target_name)}</div>
                    </div>
                </div>
                <div class="data-grid">
                    <div class="data-item">
                        <span class="data-label">Min Replicas</span>
                        <span class="data-value">${rec.config?.min_replicas ?? '--'}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Max Replicas</span>
                        <span class="data-value">${rec.config?.max_replicas ?? '--'}</span>
                    </div>
                    <div class="data-item">
                        <span class="data-label">Current Replicas</span>
                        <span class="data-value">${rec.config?.current_replicas ?? '--'}</span>
                    </div>
                </div>
                <div style="margin-top: 12px;">
                    <span class="data-label">Reasons</span>
                    ${reasonsHtml}
                </div>
                ${rec.limitation ? `<div class="limitation-text">${esc(rec.limitation)}</div>` : ''}
            </div>
        `;
    }

    hpaMisalignmentContent.innerHTML = html;
}

/**
 * Render limitations section (always visible)
 */
function renderLimitations() {
    const limitations = currentData.limitations || [];

    if (limitations.length === 0) {
        limitationsContent.innerHTML = '<p class="empty-state">No limitations reported.</p>';
        return;
    }

    let html = '';
    for (const lim of limitations) {
        html += `<div class="limitation-item">${esc(lim)}</div>`;
    }

    limitationsContent.innerHTML = html;
}

// =============================================================================
// Utilities
// =============================================================================

/**
 * Escape HTML to prevent XSS
 */
function esc(text) {
    if (text === null || text === undefined) return '--';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

/**
 * Format CPU value
 */
function formatCPU(value) {
    if (value === null || value === undefined) return '--';
    if (value < 1) {
        return `${Math.round(value * 1000)}m`;
    }
    return `${value.toFixed(2)} cores`;
}

/**
 * Format memory value (bytes to human readable)
 */
function formatMemory(bytes) {
    if (bytes === null || bytes === undefined) return '--';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
        val /= 1024;
        i++;
    }
    return `${val.toFixed(1)} ${units[i]}`;
}

/**
 * Format percentage (0-1 to %)
 */
function formatPercent(value) {
    if (value === null || value === undefined) return '--';
    return `${(value * 100).toFixed(1)}%`;
}

/**
 * Format ISO timestamp
 */
function formatTimestamp(iso) {
    if (!iso) return '--';
    try {
        return new Date(iso).toLocaleString();
    } catch (e) {
        return iso;
    }
}

/**
 * Show error message
 */
function showError(msg) {
    errorMessage.textContent = msg;
    errorDisplay.classList.remove('hidden');
}

/**
 * Hide error message
 */
function hideError() {
    errorDisplay.classList.add('hidden');
}
