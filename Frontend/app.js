/**
 * app.js
 * ======
 * FarmScore frontend application logic.
 *
 * - Initialises the Leaflet map.
 * - Reads lat/lng from inputs or map click.
 * - Calls the backend via calculateFarmScore().
 * - Renders score ring, grade badge, parameter cards, weight bars.
 *
 * No mock data. No proxy calculations. All data comes from the backend.
 */

/* ===================================================================
   API Client
   =================================================================== */

const API_BASE_URL =
    window.FARMSCORE_API_URL ||
    "https://farmprototype-1.onrender.com";

/**
 * Call the FarmScore backend to calculate an agricultural suitability score.
 */
async function calculateFarmScore(lat, lng) {
    const url = `${API_BASE_URL}/calculate`;

    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lng }),
    });

    const data = await response.json();

    if (!response.ok) {
        const message = data.error || data.detail || `Server error ${response.status}`;
        throw new Error(message);
    }

    return data;
}

/* ===================================================================
   Map Initialisation
   =================================================================== */

let marker = null;

const map = L.map("map", { zoomControl: true }).setView([20.5, 78.9], 5);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
}).addTo(map);

const farmIcon = L.divIcon({
    className: "",
    html: `<div style="width:18px;height:18px;background:#2d6a4f;border:3px solid #fff;border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,0.3)"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
});

/* ===================================================================
   Map Click → populate inputs
   =================================================================== */

map.on("click", function (e) {
    const { lat, lng } = e.latlng;
    document.getElementById("lat-input").value = lat.toFixed(5);
    document.getElementById("lng-input").value = lng.toFixed(5);
    placeMarker(lat, lng);
});

function placeMarker(lat, lng) {
    if (marker) map.removeLayer(marker);
    marker = L.marker([lat, lng], { icon: farmIcon }).addTo(map);
}

/* ===================================================================
   Grade Assignment
   =================================================================== */

function gradeStyle(grade) {
    const styles = {
        Excellent: { bg: "#d4edda", color: "#155724" },
        Good: { bg: "#d6eaf8", color: "#154360" },
        Average: { bg: "#fef9e7", color: "#7d6608" },
        Fair: { bg: "#fdebd0", color: "#784212" },
        Poor: { bg: "#fadbd8", color: "#922b21" },
    };
    return styles[grade] || styles.Poor;
}

/* ===================================================================
   Score Ring Animation
   =================================================================== */

function updateRing(score) {
    const pct = (score - 300) / 600; // 300–900

    const circumference = 339.3;
    const offset = circumference * (1 - pct);

    const arc = document.getElementById("ring-arc");
    arc.style.transition = "stroke-dashoffset 1s ease";
    arc.setAttribute("stroke-dashoffset", offset);

    const hue = Math.round(pct * 120);
    arc.setAttribute("stroke", `hsl(${hue}, 55%, 40%)`);
}

/* ===================================================================
   Render Result
   =================================================================== */

const PARAM_ORDER = ["groundwater", "ndvi", "ndmi", "rainfall", "temperature"];

const PARAM_LABELS = {
    groundwater: "Groundwater",
    ndvi: "Vegetation (NDVI)",
    ndmi: "Moisture (NDMI)",
    rainfall: "Rainfall",
    temperature: "Temperature",
};

const PARAM_COLORS = ["#2d6a4f", "#1a7a3c", "#0f6e56", "#186e8f", "#5a3e8b"];
const WEIGHT_COLORS = ["#2d6a4f", "#1e8449", "#0f6e56", "#1a5276", "#6c3483"];

function renderResult(data) {
    const { score, grade, components, coordinates, elapsed_seconds } = data;

    // ---- Score ring ----
    document.getElementById("final-score").textContent = score;
    updateRing(score);

    // ---- Grade badge ----
    const gs = gradeStyle(grade);
    const gradeEl = document.getElementById("score-grade");
    gradeEl.textContent = grade;
    gradeEl.style.background = gs.bg;
    gradeEl.style.color = gs.color;

    // ---- Coordinates display ----
    document.getElementById("coord-display").textContent =
        `${coordinates.lat.toFixed(4)}°N, ${coordinates.lng.toFixed(4)}°E`;

    // ---- Parameter cards ----
    const grid = document.getElementById("params-grid");
    grid.innerHTML = PARAM_ORDER.map((key, i) => {
        const c = components[key];
        if (!c) return "";
        const pct = Math.max(0, Math.min(100, c.sub_score));
        const rawDisplay =
            typeof c.raw_value === "number"
                ? c.raw_value.toFixed(3)
                : c.raw_value;
        const unitHtml = c.unit
            ? ` <span style="font-size:0.65rem;font-weight:400;color:var(--text-muted)">${c.unit}</span>`
            : "";
        const availability = c.data_available
            ? ""
            : ` <span style="font-size:0.6rem;color:var(--red)">⚠ no data</span>`;

        return `
            <div class="param-card">
                <div class="p-name">${PARAM_LABELS[key] || key}</div>
                <div class="p-value">${rawDisplay}${unitHtml}</div>
                <div class="p-score">Score: ${c.sub_score.toFixed(1)} · w=${c.weight}%${availability}</div>
                <div class="mini-bar">
                    <div class="mini-bar-fill" style="width:${pct}%;background:${PARAM_COLORS[i]}"></div>
                </div>
                <div style="font-size:0.6rem;color:var(--text-muted);margin-top:4px">${c.source}</div>
            </div>`;
    }).join("");

    // ---- Weight contribution bars ----
    const barsEl = document.getElementById("weight-bars");
    barsEl.innerHTML = PARAM_ORDER.map((key, i) => {
        const c = components[key];
        if (!c) return "";
        const contribution = c.weighted_contribution.toFixed(1);
        return `
            <div class="weight-row">
                <span class="w-label">${(PARAM_LABELS[key] || key).split(" ")[0]}</span>
                <div class="weight-bar">
                    <div class="weight-bar-inner" style="width:${c.sub_score}%;background:${WEIGHT_COLORS[i]}"></div>
                </div>
                <span class="w-val">${contribution}</span>
            </div>`;
    }).join("");

    // ---- Show panel ----
    document.getElementById("result-panel").style.display = "block";
}

/* ===================================================================
   Compute Score — single entry point called on button click
   =================================================================== */

async function computeScore() {
    const lat = parseFloat(document.getElementById("lat-input").value);
    const lng = parseFloat(document.getElementById("lng-input").value);

    const errBox = document.getElementById("error-box");
    errBox.style.display = "none";

    // ---- Validate ----
    if (isNaN(lat) || isNaN(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
        errBox.textContent = "Please enter valid coordinates or click on the map.";
        errBox.style.display = "block";
        return;
    }

    placeMarker(lat, lng);
    map.panTo([lat, lng]);

    // ---- UI: loading state ----
    const btn = document.getElementById("calc-btn");
    const btnText = document.getElementById("btn-text");
    const spinner = document.getElementById("spinner");
    btn.disabled = true;
    btnText.textContent = "Fetching satellite data…";
    spinner.style.display = "block";

    try {
        // ---- Call backend API (api.js) ----
        btnText.textContent = "Querying Earth Engine…";
        const result = await calculateFarmScore(lat, lng);

        // ---- Render ----
        renderResult(result);

    } catch (err) {
        errBox.textContent = err.message || "An unexpected error occurred.";
        errBox.style.display = "block";
    } finally {
        btn.disabled = false;
        btnText.textContent = "Calculate FarmScore";
        spinner.style.display = "none";
    }
}

/* ===================================================================
   Global Event Listeners
   =================================================================== */

document.addEventListener("keydown", function (e) {
    if (e.key === "Enter") computeScore();
});
