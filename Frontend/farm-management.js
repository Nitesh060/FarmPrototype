/* ===================================================================
   Farm Management — Phase 1
   Farmer CRUD, multi-farm support, boundary capture via draw / GPS
   walking survey / KML-GeoJSON import.
   =================================================================== */

const API_BASE_URL =
    window.FARMSCORE_API_URL ||
    "https://farmprototype.onrender.com";

let selectedFarmerId = null;
let pendingPolygon = null;   // GeoJSON Feature, set by draw/gps/import before saving
let pendingCentroid = null;  // {lat, lng}
let gpsWatchId = null;
let gpsPoints = [];

// ---- Map setup ----
const map = L.map("fm-map", { zoomControl: true }).setView([20.5, 78.9], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

let drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const drawControl = new L.Control.Draw({
    edit: { featureGroup: drawnItems },
    draw: {
        polygon: { allowIntersection: false, showArea: true, shapeOptions: { color: "#34d399", weight: 3 } },
        rectangle: true, polyline: false, circle: false, circlemarker: false, marker: false,
    },
});
map.addControl(drawControl);

map.on(L.Draw.Event.CREATED, function (e) {
    drawnItems.clearLayers();
    drawnItems.addLayer(e.layer);
    pendingPolygon = e.layer.toGeoJSON();
    const centroid = turf.centroid(pendingPolygon).geometry.coordinates;
    pendingCentroid = { lat: centroid[1], lng: centroid[0] };
    document.getElementById("save-farm-btn").disabled = false;
});

// ---- Tabs ----
document.querySelectorAll(".fm-tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".fm-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        const mode = tab.dataset.mode;
        document.getElementById("draw-panel").style.display = mode === "draw" ? "block" : "none";
        document.getElementById("gps-panel").style.display = mode === "gps" ? "block" : "none";
        document.getElementById("import-panel").style.display = mode === "import" ? "block" : "none";
    });
});

// ---- GPS Walking Survey ----
document.getElementById("gps-start-btn").addEventListener("click", () => {
    if (!navigator.geolocation) {
        document.getElementById("gps-status").textContent = "GPS not available on this device/browser.";
        return;
    }
    gpsPoints = [];
    drawnItems.clearLayers();
    document.getElementById("gps-start-btn").style.display = "none";
    document.getElementById("gps-stop-btn").style.display = "inline-block";
    document.getElementById("gps-status").textContent = "Walking… 0 points recorded.";

    let trackLine = L.polyline([], { color: "#34d399", weight: 3 }).addTo(map);

    gpsWatchId = navigator.geolocation.watchPosition(
        (pos) => {
            const { latitude, longitude } = pos.coords;
            gpsPoints.push([longitude, latitude]);
            trackLine.addLatLng([latitude, longitude]);
            map.panTo([latitude, longitude]);
            document.getElementById("gps-status").textContent = `Walking… ${gpsPoints.length} points recorded.`;
        },
        (err) => {
            document.getElementById("gps-status").textContent = `GPS error: ${err.message}`;
        },
        { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 }
    );
});

document.getElementById("gps-stop-btn").addEventListener("click", () => {
    if (gpsWatchId !== null) navigator.geolocation.clearWatch(gpsWatchId);
    document.getElementById("gps-start-btn").style.display = "inline-block";
    document.getElementById("gps-stop-btn").style.display = "none";

    if (gpsPoints.length < 3) {
        document.getElementById("gps-status").textContent = "Need at least 3 points to make a boundary. Walk more and try again.";
        return;
    }

    const ring = [...gpsPoints];
    if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
        ring.push(ring[0]); // close the ring
    }
    pendingPolygon = { type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: {} };
    const centroid = turf.centroid(pendingPolygon).geometry.coordinates;
    pendingCentroid = { lat: centroid[1], lng: centroid[0] };

    drawnItems.clearLayers();
    L.geoJSON(pendingPolygon, { style: { color: "#34d399", weight: 3 } }).addTo(drawnItems);
    document.getElementById("gps-status").textContent = `Boundary closed — ${gpsPoints.length} points.`;
    document.getElementById("save-farm-btn").disabled = false;
});

// ---- KML / GeoJSON Import ----
document.getElementById("import-file-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const status = document.getElementById("import-status");
    status.textContent = "Uploading…";

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await bhumiAuthFetch(`${API_BASE_URL}/farms/import`, { method: "POST", body: formData });
        const data = await res.json();
        if (!res.ok || !data.polygon) {
            status.textContent = data.error || "Could not extract a boundary from this file.";
            return;
        }
        pendingPolygon = { type: "Feature", geometry: data.polygon, properties: {} };
        const centroid = turf.centroid(pendingPolygon).geometry.coordinates;
        pendingCentroid = { lat: centroid[1], lng: centroid[0] };

        drawnItems.clearLayers();
        L.geoJSON(pendingPolygon, { style: { color: "#34d399", weight: 3 } }).addTo(drawnItems);
        map.fitBounds(L.geoJSON(pendingPolygon).getBounds());
        status.textContent = "Boundary imported successfully.";
        document.getElementById("save-farm-btn").disabled = false;
    } catch (err) {
        status.textContent = "Upload failed. Please try again.";
    }
});

// ---- Farmer CRUD ----
async function loadFarmers(search = "") {
    const url = search ? `${API_BASE_URL}/farmers?search=${encodeURIComponent(search)}` : `${API_BASE_URL}/farmers`;
    const res = await bhumiAuthFetch(url);
    if (res.status === 503) {
        document.getElementById("db-unconfigured-notice").style.display = "block";
        document.getElementById("fm-content").style.display = "none";
        return;
    }
    document.getElementById("db-unconfigured-notice").style.display = "none";
    document.getElementById("fm-content").style.display = "block";

    const data = await res.json();
    const farmers = data.farmers || [];
    document.getElementById("farmer-count").textContent = `(${farmers.length})`;

    const list = document.getElementById("farmer-list");
    if (!farmers.length) {
        list.innerHTML = `<p class="empty-hint">No farmers registered yet.</p>`;
        return;
    }
    list.innerHTML = farmers.map(f => `
        <div class="fm-list-item ${f.id === selectedFarmerId ? "selected" : ""}" data-id="${f.id}">
            <div class="fm-list-item-title">${f.name}</div>
            <div class="fm-list-item-sub">${[f.village, f.district, f.state].filter(Boolean).join(", ") || "—"} · ${f.farm_count} farm(s)</div>
        </div>`).join("");

    list.querySelectorAll(".fm-list-item").forEach(el => {
        el.addEventListener("click", () => selectFarmer(el.dataset.id, el.querySelector(".fm-list-item-title").textContent));
    });
}

document.getElementById("farmer-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
        name: document.getElementById("farmer-name").value.trim(),
        phone: document.getElementById("farmer-phone").value.trim() || null,
        village: document.getElementById("farmer-village").value.trim() || null,
        district: document.getElementById("farmer-district").value.trim() || null,
        state: document.getElementById("farmer-state").value.trim() || null,
    };
    if (!body.name) return;

    const res = await bhumiAuthFetch(`${API_BASE_URL}/farmers`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (res.ok) {
        e.target.reset();
        loadFarmers();
    }
});

document.getElementById("farmer-search").addEventListener("input", (e) => loadFarmers(e.target.value));

function selectFarmer(id, name) {
    selectedFarmerId = id;
    document.getElementById("selected-farmer-name").textContent = name;
    document.getElementById("farms-panel").style.display = "block";
    document.querySelectorAll(".fm-list-item").forEach(el => el.classList.toggle("selected", el.dataset.id === id));
    loadFarms(id);
    loadConsents(id);
    loadLoans(id);
}

// ---- Loan Lifecycle (5-stage: Application -> Disbursement -> In-Season -> Pre-Harvest -> Renewal) ----
const LOAN_STAGES = ["Application", "Disbursement", "In-Season", "Pre-Harvest", "Renewal"];
const STAGE_COLORS = { Application: "#888", Disbursement: "#38bdf8", "In-Season": "#f59e0b", "Pre-Harvest": "#34d399", Renewal: "#a78bfa" };

async function loadLoans(farmerId) {
    const list = document.getElementById("loans-list");
    try {
        const res = await bhumiAuthFetch(`${API_BASE_URL}/farmers/${farmerId}/loans`);
        const data = await res.json();
        const loans = data.loans || [];

        if (!loans.length) {
            list.innerHTML = `<p class="empty-hint">No loans yet.</p>`;
            return;
        }
        list.innerHTML = loans.map(l => {
            const nextIdx = LOAN_STAGES.indexOf(l.stage) + 1;
            const nextStage = nextIdx < LOAN_STAGES.length ? LOAN_STAGES[nextIdx] : null;
            return `
                <div class="fm-list-item">
                    <div class="fm-list-item-title">
                        ${l.crop || "Loan"} — ₹${(l.requested_amount_rs || 0).toLocaleString("en-IN")}
                        <span style="color:${STAGE_COLORS[l.stage] || "#888"};font-weight:700;float:right;">${l.stage}</span>
                    </div>
                    <div class="fm-list-item-sub">
                        ${l.approved_ceiling_rs ? `Approved ceiling: ₹${l.approved_ceiling_rs.toLocaleString("en-IN")} (${l.bcis_tier_at_approval || "—"})` : "Not yet approved"}
                    </div>
                    ${nextStage ? `<button type="button" class="shell-theme-btn" data-loan-id="${l.id}" data-next-stage="${nextStage}" style="margin-top:6px;">Advance to ${nextStage} →</button>` : ""}
                </div>`;
        }).join("");

        list.querySelectorAll("button[data-loan-id]").forEach(btn => {
            btn.addEventListener("click", async () => {
                await bhumiAuthFetch(`${API_BASE_URL}/loans/${btn.dataset.loanId}/advance`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ stage: btn.dataset.nextStage }),
                });
                loadLoans(farmerId);
            });
        });
    } catch (err) {
        list.innerHTML = `<p class="empty-hint">Could not load loans.</p>`;
    }
}

document.getElementById("create-loan-btn").addEventListener("click", async () => {
    if (!selectedFarmerId) return;
    const amount = document.getElementById("loan-amount-input").value;
    const crop = document.getElementById("loan-crop-input").value.trim();

    await bhumiAuthFetch(`${API_BASE_URL}/farmers/${selectedFarmerId}/loans`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requested_amount_rs: amount ? parseFloat(amount) : null, crop: crop || null }),
    });
    document.getElementById("loan-amount-input").value = "";
    document.getElementById("loan-crop-input").value = "";
    loadLoans(selectedFarmerId);
});

// ---- Consent & Privacy (DPDP compliance) ----
const CONSENT_LABELS = {
    advisory: "Copilot Advisory (WhatsApp)",
    loan_data: "Loan Data Use",
    insurance_data: "Insurance Data Use",
    photo_storage: "Photo Storage (AI training)",
};

async function loadConsents(farmerId) {
    const list = document.getElementById("consent-list");
    list.innerHTML = `<p class="empty-hint">Loading…</p>`;
    try {
        const res = await bhumiAuthFetch(`${API_BASE_URL}/farmers/${farmerId}/consent`);
        const data = await res.json();
        const byType = {};
        (data.consents || []).forEach(c => { byType[c.consent_type] = c; });

        list.innerHTML = Object.keys(CONSENT_LABELS).map(type => {
            const rec = byType[type];
            const granted = rec && rec.granted === "granted";
            return `
                <div class="enrichment-row">
                    <span class="er-icon">${granted ? "✅" : "⬜"}</span>
                    <span class="er-label">${CONSENT_LABELS[type]}</span>
                    <span class="er-value" style="cursor:pointer;text-decoration:underline;" data-type="${type}" data-current="${granted}">
                        ${granted ? "Granted" : "Not granted"}
                    </span>
                </div>`;
        }).join("");

        list.querySelectorAll("span[data-type]").forEach(el => {
            el.addEventListener("click", async () => {
                const type = el.dataset.type;
                const currentlyGranted = el.dataset.current === "true";
                await bhumiAuthFetch(`${API_BASE_URL}/farmers/${farmerId}/consent`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ consent_type: type, granted: !currentlyGranted }),
                });
                loadConsents(farmerId);
            });
        });
    } catch (err) {
        list.innerHTML = `<p class="empty-hint">Could not load consent records.</p>`;
    }
}

document.getElementById("request-deletion-btn").addEventListener("click", async () => {
    if (!selectedFarmerId) return;
    if (!confirm("Flag this farmer's data for deletion? This starts the 72-hour deletion clock — it does not delete anything automatically.")) return;
    await bhumiAuthFetch(`${API_BASE_URL}/farmers/${selectedFarmerId}/request-deletion`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
    });
    alert("Deletion request recorded. An admin must complete the actual data removal.");
});
async function loadFarms(farmerId) {
    const res = await bhumiAuthFetch(`${API_BASE_URL}/farmers/${farmerId}/farms`);
    const data = await res.json();
    const farms = data.farms || [];

    const list = document.getElementById("farm-list");
    if (!farms.length) {
        list.innerHTML = `<p class="empty-hint">No farms yet — add one below.</p>`;
    } else {
        list.innerHTML = farms.map(f => `
            <div class="fm-list-item">
                <div class="fm-list-item-title">${f.label || "Unlabeled farm"} <span style="float:right;">🗑️</span></div>
                <div class="fm-list-item-sub">
                    ${f.lat.toFixed(4)}°, ${f.lng.toFixed(4)}° · ${f.area_ha ? f.area_ha.toFixed(2) + " ha" : "area unknown"} · ${f.survey_method || "—"}
                </div>
            </div>`).join("");

        list.querySelectorAll(".fm-list-item").forEach((el, i) => {
            el.querySelector("span").addEventListener("click", async (ev) => {
                ev.stopPropagation();
                if (!confirm("Delete this farm?")) return;
                await bhumiAuthFetch(`${API_BASE_URL}/farms/${farms[i].id}`, { method: "DELETE" });
                loadFarms(farmerId);
            });
        });
    }

    // Show all farm boundaries/pins on the map for context
    drawnItems.clearLayers();
    farms.forEach(f => {
        if (f.polygon) {
            L.geoJSON(f.polygon, { style: { color: "#60a5fa", weight: 2, fillOpacity: 0.1 } }).addTo(drawnItems);
        } else {
            L.marker([f.lat, f.lng]).addTo(drawnItems);
        }
    });
    if (farms.length) {
        try { map.fitBounds(drawnItems.getBounds(), { maxZoom: 15 }); } catch (e) { /* single point, ignore */ }
    }
}

document.getElementById("save-farm-btn").addEventListener("click", async () => {
    if (!selectedFarmerId || !pendingCentroid) return;

    const activeTab = document.querySelector(".fm-tab.active").dataset.mode;
    const surveyMethod = { draw: "drawn", gps: "gps_walk", import: pendingPolygon ? "geojson_import" : "point_only" }[activeTab] || "drawn";

    const body = {
        lat: pendingCentroid.lat,
        lng: pendingCentroid.lng,
        label: document.getElementById("farm-label").value.trim() || null,
        polygon: pendingPolygon,
        survey_method: surveyMethod,
    };

    const res = await bhumiAuthFetch(`${API_BASE_URL}/farmers/${selectedFarmerId}/farms`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });

    if (res.ok) {
        pendingPolygon = null;
        pendingCentroid = null;
        document.getElementById("farm-label").value = "";
        document.getElementById("save-farm-btn").disabled = true;
        loadFarms(selectedFarmerId);
        loadFarmers(); // refresh farm_count in the farmer list
    } else {
        const err = await res.json();
        document.getElementById("error-box").textContent = err.error || "Could not save farm.";
        document.getElementById("error-box").style.display = "block";
    }
});

// ---- Init ----
loadFarmers();
document.getElementById("fm-subtitle").textContent = "Register farmers, capture farm boundaries, manage multiple farms per farmer.";
