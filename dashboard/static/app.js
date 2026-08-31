/**
 * Smart Agriculture Dashboard Front-End JavaScript
 * Handles SSE live telemetry streaming, Chart.js multi-sensor rendering,
 * valve override controls, dynamic threshold tuning, soil simulation,
 * CRUD operations for Zones, Schedules, Field Notes, byte-by-byte LoRa packet inspection, and power calculator.
 */

let moistureChart = null;
const maxChartPoints = 40;
const chartData = {
    labels: [],
    moisture: [],
    valve: [],
    temperature: []
};

document.addEventListener("DOMContentLoaded", () => {
    initChart();
    fetchHistory();
    initSSE();
    recalculatePower();
    
    // Fetch CRUD Lists
    fetchZones();
    fetchSchedules();
    fetchNotes();
});

// Initialize Chart.js
function initChart() {
    const ctx = document.getElementById("moistureChart").getContext("2d");

    moistureChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: "Soil Moisture (%)",
                    data: chartData.moisture,
                    borderColor: "#38bdf8",
                    backgroundColor: "rgba(56, 189, 248, 0.1)",
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.3,
                    yAxisID: "y"
                },
                {
                    label: "Valve State (1=OPEN, 0=CLOSED)",
                    data: chartData.valve,
                    borderColor: "#10b981",
                    backgroundColor: "rgba(16, 185, 129, 0.2)",
                    borderWidth: 2,
                    stepped: true,
                    fill: true,
                    yAxisID: "y1"
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            scales: {
                x: {
                    grid: { color: "rgba(51, 65, 85, 0.4)" },
                    ticks: { color: "#94a3b8", maxTicksLimit: 8 }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: "rgba(51, 65, 85, 0.4)" },
                    ticks: { color: "#38bdf8", callback: v => v + "%" },
                    title: { display: true, text: "Soil Moisture %", color: "#38bdf8" }
                },
                y1: {
                    min: 0,
                    max: 1.2,
                    position: "right",
                    grid: { drawOnChartArea: false },
                    ticks: {
                        color: "#10b981",
                        stepSize: 1,
                        callback: v => (v === 1 ? "OPEN" : "CLOSED")
                    }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// --- CRUD 1: Agricultural Field Zones ---
async function fetchZones() {
    try {
        const res = await fetch("/api/zones");
        const json = await res.json();
        renderZones(json.zones || []);
    } catch (err) {
        console.error("Fetch zones error:", err);
    }
}

function renderZones(zones) {
    const container = document.getElementById("zones-list-container");
    if (!container) return;

    if (zones.length === 0) {
        container.innerHTML = `<div class="bg-slate-900 border border-slate-700 rounded-xl p-4 text-center text-slate-500 text-xs col-span-full">No zones created yet. Use the form above to add a new plot!</div>`;
        return;
    }

    container.innerHTML = zones.map(z => `
        <div class="bg-slate-900 border border-slate-700 hover:border-slate-600 rounded-xl p-4 space-y-2 transition-all">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="text-sm font-bold text-white">${z.name}</h3>
                    <span class="text-[11px] text-emerald-400 font-medium">${z.crop_type} (${z.soil_type} Soil)</span>
                </div>
                <button onclick="deleteZone(${z.id})" class="text-slate-500 hover:text-rose-400 transition-all p-1" title="Delete Zone">
                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
            </div>
            <div class="text-[11px] text-slate-400 grid grid-cols-2 gap-1 border-t border-slate-800 pt-2 font-mono">
                <div>Dry Thresh: <strong class="text-cyan-300">${z.dry_threshold_pct}%</strong></div>
                <div>Target: <strong class="text-emerald-300">${z.target_moisture_pct}%</strong></div>
            </div>
        </div>
    `).join("");

    if (window.lucide) lucide.createIcons();
}

async function submitNewZone(event) {
    event.preventDefault();
    const name = document.getElementById("zone-name").value;
    const crop = document.getElementById("zone-crop").value;
    const dry = parseFloat(document.getElementById("zone-dry").value) || 30.0;

    try {
        const res = await fetch("/api/zones/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, crop_type: crop, dry_threshold_pct: dry, target_moisture_pct: dry + 35.0 })
        });
        const json = await res.json();
        if (json.status === "success") {
            document.getElementById("zone-name").value = "";
            document.getElementById("zone-crop").value = "";
            fetchZones();
        }
    } catch (err) {
        console.error("Create zone error:", err);
    }
}

async function deleteZone(id) {
    if (!confirm("Are you sure you want to delete this agricultural zone?")) return;
    try {
        await fetch(`/api/zones/${id}`, { method: "DELETE" });
        fetchZones();
    } catch (err) {
        console.error("Delete zone error:", err);
    }
}

// --- CRUD 2: Automated Irrigation Schedules ---
async function fetchSchedules() {
    try {
        const res = await fetch("/api/schedules");
        const json = await res.json();
        renderSchedules(json.schedules || []);
    } catch (err) {
        console.error("Fetch schedules error:", err);
    }
}

function renderSchedules(schedules) {
    const container = document.getElementById("schedules-list-container");
    if (!container) return;

    if (schedules.length === 0) {
        container.innerHTML = `<div class="text-xs text-slate-500 text-center p-3 bg-slate-900 rounded-xl border border-slate-700">No schedules configured yet.</div>`;
        return;
    }

    container.innerHTML = schedules.map(s => `
        <div class="bg-slate-900 border border-slate-700 rounded-xl p-3 flex justify-between items-center text-xs">
            <div class="space-y-0.5">
                <div class="font-bold text-white flex items-center gap-2">
                    ${s.name}
                    <span class="font-mono text-cyan-400 bg-cyan-950/50 px-2 py-0.5 rounded text-[10px]">${s.start_time} (${s.duration_minutes}m)</span>
                </div>
                <div class="text-[11px] text-slate-400">${s.days_of_week}</div>
            </div>
            <div class="flex items-center gap-2">
                <button onclick="toggleSchedule(${s.id}, ${!s.enabled})" class="px-2 py-1 rounded text-[10px] font-bold ${s.enabled ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-800 text-slate-500'}">
                    ${s.enabled ? 'ACTIVE' : 'PAUSED'}
                </button>
                <button onclick="deleteSchedule(${s.id})" class="text-slate-500 hover:text-rose-400 p-1">
                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
            </div>
        </div>
    `).join("");

    if (window.lucide) lucide.createIcons();
}

async function submitNewSchedule(event) {
    event.preventDefault();
    const name = document.getElementById("sch-name").value;
    const time = document.getElementById("sch-time").value;
    const duration = parseInt(document.getElementById("sch-duration").value) || 15;

    try {
        const res = await fetch("/api/schedules/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, start_time: time, duration_minutes: duration })
        });
        const json = await res.json();
        if (json.status === "success") {
            document.getElementById("sch-name").value = "";
            fetchSchedules();
        }
    } catch (err) {
        console.error("Create schedule error:", err);
    }
}

async function toggleSchedule(id, enabled) {
    try {
        await fetch(`/api/schedules/${id}/toggle?enabled=${enabled}`, { method: "POST" });
        fetchSchedules();
    } catch (err) {
        console.error("Toggle schedule error:", err);
    }
}

async function deleteSchedule(id) {
    try {
        await fetch(`/api/schedules/${id}`, { method: "DELETE" });
        fetchSchedules();
    } catch (err) {
        console.error("Delete schedule error:", err);
    }
}

// --- CRUD 3: Field Inspection Notes ---
async function fetchNotes() {
    try {
        const res = await fetch("/api/notes");
        const json = await res.json();
        renderNotes(json.notes || []);
    } catch (err) {
        console.error("Fetch notes error:", err);
    }
}

function renderNotes(notes) {
    const container = document.getElementById("notes-list-container");
    if (!container) return;

    if (notes.length === 0) {
        container.innerHTML = `<div class="text-xs text-slate-500 text-center p-3 bg-slate-900 rounded-xl border border-slate-700">No field notes logged yet.</div>`;
        return;
    }

    container.innerHTML = notes.map(n => {
        const timeStr = new Date(n.timestamp * 1000).toLocaleString();
        return `
            <div class="bg-slate-900 border border-slate-700 rounded-xl p-3 space-y-1 text-xs">
                <div class="flex justify-between items-center text-slate-400 text-[10px]">
                    <span class="font-bold text-amber-400">${n.author}</span>
                    <span>${timeStr}</span>
                </div>
                <div class="text-slate-200">${n.note_text}</div>
            </div>
        `;
    }).join("");
}

async function submitNewNote(event) {
    event.preventDefault();
    const author = document.getElementById("note-author").value;
    const text = document.getElementById("note-text").value;

    try {
        const res = await fetch("/api/notes/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ author, note_text: text })
        });
        const json = await res.json();
        if (json.status === "success") {
            document.getElementById("note-text").value = "";
            fetchNotes();
        }
    } catch (err) {
        console.error("Create note error:", err);
    }
}

// --- Historical Telemetry Fetch ---
async function fetchHistory() {
    try {
        const res = await fetch("/api/history?limit=30");
        const json = await res.json();
        if (json.history) {
            populateTable(json.history);
            json.history.forEach(item => {
                const timeStr = new Date(item.timestamp * 1000).toLocaleTimeString();
                addPointToChart(timeStr, item.moisture_pct, item.valve_state === "OPEN" ? 1 : 0);
            });
        }
    } catch (err) {
        console.error("Failed to fetch history:", err);
    }
}

function populateTable(records) {
    const tbody = document.getElementById("telemetry-table-body");
    if (!tbody) return;

    if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="p-4 text-center text-slate-500">No telemetry recorded yet</td></tr>`;
        return;
    }

    tbody.innerHTML = records.slice(0, 10).map(r => {
        const timeStr = new Date(r.timestamp * 1000).toLocaleTimeString();
        const valveClass = r.valve_state === "OPEN" ? "text-emerald-400 font-bold" : "text-slate-400";
        return `
            <tr class="hover:bg-slate-800/60 transition-all">
                <td class="p-3 text-slate-300">${timeStr}</td>
                <td class="p-3 text-cyan-400 font-bold">Node #${r.node_id}</td>
                <td class="p-3 text-white font-bold">${r.moisture_pct}%</td>
                <td class="p-3 text-amber-300">${r.temperature_c}°C</td>
                <td class="p-3 ${valveClass}">${r.valve_state}</td>
                <td class="p-3 text-emerald-400">${r.health_score}</td>
                <td class="p-3 text-purple-300">${r.rssi_dbm} dBm</td>
                <td class="p-3 text-emerald-300">${r.snr_db} dB</td>
            </tr>
        `;
    }).join("");
}

// Connect to Server-Sent Events (SSE)
function initSSE() {
    const evtSource = new EventSource("/api/stream");

    evtSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        } catch (err) {
            console.error("SSE JSON decode error:", err);
        }
    };

    evtSource.onerror = (err) => {
        console.warn("SSE connection error. Retrying fallback poll...");
        evtSource.close();
        setTimeout(initSSE, 3000);
    };
}

// Update UI elements with new telemetry payload
function updateDashboard(data) {
    const summary = data.edge_summary;
    if (!summary) return;

    const sensor = summary.sensor;
    const valve = summary.valve;
    const analytics = summary.analytics;
    const lora = data.lora || {};
    const config = data.config || {};

    // 1. Hardware Status Badge
    const hwBadge = document.getElementById("badge-hw-mode");
    if (hwBadge) {
        if (config.MOCK_HARDWARE) {
            hwBadge.textContent = "Hardware: Simulator Mode";
            hwBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono";
        } else {
            hwBadge.textContent = "Hardware: PHYSICAL IoT CONNECTED";
            hwBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono font-bold animate-pulse";
        }
    }

    // 2. Update KPI Values
    document.getElementById("kpi-moisture").textContent = sensor.moisture_pct;
    document.getElementById("kpi-temp").textContent = sensor.temperature_c;
    document.getElementById("kpi-humidity").textContent = `${sensor.ambient_humidity_pct}%`;
    document.getElementById("kpi-ph").textContent = sensor.soil_ph || "6.8";
    document.getElementById("kpi-ec").textContent = `${sensor.electrical_conductivity_ec || "1.4"} mS/cm`;

    // Valve Badge & Water Volume Delivered
    const valveBadge = document.getElementById("kpi-valve-badge");
    const valveIconContainer = document.getElementById("kpi-valve-icon-container");
    const valveTimer = document.getElementById("kpi-valve-timer");
    document.getElementById("lbl-water-liters").textContent = `${valve.total_water_liters || 0.0} L`;

    if (valve.is_open) {
        valveBadge.textContent = "OPEN";
        valveBadge.className = "px-2.5 py-0.5 text-xs font-bold rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 glow-emerald animate-pulse-ring";
        valveIconContainer.className = "p-1.5 bg-emerald-500/20 text-emerald-400 rounded-lg";
        valveTimer.textContent = `${valve.current_run_seconds}s`;
    } else {
        valveBadge.textContent = "CLOSED";
        valveBadge.className = "px-2.5 py-0.5 text-xs font-bold rounded-lg bg-slate-700 text-slate-300";
        valveIconContainer.className = "p-1.5 bg-slate-700 text-slate-400 rounded-lg";
        valveTimer.textContent = "0s";
    }

    if (valve.manual_override) {
        document.getElementById("lbl-override-status").textContent = "Enabled (Manual)";
        document.getElementById("lbl-override-status").className = "text-amber-400 font-semibold";
    } else {
        document.getElementById("lbl-override-status").textContent = "Disabled (Auto)";
        document.getElementById("lbl-override-status").className = "text-slate-400";
    }

    // Health Score
    document.getElementById("kpi-health-score").textContent = analytics.health_score;
    const healthStatusEl = document.getElementById("kpi-health-status");
    healthStatusEl.textContent = analytics.health_status;
    document.getElementById("kpi-depletion-rate").textContent = `${analytics.depletion_rate_pct_hr}%/h`;

    if (analytics.health_status === "OPTIMAL") {
        healthStatusEl.className = "px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 font-medium";
    } else if (analytics.health_status === "MILD_STRESS") {
        healthStatusEl.className = "px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-medium";
    } else {
        healthStatusEl.className = "px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 font-medium";
    }

    // Decision Info
    document.getElementById("lbl-last-reason").textContent = analytics.last_decision_reason;
    document.getElementById("lbl-wilting-time").textContent = analytics.estimated_hours_to_wilting > 900 ? "N/A" : `${analytics.estimated_hours_to_wilting} hrs`;

    // Threshold labels
    document.getElementById("lbl-dry-thresh").textContent = config.DRY_THRESHOLD_PCT || 30;
    document.getElementById("lbl-target-thresh").textContent = config.TARGET_MOISTURE_PCT || 65;

    // LoRa RF Link
    if (lora) {
        document.getElementById("kpi-lora-rssi").textContent = lora.rssi_dbm || "-78";
        document.getElementById("kpi-lora-airtime").textContent = `${lora.airtime_ms || 51.5}ms`;
        document.getElementById("kpi-lora-snr").textContent = `${lora.snr_db || 9.5}dB`;
        document.getElementById("header-lora-freq").textContent = `LoRa ${lora.frequency_mhz || 868.1} MHz (SF${lora.spreading_factor || 7})`;
        if (lora.payload_hex) {
            renderHexInspector(lora.payload_hex);
        }
    }

    // Update Chart
    const timeStr = new Date(sensor.timestamp * 1000).toLocaleTimeString();
    addPointToChart(timeStr, sensor.moisture_pct, valve.is_open ? 1 : 0);
}

function addPointToChart(timeLabel, moistureVal, valveVal) {
    if (!moistureChart) return;
    
    chartData.labels.push(timeLabel);
    chartData.moisture.push(moistureVal);
    chartData.valve.push(valveVal);

    if (chartData.labels.length > maxChartPoints) {
        chartData.labels.shift();
        chartData.moisture.shift();
        chartData.valve.shift();
    }

    moistureChart.update();
}

function renderHexInspector(hexStr) {
    const el = document.getElementById("lbl-hex-payload");
    if (!el || !hexStr) return;

    const bytes = hexStr.match(/.{1,2}/g) || [];
    if (bytes.length < 16) return;

    el.innerHTML = `
        <span class="px-1.5 py-0.5 bg-blue-900/50 text-blue-300 rounded" title="Header">${bytes[0]}</span>
        <span class="px-1.5 py-0.5 bg-blue-900/50 text-blue-300 rounded" title="Node ID">${bytes[1]}</span>
        <span class="px-1.5 py-0.5 bg-cyan-900/50 text-cyan-300 rounded" title="Moisture % MSB">${bytes[2]}</span>
        <span class="px-1.5 py-0.5 bg-cyan-900/50 text-cyan-300 rounded" title="Moisture % LSB">${bytes[3]}</span>
        <span class="px-1.5 py-0.5 bg-amber-900/50 text-amber-300 rounded" title="Temp MSB">${bytes[4]}</span>
        <span class="px-1.5 py-0.5 bg-amber-900/50 text-amber-300 rounded" title="Temp LSB">${bytes[5]}</span>
        <span class="px-1.5 py-0.5 bg-indigo-900/50 text-indigo-300 rounded" title="Humidity MSB">${bytes[6]}</span>
        <span class="px-1.5 py-0.5 bg-indigo-900/50 text-indigo-300 rounded" title="Humidity LSB">${bytes[7]}</span>
        <span class="px-1.5 py-0.5 bg-emerald-900/50 text-emerald-300 rounded" title="Valve Code">${bytes[8]}</span>
        <span class="px-1.5 py-0.5 bg-emerald-900/50 text-emerald-300 rounded" title="Health Score">${bytes[9]}</span>
        <span class="px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded" title="Depletion MSB">${bytes[10]}</span>
        <span class="px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded" title="Depletion LSB">${bytes[11]}</span>
        <span class="px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded" title="Seq MSB">${bytes[12]}</span>
        <span class="px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded" title="Seq LSB">${bytes[13]}</span>
        <span class="px-1.5 py-0.5 bg-rose-900/50 text-rose-300 rounded" title="CRC16 MSB">${bytes[14]}</span>
        <span class="px-1.5 py-0.5 bg-rose-900/50 text-rose-300 rounded" title="CRC16 LSB">${bytes[15]}</span>
    `;
}

// Toggle manual valve override
async function toggleValveOverride(enable, forceOpen) {
    try {
        await fetch("/api/valve/control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ manual_override: enable, force_open: forceOpen })
        });
    } catch (err) {
        console.error("Failed to toggle valve override:", err);
    }
}

// Apply dynamic configuration changes
async function applyConfigChanges() {
    const dry = parseFloat(document.getElementById("cfg-dry-thresh").value);
    const target = parseFloat(document.getElementById("cfg-target-thresh").value);
    const maxRuntime = parseInt(document.getElementById("cfg-max-runtime").value);
    const sf = parseInt(document.getElementById("cfg-lora-sf").value);

    try {
        const res = await fetch("/api/config/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                dry_threshold_pct: dry,
                target_moisture_pct: target,
                max_valve_on_seconds: maxRuntime,
                lora_spreading_factor: sf
            })
        });
        const json = await res.json();
        if (json.status === "success") {
            alert("Edge Config Changes Applied Successfully!");
        }
    } catch (err) {
        console.error("Config update error:", err);
    }
}

// Toggle Hardware Mode (Physical vs Simulator)
async function toggleMockHardwareMode() {
    const hwBadge = document.getElementById("badge-hw-mode");
    const isMockCurrently = hwBadge && hwBadge.textContent.includes("Simulator");

    try {
        await fetch("/api/config/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mock_hardware: !isMockCurrently })
        });
    } catch (err) {
        console.error("Toggle hardware mode error:", err);
    }
}

// Weather / Environment Simulator Controls
function updateSimParams() {
    const rain = parseFloat(document.getElementById("slider-rain").value);
    document.getElementById("val-rain").textContent = `${rain.toFixed(1)} %/s`;
    
    fetch("/api/simulate/environment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rain_rate: rain })
    });
}

function setRain(val) {
    document.getElementById("slider-rain").value = val;
    updateSimParams();
}

function forceMoisture(val) {
    fetch("/api/simulate/environment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ forced_moisture: val })
    });
}

// Recalculate LoRa vs Wi-Fi power comparison
async function recalculatePower() {
    const cap = parseFloat(document.getElementById("calc-battery").value) || 2500;
    const interval = parseFloat(document.getElementById("calc-interval").value) || 15;

    try {
        const res = await fetch("/api/power-calculator", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                battery_capacity_mah: cap,
                interval_minutes: interval
            })
        });
        const data = await res.json();
        
        document.getElementById("res-lora-years").textContent = `${data.lora.lifespan_years} Years`;
        document.getElementById("res-lora-daily").textContent = `${data.lora.daily_joules} Joules / day`;

        if (data.wifi.lifespan_years < 1) {
            document.getElementById("res-wifi-years").textContent = `${data.wifi.lifespan_days} Days`;
        } else {
            document.getElementById("res-wifi-years").textContent = `${data.wifi.lifespan_years} Years`;
        }
        document.getElementById("res-wifi-daily").textContent = `${data.wifi.daily_joules} Joules / day`;

        document.getElementById("res-multiplier-banner").textContent = data.efficiency_multiplier;
    } catch (err) {
        console.error("Power calc error:", err);
    }
}
