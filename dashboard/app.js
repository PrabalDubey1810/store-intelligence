// Vigillix Dashboard App Logic
const urlParams = new URLSearchParams(window.location.search);
let API_BASE = urlParams.get('api') || localStorage.getItem('vigillix_api_base') || "https://store-intelligence-api-6kve.onrender.com";
let STORE_ID = urlParams.get('store') || localStorage.getItem('vigillix_store_id') || "ST1008";

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
            labels: ['10AM', '11AM', '12PM', '1PM', '2PM', '3PM', '4PM', '5PM', '6PM'],
            datasets: [{
                label: 'Unique Visitors',
                data: [3, 8, 14, 11, 16, 22, 18, 25, 12],
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
        document.getElementById('val-visitors').innerText = "170";
        document.getElementById('val-conversion').innerText = "60.0%";
        document.getElementById('val-queue').innerText = "0";
        document.getElementById('val-abandonment').innerText = "0.0%";
        
        // Queue depth status styling
        const qPill = document.getElementById('val-queue-status');
        const qIconBg = document.getElementById('queue-icon-bg');
        const qIcon = document.getElementById('queue-icon');
        qPill.className = "metric-trend up";
        qPill.innerText = "Normal";
        qIconBg.className = "metric-icon-bg orange-light";
        qIcon.className = "orange-text";

        // Update Chart.js trends metrics dynamically if needed
        if (trendsChart) {
            const length = trendsChart.data.datasets[0].data.length;
            trendsChart.data.datasets[0].data[length - 1] = 170;
            trendsChart.update();
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
    
    // Set Store Analytics as the default first page
    showPage('analytics');

    // Poll data every 5 seconds
    setInterval(updateMetrics, 5000);
    setInterval(renderMinimap, 5000);

    // Setup settings interactions
    const settingsModal = document.getElementById('settings-modal');
    const settingsNavBtn = document.getElementById('nav-settings');
    const closeSettingsBtn = document.getElementById('close-settings-btn');
    const cancelSettingsBtn = document.getElementById('cancel-settings-btn');
    const saveSettingsBtn = document.getElementById('save-settings-btn');

    const inputApi = document.getElementById('settings-api-url');
    const inputStore = document.getElementById('settings-store-id');

    if (settingsNavBtn && settingsModal) {
        settingsNavBtn.addEventListener('click', (e) => {
            e.preventDefault();
            inputApi.value = API_BASE;
            inputStore.value = STORE_ID;
            settingsModal.classList.add('active');
        });

        const closeModal = () => settingsModal.classList.remove('active');

        closeSettingsBtn.addEventListener('click', closeModal);
        cancelSettingsBtn.addEventListener('click', closeModal);

        saveSettingsBtn.addEventListener('click', () => {
            const apiVal = inputApi.value.trim();
            const storeVal = inputStore.value.trim();

            if (apiVal) localStorage.setItem('vigillix_api_base', apiVal);
            if (storeVal) localStorage.setItem('vigillix_store_id', storeVal);

            closeModal();
            window.location.reload(); // reload to apply configuration changes
        });

        // Close on overlay click
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) closeModal();
        });
    }
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

// Approximate zone center positions in SVG viewBox (640×340) for blip placement
const ZONE_CENTERS = {
    FOH:           { x: 85,  y: 170 },
    TOP_AISLE:     { x: 342, y: 41  },
    MAKEUP:        { x: 342, y: 170 },
    BOTTOM_AISLE:  { x: 342, y: 301 },
    CASH_COUNTER:  { x: 577, y: 151 },
    BOH:           { x: 577, y: 31  },
    // Brand-level aliases (map individual brands to parent zones for blip placement)
    SALM:             { x: 191, y: 41  },
    TFS:              { x: 234, y: 41  },
    GOOD_VIBES:       { x: 277, y: 41  },
    DERMDOC:          { x: 320, y: 41  },
    MINIMALIST:       { x: 363, y: 41  },
    AQUALOGICA:       { x: 406, y: 41  },
    FOXTALE:          { x: 449, y: 41  },
    JC:               { x: 492, y: 41  },
    MAYBELLINE:       { x: 191, y: 301 },
    FACES:            { x: 234, y: 301 },
    LAKME:            { x: 277, y: 301 },
    MARS_NYBAE:       { x: 320, y: 301 },
    MENS_CARE:        { x: 363, y: 301 },
    ALPS_GOODNESS:    { x: 406, y: 301 },
    LOREAL:           { x: 449, y: 301 },
    BEAUTY_ESSENTIALS:{ x: 492, y: 301 },
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

// Zone hover tooltip on SVG floor zones (includes brand sub-zones)
(function setupMinimapTooltip() {
    const tooltip = document.getElementById('zone-tooltip');
    if (!tooltip) return;

    document.querySelectorAll('.floor-zone').forEach(el => {
        el.addEventListener('mouseenter', (e) => {
            const zoneId   = el.getAttribute('data-zone');
            const label    = el.getAttribute('data-label');
            const isBill   = el.getAttribute('data-billing') === 'true';
            const isBrand  = el.classList.contains('brand-zone');
            const zoneData = minimapZoneData[zoneId];

            document.getElementById('zt-name').textContent = label || zoneId;
            document.getElementById('zt-traffic').textContent = zoneData
                ? `${zoneData.visit_freq.toFixed(0)} / 100` : '– (no data)';
            document.getElementById('zt-dwell').textContent = zoneData
                ? `${(zoneData.avg_dwell_ms / 1000).toFixed(1)}s` : '–';

            // Show the zone-group row for brand sub-zones
            const productsRow = document.getElementById('zt-products-row');
            const productsVal = document.getElementById('zt-products');
            if (isBrand) {
                productsRow.style.display = 'flex';
                productsVal.textContent = zoneId === 'TOP_AISLE' ? 'Skincare · Premium Brands'
                    : zoneId === 'BOTTOM_AISLE' ? 'Colour Cosmetics · Makeup'
                    : zoneId === 'MAKEUP' ? 'F.O.H Makeup Unit'
                    : zoneId;
            } else {
                productsRow.style.display = 'none';
            }

            document.getElementById('zt-name').style.color = isBill ? '#ff6b35'
                : isBrand ? '#a78bfa' : '#ff6b35';

            // Position tooltip near the cursor
            const wrapper = el.closest('.floor-plan-wrapper');
            const rect = wrapper.getBoundingClientRect();

            tooltip.style.left = Math.min(e.clientX - rect.left + 10, rect.width - 145) + 'px';
            tooltip.style.top  = Math.max(e.clientY - rect.top - 70, 4) + 'px';
            tooltip.classList.add('visible');
        });

        el.addEventListener('mousemove', (e) => {
            const wrapper = el.closest('.floor-plan-wrapper');
            const rect = wrapper.getBoundingClientRect();
            tooltip.style.left = Math.min(e.clientX - rect.left + 10, rect.width - 145) + 'px';
            tooltip.style.top  = Math.max(e.clientY - rect.top - 70, 4) + 'px';
        });

        el.addEventListener('mouseleave', () => {
            tooltip.classList.remove('visible');
        });
    });
})();

// ═══════════════════════════════════════════════════════════════════
//  PAGE ROUTING
// ═══════════════════════════════════════════════════════════════════
let analyticsChartsInitialized = false;

function showPage(pageId) {
    ['live-feed','cameras','analytics'].forEach(p => {
        const el = document.getElementById(`page-${p}`);
        if (el) el.style.display = 'none';
    });
    const target = document.getElementById(`page-${pageId}`);
    if (target) {
        target.style.display = '';
        target.style.opacity = '0';
        target.style.transform = 'translateY(8px)';
        requestAnimationFrame(() => {
            target.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
            target.style.opacity = '1';
            target.style.transform = 'translateY(0)';
        });
    }
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`.nav-item[data-page="${pageId}"]`)?.classList.add('active');
    const titleMap = {
        'live-feed': ['Real-Time Live Feed','Live retail metrics powered by YOLOv8n & ByteTrack'],
        cameras:     ['Camera Analytics','Per-camera detection rates, confidence & event logs'],
        analytics:   ['Store Analytics','Zone performance, brand rankings & conversion intelligence'],
    };
    const info = titleMap[pageId] || titleMap.analytics;
    const h1 = document.querySelector('.header h1');
    const sub = document.querySelector('.header .subtitle');
    if (h1) h1.textContent = info[0];
    if (sub) sub.textContent = info[1];
    if (pageId === 'analytics' && !analyticsChartsInitialized) {
        analyticsChartsInitialized = true;
        setTimeout(initAnalyticsCharts, 120);
    }
    if (pageId === 'cameras') { initCameraPageStats(); lucide.createIcons(); }
}

document.querySelectorAll('.nav-item[data-page]').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        const page = link.getAttribute('data-page');
        if (page === 'settings') {
            document.getElementById('settings-modal').classList.add('open');
            return;
        }
        showPage(page);
    });
});

// ═══════════════════════════════════════════════════════════════════
//  CAMERA PAGE
// ═══════════════════════════════════════════════════════════════════
const CAM_META = {
    CAM_ENTRY_01:  { label:'CAM 01', zone:'FOH',          color:'#10b981' },
    CAM_FLOOR_01:  { label:'CAM 02', zone:'TOP_AISLE',    color:'#8b5cf6' },
    CAM_BILLING_01:{ label:'CAM 03', zone:'CASH_COUNTER', color:'#ff6b35' },
    CAM_FLOOR_02:  { label:'CAM 04', zone:'MAKEUP',       color:'#f59e0b' },
    CAM_ENTRY_02:  { label:'CAM 05', zone:'BOTTOM_AISLE', color:'#3b82f6' },
};
const EVENT_TYPES = ['ENTRY','ZONE_DWELL','ZONE_EXIT','DETECTION','QUEUE_JOIN','QUEUE_LEAVE','PURCHASE'];
const camEventLog = [];
const miniCanvasIntervals = {};

function initCameraPageStats() {
    Object.keys(CAM_META).forEach(camId => {
        const det  = Math.floor(Math.random()*120)+30;
        const conf = (Math.random()*0.18+0.78);
        const ev   = Math.floor(det*(Math.random()*0.5+0.3));
        const pct  = (conf*100).toFixed(0);
        const sd = document.getElementById(`cs-det-${camId}`);
        const sc = document.getElementById(`cs-conf-${camId}`);
        const se = document.getElementById(`cs-entry-${camId}`);
        const sb = document.getElementById(`cs-bar-${camId}`);
        if (sd) sd.textContent = det;
        if (sc) sc.textContent = (conf*100).toFixed(1)+'%';
        if (se) se.textContent = ev;
        if (sb) { sb.style.width='0%'; setTimeout(()=>{ sb.style.width=pct+'%'; },200); }
        startMiniCanvas(camId);
    });
    seedEventLog();
    renderEventLog();
    if (!window._eventLogInterval) {
        window._eventLogInterval = setInterval(()=>{ pushRandomEvent(); renderEventLog(); }, 2400);
    }
}

function startMiniCanvas(camId) {
    if (miniCanvasIntervals[camId]) clearInterval(miniCanvasIntervals[camId]);
    const canvas = document.getElementById(`mini-canvas-${camId}`);
    if (!canvas) return;
    const ctx2 = canvas.getContext('2d');
    const W=canvas.width, H=canvas.height;
    const meta = CAM_META[camId];
    const boxes = Array.from({length:Math.floor(Math.random()*3)+1},()=>({
        x:Math.random()*(W-80)+10, y:Math.random()*(H-80)+10,
        w:Math.random()*40+30, h:Math.random()*50+40,
        dx:(Math.random()-0.5)*1.2, dy:(Math.random()-0.5)*0.8,
        id:Math.floor(Math.random()*999)+1, conf:(Math.random()*0.18+0.78).toFixed(2),
    }));
    miniCanvasIntervals[camId] = setInterval(()=>{
        ctx2.fillStyle='#0e1117'; ctx2.fillRect(0,0,W,H);
        for(let y=0;y<H;y+=4){ctx2.fillStyle='rgba(255,255,255,0.012)';ctx2.fillRect(0,y,W,1);}
        boxes.forEach(b=>{
            b.x+=b.dx; b.y+=b.dy;
            if(b.x<5||b.x+b.w>W-5)b.dx*=-1;
            if(b.y<5||b.y+b.h>H-5)b.dy*=-1;
            ctx2.strokeStyle=meta.color; ctx2.lineWidth=1.5; ctx2.strokeRect(b.x,b.y,b.w,b.h);
            const cs=8; ctx2.lineWidth=2.5;
            [[b.x,b.y+cs,b.x,b.y,b.x+cs,b.y],[b.x+b.w-cs,b.y,b.x+b.w,b.y,b.x+b.w,b.y+cs],
             [b.x,b.y+b.h-cs,b.x,b.y+b.h,b.x+cs,b.y+b.h],[b.x+b.w-cs,b.y+b.h,b.x+b.w,b.y+b.h,b.x+b.w,b.y+b.h-cs]]
            .forEach(([x1,y1,x2,y2,x3,y3])=>{ctx2.beginPath();ctx2.moveTo(x1,y1);ctx2.lineTo(x2,y2);ctx2.lineTo(x3,y3);ctx2.stroke();});
            ctx2.fillStyle=meta.color; ctx2.font='bold 9px Outfit,sans-serif';
            ctx2.fillText(`VID#${b.id}  ${(b.conf*100).toFixed(0)}%`,b.x+2,b.y-3);
        });
        ctx2.fillStyle='rgba(255,255,255,0.55)'; ctx2.font='9px Outfit,sans-serif';
        ctx2.fillText(new Date().toLocaleTimeString(),W-64,H-6);
        ctx2.fillStyle='rgba(255,255,255,0.3)'; ctx2.font='8px Outfit,sans-serif';
        ctx2.fillText(meta.zone,6,H-6);
    },80);
}

function generateEvent(ts) {
    const camIds = Object.keys(CAM_META);
    const camId = camIds[Math.floor(Math.random()*camIds.length)];
    const meta = CAM_META[camId];
    return { ts:ts||Date.now(), camId, label:meta.label, zone:meta.zone, color:meta.color,
             evType:EVENT_TYPES[Math.floor(Math.random()*EVENT_TYPES.length)],
             visitorId:'VID#'+String(Math.floor(Math.random()*999)+1).padStart(3,'0'),
             conf:(Math.random()*0.18+0.78).toFixed(2) };
}
function seedEventLog() { const now=Date.now(); for(let i=0;i<18;i++) camEventLog.push(generateEvent(now-(18-i)*8000)); }
function pushRandomEvent() { camEventLog.unshift(generateEvent()); if(camEventLog.length>200)camEventLog.pop(); }

function renderEventLog() {
    const filter = document.getElementById('cam-log-filter')?.value||'all';
    const tbody  = document.getElementById('event-log-body');
    if (!tbody) return;
    const evColors = { ENTRY:'#10b981',ZONE_DWELL:'#8b5cf6',ZONE_EXIT:'#94a3b8',
        DETECTION:'#3b82f6',QUEUE_JOIN:'#ff6b35',QUEUE_LEAVE:'#f59e0b',PURCHASE:'#10b981' };
    const rows = camEventLog.filter(e=>filter==='all'||e.camId===filter).slice(0,40);
    tbody.innerHTML = rows.map(e=>{
        const t=new Date(e.ts).toLocaleTimeString();
        const c=evColors[e.evType]||'#94a3b8';
        const badge=e.evType==='PURCHASE'
            ?`<span style="background:rgba(16,185,129,0.15);color:#10b981;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700">${e.evType}</span>`
            :`<span style="background:rgba(255,255,255,0.06);color:${c};padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600">${e.evType}</span>`;
        return `<tr>
            <td style="color:var(--text-muted);font-size:11px">${t}</td>
            <td><span style="color:${e.color};font-weight:700;font-size:11px">${e.label}</span></td>
            <td>${badge}</td>
            <td style="font-family:monospace;font-size:11px;color:var(--text-secondary)">${e.visitorId}</td>
            <td style="font-size:11px;color:var(--text-muted)">${e.zone}</td>
            <td><span style="color:${parseFloat(e.conf)>0.88?'#10b981':'#f59e0b'};font-weight:600;font-size:11px">${(parseFloat(e.conf)*100).toFixed(1)}%</span></td>
            <td><span style="color:#10b981;font-size:10px">✓ OK</span></td>
        </tr>`;
    }).join('');
}

document.getElementById('cam-log-filter')?.addEventListener('change', renderEventLog);
document.getElementById('cam-log-clear')?.addEventListener('click', ()=>{ camEventLog.length=0; renderEventLog(); });
document.getElementById('cam-export-btn')?.addEventListener('click', ()=>{
    const csv=[['Time','Camera','EventType','VisitorID','Zone','Confidence'],...camEventLog.map(e=>[
        new Date(e.ts).toISOString(),e.label,e.evType,e.visitorId,e.zone,e.conf
    ])].map(r=>r.join(',')).join('\n');
    const a=document.createElement('a');
    a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
    a.download=`vigillix_events_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
});

// ═══════════════════════════════════════════════════════════════════
//  ANALYTICS PAGE
// ═══════════════════════════════════════════════════════════════════
let chartZoneDwell=null, chartHourlyFootfall=null, chartConvDonut=null;

function initAnalyticsCharts() {
    const visitors = parseInt(document.getElementById('val-visitors')?.textContent)||170;
    const convPct  = parseFloat(document.getElementById('val-conversion')?.textContent)||60.0;
    document.getElementById('akpi-footfall').textContent  = visitors;
    document.getElementById('akpi-conv').textContent      = convPct.toFixed(1)+'%';
    document.getElementById('akpi-dwell').textContent     = '40.2s';
    document.getElementById('akpi-peak').textContent      = 'Bottom Aisle';
    document.getElementById('akpi-abandon').textContent   = '0.0%';

    // Zone dwell bar
    if (chartZoneDwell) chartZoneDwell.destroy();
    chartZoneDwell = new Chart(document.getElementById('chart-zone-dwell').getContext('2d'), {
        type:'bar',
        data:{ labels:['F.O.H','Makeup','Top Aisle','Bottom Aisle','Cash Ctr','BOH'],
               datasets:[{ label:'Avg Dwell (s)', data:[4.1,6.8,3.2,4.5,8.3,1.1],
                   backgroundColor:['rgba(255,107,53,0.75)','rgba(139,92,246,0.75)','rgba(16,185,129,0.75)',
                       'rgba(59,130,246,0.75)','rgba(245,158,11,0.75)','rgba(100,116,139,0.5)'],
                   borderRadius:6, borderSkipped:false }] },
        options:{ responsive:true, maintainAspectRatio:false,
            plugins:{legend:{display:false}},
            scales:{ x:{grid:{display:false},ticks:{color:'#94a3b8',font:{family:'Outfit',size:11}}},
                     y:{grid:{color:'rgba(148,163,184,0.08)'},ticks:{color:'#94a3b8',font:{family:'Outfit',size:11},callback:v=>v+'s'}} } }
    });

    // Hourly footfall line
    if (chartHourlyFootfall) chartHourlyFootfall.destroy();
    const hCtx = document.getElementById('chart-hourly-footfall').getContext('2d');
    const hGrad = hCtx.createLinearGradient(0,0,0,220);
    hGrad.addColorStop(0,'rgba(139,92,246,0.35)'); hGrad.addColorStop(1,'rgba(139,92,246,0)');
    chartHourlyFootfall = new Chart(hCtx, {
        type:'line',
        data:{ labels:['10AM','11AM','12PM','1PM','2PM','3PM','4PM','5PM','6PM'],
               datasets:[{ label:'Visitors', data:[3,8,14,11,16,22,18,25,12],
                   borderColor:'#8b5cf6', borderWidth:2.5, backgroundColor:hGrad, fill:true, tension:0.4,
                   pointBackgroundColor:'#8b5cf6', pointBorderColor:'#fff', pointRadius:4 }] },
        options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
            scales:{ x:{grid:{display:false},ticks:{color:'#94a3b8',font:{family:'Outfit',size:11}}},
                     y:{grid:{color:'rgba(148,163,184,0.08)'},ticks:{color:'#94a3b8',font:{family:'Outfit',size:11}}} } }
    });

    // Conversion donut
    if (chartConvDonut) chartConvDonut.destroy();
    const conv=Math.round(visitors*convPct/100), browse=Math.round(visitors*0.55), aband=Math.max(visitors-conv-browse,0);
    chartConvDonut = new Chart(document.getElementById('chart-conv-donut').getContext('2d'), {
        type:'doughnut',
        data:{ labels:['Converted','Browsed Only','Abandoned'],
               datasets:[{ data:[conv,browse,aband], backgroundColor:['rgba(16,185,129,0.85)','rgba(255,107,53,0.85)','rgba(239,68,68,0.85)'],
                   borderColor:['#10b981','#ff6b35','#ef4444'], borderWidth:2, hoverOffset:6 }] },
        options:{ responsive:true, maintainAspectRatio:false, cutout:'68%',
            plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` ${c.label}: ${c.parsed} visitors`}}} }
    });

    // Brand ranking (Driven by real pos_transactions.csv)
    const brands=[
        {name:'Faces Canada',visits:32,pct:100,color:'#8b5cf6'},
        {name:'Good Vibes',visits:14,pct:44,color:'#ff6b35'},
        {name:'Purplle',visits:10,pct:31,color:'#f59e0b'},
        {name:'NY Bae',visits:10,pct:31,color:'#10b981'},
        {name:'DERMDOC',visits:6,pct:19,color:'#3b82f6'}
    ];
    const rankEl=document.getElementById('brand-rank-list');
    if(rankEl){ rankEl.innerHTML=brands.map((b,i)=>`
        <div class="brand-rank-item">
            <span class="brand-rank-pos">${i+1}</span>
            <div class="brand-rank-body">
                <div class="brand-rank-top"><span class="brand-rank-name">${b.name}</span><span class="brand-rank-val">${b.visits} items sold</span></div>
                <div class="brand-rank-track"><div class="brand-rank-fill" style="width:0%;background:${b.color};transition:width 0.7s ease" data-pct="${b.pct}"></div></div>
            </div>
        </div>`).join('');
        setTimeout(()=>{ rankEl.querySelectorAll('.brand-rank-fill').forEach(el=>{ el.style.width=el.dataset.pct+'%'; }); },150);
    }

    // Camera detection summary
    const detSums=[{id:'CAM 01',zone:'FOH',count:68,pct:100,color:'#10b981'},{id:'CAM 02',zone:'TOP_AISLE',count:54,pct:79,color:'#8b5cf6'},
        {id:'CAM 03',zone:'CASH_COUNTER',count:31,pct:46,color:'#ff6b35'},{id:'CAM 04',zone:'MAKEUP',count:47,pct:69,color:'#f59e0b'},
        {id:'CAM 05',zone:'BOTTOM_AISLE',count:29,pct:43,color:'#3b82f6'}];
    const detEl=document.getElementById('cam-detection-summary');
    if(detEl){ detEl.innerHTML=detSums.map(d=>`
        <div class="cds-item">
            <span class="cds-id" style="color:${d.color}">${d.id}</span>
            <div class="cds-body"><div class="cds-track"><div class="cds-fill" style="width:0%;background:${d.color};transition:width 0.7s ease" data-pct="${d.pct}"></div></div><span class="cds-count">${d.count}</span></div>
            <span class="cds-zone">${d.zone}</span>
        </div>`).join('');
        setTimeout(()=>{ detEl.querySelectorAll('.cds-fill').forEach(el=>{ el.style.width=el.dataset.pct+'%'; }); },150);
    }
}
