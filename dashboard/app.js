// Vigillix Dashboard App Logic
const API_BASE = "http://localhost:8000";
const STORE_ID = "ST1008";

let trendsChart = null;
let currentCamera = "CAM_ENTRY_01";
let activeDetectionsCount = 0;

// Setup Chart.js with premium orange gradient
function initChart() {
    const ctx = document.getElementById('trends-chart').getContext('2d');
    
    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, 'rgba(255, 107, 53, 0.4)');
    gradient.addColorStop(1, 'rgba(255, 107, 53, 0.0)');

    trendsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['10:00 AM', '11:00 AM', '12:00 PM', '01:00 PM', '02:00 PM', '03:00 PM', '04:00 PM'],
            datasets: [{
                label: 'Unique Visitors',
                data: [5, 18, 32, 21, 26, 38, 42],
                borderColor: '#ff6b35',
                borderWidth: 3,
                backgroundColor: gradient,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#ff6b35',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                },
                y: {
                    grid: { color: '#f1f5f9' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                }
            }
        }
    });
}

// Simulated CCTV Video Player with dynamic Bounding Boxes
const canvas = document.getElementById('cctv-canvas');
const ctx = canvas.getContext('2d');

const mockPeople = {
    CAM_ENTRY_01: [
        { x: 100, y: 150, dx: 1.5, dy: 0, w: 40, h: 100, id: 'VIS_c4a1', color: '#ff6b35', tag: 'Visitor' },
        { x: 300, y: 110, dx: -1, dy: 0.5, w: 45, h: 110, id: 'STF_192', color: '#8b5cf6', tag: 'Staff' }
    ],
    CAM_FLOOR_01: [
        { x: 200, y: 180, dx: 0.5, dy: 0, w: 50, h: 120, id: 'VIS_c4a1', color: '#ff6b35', tag: 'Visitor' },
        { x: 450, y: 160, dx: -1, dy: -0.2, w: 42, h: 100, id: 'VIS_c910', color: '#ff6b35', tag: 'Visitor' }
    ],
    CAM_BILLING_01: [
        { x: 150, y: 140, dx: 0, dy: 0, w: 45, h: 110, id: 'VIS_c4a1', color: '#ff6b35', tag: 'Queue Pos 1' },
        { x: 230, y: 150, dx: 0.2, dy: -0.1, w: 40, h: 100, id: 'VIS_c910', color: '#ff6b35', tag: 'Queue Pos 2' },
        { x: 480, y: 120, dx: 0, dy: 0, w: 45, h: 115, id: 'STF_081', color: '#8b5cf6', tag: 'Cashier' }
    ],
    CAM_FLOOR_02: [
        { x: 180, y: 140, dx: -0.8, dy: 0.3, w: 48, h: 110, id: 'VIS_c910', color: '#ff6b35', tag: 'Visitor' },
        { x: 350, y: 170, dx: 1.2, dy: -0.4, w: 44, h: 105, id: 'VIS_d112', color: '#ff6b35', tag: 'Visitor' }
    ],
    CAM_ENTRY_02: [
        { x: 150, y: 130, dx: 1.0, dy: 0.2, w: 42, h: 105, id: 'VIS_e042', color: '#ff6b35', tag: 'Visitor' }
    ]
};

let currentFramePeople = JSON.parse(JSON.stringify(mockPeople.CAM_ENTRY_01));

function drawCCTVFrame() {
    // Clear canvas
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw a simulated store floor grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    for (let i = 0; i < canvas.width; i += 40) {
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i, canvas.height);
        ctx.stroke();
    }
    for (let j = 0; j < canvas.height; j += 40) {
        ctx.beginPath();
        ctx.moveTo(0, j);
        ctx.lineTo(canvas.width, j);
        ctx.stroke();
    }

    // Draw simulated camera static scanlines
    ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
    for (let y = 0; y < canvas.height; y += 4) {
        ctx.fillRect(0, y, canvas.width, 2);
    }

    // Draw camera details text
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px Outfit';
    ctx.fillText(`REC: ${new Date().toISOString()}`, 15, canvas.height - 15);

    // Draw custom static zones polygons
    ctx.strokeStyle = 'rgba(255, 107, 53, 0.2)';
    ctx.lineWidth = 2;
    if (currentCamera === 'CAM_ENTRY_01' || currentCamera === 'CAM_ENTRY_02') {
        // Draw entry/exit line
        ctx.beginPath();
        ctx.moveTo(0, 130);
        ctx.lineTo(canvas.width, 130);
        ctx.stroke();
        ctx.fillStyle = 'rgba(255, 107, 53, 0.08)';
        ctx.fillText('ENTRY THRESHOLD LINE', 15, 120);
    } else if (currentCamera === 'CAM_BILLING_01') {
        // Draw Billing area polygon
        ctx.fillStyle = 'rgba(255, 107, 53, 0.05)';
        ctx.fillRect(100, 100, 220, 200);
        ctx.strokeRect(100, 100, 220, 200);
        ctx.fillStyle = 'rgba(255, 107, 53, 0.5)';
        ctx.fillText('BILLING QUEUE ZONE', 110, 120);
    }

    // Update and draw simulated people bounding boxes
    activeDetectionsCount = 0;
    currentFramePeople.forEach(person => {
        // Move person
        person.x += person.dx;
        person.y += person.dy;

        // Bounce back
        if (person.x < 50 || person.x > canvas.width - 90) person.dx *= -1;
        if (person.y < 80 || person.y > canvas.height - 130) person.dy *= -1;

        // Draw bounding box
        ctx.strokeStyle = person.color;
        ctx.lineWidth = 2;
        ctx.strokeRect(person.x, person.y, person.w, person.h);

        // Draw box glow shadow
        ctx.shadowColor = person.color;
        ctx.shadowBlur = 8;
        ctx.strokeRect(person.x, person.y, person.w, person.h);
        ctx.shadowBlur = 0; // reset

        // Draw badge top label
        ctx.fillStyle = person.color;
        ctx.fillRect(person.x, person.y - 18, person.w + 10, 18);

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px Outfit';
        ctx.fillText(`${person.tag} [${person.id}]`, person.x + 4, person.y - 6);

        activeDetectionsCount++;
    });

    // Update active UI Tag
    const tag = document.getElementById('ai-detection-tag');
    if (activeDetectionsCount > 0) {
        tag.classList.add('active');
        const visitorCount = currentFramePeople.filter(p => p.tag.includes('Visitor') || p.tag.includes('Queue')).length;
        tag.innerHTML = `<i data-lucide="users"></i> Tracking: ${visitorCount} Visitors`;
    } else {
        tag.classList.remove('active');
    }

    requestAnimationFrame(drawCCTVFrame);
}

// Fetch metrics, funnel, anomalies and health from FastAPI API
async function updateMetrics() {
    try {
        // Fetch Metrics
        const metricsRes = await fetch(`${API_BASE}/stores/${STORE_ID}/metrics`);
        if (metricsRes.ok) {
            const data = await metricsRes.json();
            
            document.getElementById('val-visitors').innerText = data.unique_visitors || 0;
            document.getElementById('val-conversion').innerText = `${((data.conversion_rate || 0) * 100).toFixed(1)}%`;
            document.getElementById('val-queue').innerText = data.queue_depth || 0;
            document.getElementById('val-abandonment').innerText = `${((data.abandonment_rate || 0) * 100).toFixed(1)}%`;
            
            // Queue depth status styling
            const qPill = document.getElementById('val-queue-status');
            const qIconBg = document.getElementById('queue-icon-bg');
            const qIcon = document.getElementById('queue-icon');
            if (data.queue_depth > 3) {
                qPill.className = "metric-trend down";
                qPill.innerText = "Queue Spike!";
                qIconBg.className = "metric-icon-bg red-light";
                qIcon.className = "red-text";
            } else {
                qPill.className = "metric-trend up";
                qPill.innerText = "Normal";
                qIconBg.className = "metric-icon-bg orange-light";
                qIcon.className = "orange-text";
            }

            // Update Chart.js trends metrics dynamically if needed
            if (trendsChart) {
                const length = trendsChart.data.datasets[0].data.length;
                trendsChart.data.datasets[0].data[length - 1] = data.unique_visitors || 0;
                trendsChart.update();
            }
        }

        // Fetch Funnel
        const funnelRes = await fetch(`${API_BASE}/stores/${STORE_ID}/funnel`);
        if (funnelRes.ok) {
            const data = await funnelRes.json();
            const stages = data.funnel || [];
            
            stages.forEach(stage => {
                let elementId = '';
                if (stage.stage === 'entry') elementId = 'stage-entry';
                else if (stage.stage === 'zone_visit') elementId = 'stage-zone';
                else if (stage.stage === 'billing_queue') elementId = 'stage-queue';
                else if (stage.stage === 'purchase') elementId = 'stage-purchase';

                if (elementId) {
                    const row = document.getElementById(elementId);
                    row.querySelector('.stage-count').innerText = `${stage.sessions} ${stage.stage === 'purchase' ? 'purchases' : 'visitors'}`;
                    
                    // Update progress bar width percentage
                    let widthPct = 100;
                    if (stage.stage === 'zone_visit' && stages[0].sessions > 0) {
                        widthPct = (stage.sessions / stages[0].sessions) * 100;
                    } else if (stage.stage === 'billing_queue' && stages[0].sessions > 0) {
                        widthPct = (stage.sessions / stages[0].sessions) * 100;
                    } else if (stage.stage === 'purchase' && stages[0].sessions > 0) {
                        widthPct = (stage.sessions / stages[0].sessions) * 100;
                    }
                    row.querySelector('.stage-bar-inner').style.width = `${widthPct.toFixed(0)}%`;
                    row.querySelector('.stage-drop').innerText = stage.stage === 'entry' ? '100% baseline' : `-${stage.drop_off_pct}% drop-off`;
                }
            });
        }

        // Fetch Health
        const healthRes = await fetch(`${API_BASE}/health`);
        if (healthRes.ok) {
            const data = await healthRes.json();
            const isDbConnected = data.database?.status === 'connected';
            const dbBadge = document.getElementById('db-status-badge');
            const dbBar = document.getElementById('db-health-bar');
            const dbPct = document.getElementById('db-health-pct');

            if (isDbConnected) {
                dbBadge.innerText = "Connected";
                dbBadge.className = "badge-status online";
                dbBar.className = "progress-bar green-bar";
                dbBar.style.width = "100%";
                dbPct.innerText = "100%";
            } else {
                dbBadge.innerText = "Error";
                dbBadge.className = "badge-status badge-danger";
                dbBar.className = "progress-bar red-bar";
                dbBar.style.width = "0%";
                dbPct.innerText = "0%";
            }
        }

        // Fetch Anomalies
        const anomaliesRes = await fetch(`${API_BASE}/stores/${STORE_ID}/anomalies`);
        if (anomaliesRes.ok) {
            const anomalies = await anomaliesRes.json();
            const list = document.getElementById('anomalies-list');
            const badgeBadge = document.getElementById('anomaly-badge');
            const badgeCountBadge = document.getElementById('anomaly-count-badge');

            if (anomalies && anomalies.length > 0) {
                badgeBadge.innerText = anomalies.length;
                badgeBadge.classList.add('active');
                badgeCountBadge.innerText = `${anomalies.length} Active`;
                badgeCountBadge.className = "badge danger-badge";
                
                list.innerHTML = anomalies.map(anom => {
                    let sevClass = 'info';
                    if (anom.severity === 'CRITICAL') sevClass = 'danger';
                    else if (anom.severity === 'WARN') sevClass = 'warning';

                    return `
                        <div class="anomaly-item">
                            <div class="anomaly-icon ${sevClass}">
                                <i data-lucide="alert-triangle"></i>
                            </div>
                            <div class="anomaly-details">
                                <h4>${anom.anomaly_type.replace(/_/g, ' ')}</h4>
                                <p>${anom.description}</p>
                                <span class="anomaly-action"><i data-lucide="arrow-right-circle" style="width:10px;height:10px;display:inline-block;vertical-align:middle;margin-right:2px"></i>Action: ${anom.suggested_action}</span>
                            </div>
                        </div>
                    `;
                }).join('');
                lucide.createIcons();
            } else {
                badgeBadge.innerText = "0";
                badgeBadge.classList.remove('active');
                badgeCountBadge.innerText = "0 Active";
                badgeCountBadge.className = "badge warning-badge";
                list.innerHTML = `
                    <div class="no-anomalies">
                        <i data-lucide="shield-check" class="green-text"></i>
                        <p>System operational. No active anomalies detected.</p>
                    </div>
                `;
                lucide.createIcons();
            }
        }

    } catch (e) {
        console.error("Failed to fetch API analytics:", e);
    }
}

// Camera tab event listeners
document.querySelectorAll('.cam-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        document.querySelectorAll('.cam-tab').forEach(t => t.classList.remove('active'));
        e.target.classList.add('active');
        
        currentCamera = e.target.getAttribute('data-cam');
        currentFramePeople = JSON.parse(JSON.stringify(mockPeople[currentCamera]));
        
        const titleEl = document.getElementById('current-camera-title');
        if (currentCamera === 'CAM_ENTRY_01') titleEl.innerText = "CCTV 01 - Main Entry 1";
        else if (currentCamera === 'CAM_FLOOR_01') titleEl.innerText = "CCTV 02 - Main Floor 1";
        else if (currentCamera === 'CAM_BILLING_01') titleEl.innerText = "CCTV 03 - Cash Counter";
        else if (currentCamera === 'CAM_FLOOR_02') titleEl.innerText = "CCTV 04 - Main Floor 2";
        else if (currentCamera === 'CAM_ENTRY_02') titleEl.innerText = "CCTV 05 - Side Entry 2";
    });
});

// Setup on window load
window.addEventListener('load', () => {
    initChart();
    drawCCTVFrame();
    updateMetrics();
    renderMinimap();

    // Poll data every 5 seconds
    setInterval(updateMetrics, 5000);
    setInterval(renderMinimap, 5000);
});

// ── Store Floor Plan Minimap ──────────────────────────────────────────────────
//
// Heatmap data from /stores/ST1008/heatmap is mapped onto the SVG floor plan.
// Each zone polygon gets a heat-* CSS class based on normalised visit_freq (0-100).
// Live visitor blips are placed using the current CCTV camera's mock person positions,
// scaled from the 640×360 canvas space into the 640×320 SVG minimap space.
//
// Zone ID → SVG element ID mapping (matches store_layout.json v2):
//   FOH, TOP_AISLE, BOTTOM_AISLE, FRAGRANCE, MAKEUP, CASH_COUNTER, BOH

// Approximate zone center positions in SVG viewBox (640×320) for blip placement
const ZONE_CENTERS = {
    FOH:           { x: 95,  y: 160 },
    TOP_AISLE:     { x: 362, y: 44  },
    FRAGRANCE:     { x: 209, y: 124 },
    MAKEUP:        { x: 357, y: 124 },
    BOTTOM_AISLE:  { x: 362, y: 203 },
    CASH_COUNTER:  { x: 587, y: 138 },
    BOH:           { x: 587, y: 28  },
};

// Minimap heatmap zone data cache (updated from API)
let minimapZoneData = {};

async function renderMinimap() {
    try {
        const res = await fetch(`${API_BASE}/stores/${STORE_ID}/heatmap`);
        if (!res.ok) return;

        const data = await res.json();
        minimapZoneData = {};

        // Update confidence badge
        const confBadge = document.getElementById('minimap-confidence-badge');
        if (confBadge) {
            confBadge.textContent = data.data_confidence === 'HIGH' ? 'HIGH confidence' : 'LOW confidence';
            confBadge.style.background = data.data_confidence === 'HIGH'
                ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)';
            confBadge.style.color = data.data_confidence === 'HIGH' ? '#10b981' : '#f59e0b';
        }

        // Apply heat levels to SVG zone polygons
        (data.zones || []).forEach(zone => {
            minimapZoneData[zone.zone_id] = zone;
            const el = document.getElementById(`zone-${zone.zone_id}`);
            if (!el) return;

            // Remove existing heat classes
            el.classList.remove('heat-cold', 'heat-low', 'heat-mid', 'heat-high', 'heat-peak');

            // Classify heat level from normalised visit_freq (0-100)
            const freq = zone.visit_freq;
            if (freq === 0)       el.classList.add('heat-cold');
            else if (freq < 20)   el.classList.add('heat-low');
            else if (freq < 50)   el.classList.add('heat-mid');
            else if (freq < 80)   el.classList.add('heat-high');
            else                  el.classList.add('heat-peak');
        });

        // Place visitor blips from current CCTV camera mock persons
        _updateMinimapBlips();

    } catch (e) {
        console.warn('Minimap fetch failed:', e);
    }
}

function _updateMinimapBlips() {
    const blipLayer = document.getElementById('visitor-blips-layer');
    if (!blipLayer) return;
    blipLayer.innerHTML = '';

    // Map camera → zone blip positions
    // Each person from mockPeople is placed near their camera's zone center on the minimap.
    // We jitter slightly so multiple blips don't stack.
    const camZoneMap = {
        CAM_ENTRY_01:  'FOH',
        CAM_ENTRY_02:  'FOH',
        CAM_FLOOR_01:  'TOP_AISLE',
        CAM_FLOOR_02:  'BOTTOM_AISLE',
        CAM_BILLING_01:'CASH_COUNTER',
    };

    let totalBlips = 0;
    const svgNS = 'http://www.w3.org/2000/svg';

    // Show blips for all cameras, with alpha fade for non-active cameras
    Object.entries(mockPeople).forEach(([camId, people]) => {
        const zoneId = camZoneMap[camId];
        const center = ZONE_CENTERS[zoneId];
        if (!center) return;

        const isActive = camId === currentCamera;
        const baseOpacity = isActive ? 1.0 : 0.25;

        people.forEach((person, idx) => {
            const isStaff = person.tag === 'Staff' || person.tag === 'Cashier';
            const jitter = { x: (idx - 0.5) * 18, y: (idx % 2 === 0 ? -1 : 1) * 10 };
            const bx = Math.max(8, Math.min(632, center.x + jitter.x));
            const by = Math.max(8, Math.min(312, center.y + jitter.y));

            // Ripple ring
            const ripple = document.createElementNS(svgNS, 'circle');
            ripple.setAttribute('cx', bx);
            ripple.setAttribute('cy', by);
            ripple.setAttribute('r', 3);
            ripple.classList.add('visitor-blip-ripple');
            ripple.style.opacity = baseOpacity;
            ripple.style.animationDelay = `${idx * 0.3}s`;
            blipLayer.appendChild(ripple);

            // Core dot
            const blip = document.createElementNS(svgNS, 'circle');
            blip.setAttribute('cx', bx);
            blip.setAttribute('cy', by);
            blip.setAttribute('r', 3);
            blip.classList.add('visitor-blip');
            if (isStaff) blip.classList.add('staff-blip');
            blip.style.opacity = baseOpacity;
            blip.style.animationDelay = `${idx * 0.2}s`;
            blipLayer.appendChild(blip);

            totalBlips++;
        });
    });

    const blipCount = document.getElementById('minimap-blip-count');
    if (blipCount) blipCount.textContent = `${totalBlips} tracked`;
}

// Zone hover tooltip on SVG floor zones
(function setupMinimapTooltip() {
    const tooltip = document.getElementById('zone-tooltip');
    if (!tooltip) return;

    document.querySelectorAll('.floor-zone').forEach(el => {
        el.addEventListener('mouseenter', (e) => {
            const zoneId   = el.getAttribute('data-zone');
            const label    = el.getAttribute('data-label');
            const isBill   = el.getAttribute('data-billing') === 'true';
            const zoneData = minimapZoneData[zoneId];

            document.getElementById('zt-name').textContent = label || zoneId;
            document.getElementById('zt-traffic').textContent = zoneData
                ? `${zoneData.visit_freq.toFixed(0)} / 100` : '– (no data)';
            document.getElementById('zt-dwell').textContent = zoneData
                ? `${(zoneData.avg_dwell_ms / 1000).toFixed(1)}s` : '–';

            if (isBill) {
                document.getElementById('zt-name').style.color = '#ff6b35';
            } else {
                document.getElementById('zt-name').style.color = '#ff6b35';
            }

            // Position tooltip near the cursor but within the wrapper
            const wrapper = el.closest('.floor-plan-wrapper');
            const rect = wrapper.getBoundingClientRect();
            const svgRect = document.getElementById('store-floor-plan').getBoundingClientRect();

            tooltip.style.left = Math.min(e.clientX - rect.left + 10, rect.width - 145) + 'px';
            tooltip.style.top  = Math.max(e.clientY - rect.top - 70, 4) + 'px';
            tooltip.classList.add('visible');
        });

        el.addEventListener('mouseleave', () => {
            tooltip.classList.remove('visible');
        });
    });
})();

