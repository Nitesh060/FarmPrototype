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
        body: JSON.stringify({     lat,     lng,     polygon: farmPolygon }),
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

const streetLayer = L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        attribution: "© OpenStreetMap contributors",
        maxZoom: 19,
    }
);

const satelliteLayer = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
        attribution: "Tiles © Esri",
        maxZoom: 19,
    }
);

// Default layer
satelliteLayer.addTo(map);

// Layer switcher
L.control.layers(
    {
        "Road Map": streetLayer,
        "Satellite": satelliteLayer,
    }
).addTo(map);
// Search Control
L.Control.geocoder({
    defaultMarkGeocode: false
})
.on("markgeocode", function (e) {

    const center = e.geocode.center;

    map.setView(center, 16);

    placeMarker(center.lat, center.lng);
   fetchLocationDetails(center.lat, center.lng);
   fetchWeather(center.lat, center.lng);

    document.getElementById("lat-input").value = center.lat.toFixed(6);
    document.getElementById("lng-input").value = center.lng.toFixed(6);

})
.addTo(map);
/* ==========================================================
   Polygon Layer
   ========================================================== */

let drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

let farmPolygon = null;

const drawControl = new L.Control.Draw({

    edit: {
        featureGroup: drawnItems
    },

    draw: {

        polygon: {
            allowIntersection: false,
            showArea: true,
            shapeOptions: {
                color: "#2d6a4f",
                weight: 3
            }
        },

        rectangle: true,

        polyline: false,
        circle: false,
        circlemarker: false,
        marker: false

    }

});

map.addControl(drawControl);
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
   fetchLocationDetails(lat, lng);
   fetchWeather(lat, lng);
});

function placeMarker(lat, lng) {
   /* ==========================================================
   Polygon Created
   ========================================================== */

map.on(L.Draw.Event.CREATED, function (e) {

    drawnItems.clearLayers();

    const layer = e.layer;

    drawnItems.addLayer(layer);

    farmPolygon = layer.toGeoJSON();
   const areaSqM = turf.area(farmPolygon);

const areaAcres = areaSqM / 4046.85642;

const areaHectare = areaSqM / 10000;

document.getElementById("farm-area").value =
`${areaAcres.toFixed(2)} Acres (${areaHectare.toFixed(2)} ha)`;

    console.log("Polygon");

    console.log(farmPolygon);

});
    if (marker) map.removeLayer(marker);
    marker = L.marker([lat, lng], { icon: farmIcon }).addTo(map);
}
async function fetchLocationDetails(lat, lng) {

    try {

        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`
        );

        const data = await response.json();

        const addr = data.address || {};

        document.getElementById("village-input").value =
            addr.village ||
            addr.town ||
            addr.city ||
            addr.hamlet ||
            "";

        document.getElementById("district-input").value =
            addr.county ||
            addr.state_district ||
            "";

        document.getElementById("state-input").value =
            addr.state || "";

        document.getElementById("pincode-input").value =
            addr.postcode || "";

    } catch (err) {
        console.error("Reverse Geocoding Error:", err);
    }

}

/* ===================================================================
   Weather Forecast (Open-Meteo — free, no API key required)
   =================================================================== */

const WMO_WEATHER = {
    0:  { icon: "☀️", label: "Clear sky" },
    1:  { icon: "🌤️", label: "Mainly clear" },
    2:  { icon: "⛅", label: "Partly cloudy" },
    3:  { icon: "☁️", label: "Overcast" },
    45: { icon: "🌫️", label: "Fog" },
    48: { icon: "🌫️", label: "Depositing fog" },
    51: { icon: "🌦️", label: "Light drizzle" },
    53: { icon: "🌦️", label: "Drizzle" },
    55: { icon: "🌦️", label: "Dense drizzle" },
    61: { icon: "🌧️", label: "Light rain" },
    63: { icon: "🌧️", label: "Rain" },
    65: { icon: "🌧️", label: "Heavy rain" },
    71: { icon: "❄️", label: "Light snow" },
    73: { icon: "❄️", label: "Snow" },
    75: { icon: "❄️", label: "Heavy snow" },
    80: { icon: "🌦️", label: "Rain showers" },
    81: { icon: "🌦️", label: "Rain showers" },
    82: { icon: "🌧️", label: "Violent showers" },
    95: { icon: "⛈️", label: "Thunderstorm" },
    96: { icon: "⛈️", label: "Thunderstorm, hail" },
    99: { icon: "⛈️", label: "Thunderstorm, hail" },
};

function weatherInfo(code) {
    return WMO_WEATHER[code] || { icon: "🌡️", label: "Unknown" };
}

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

async function fetchWeather(lat, lng) {
    const card = document.getElementById("weather-card");

    try {
        const url =
            `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}` +
            `&current_weather=true` +
            `&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum` +
            `&timezone=auto`;

        const response = await fetch(url);
        const data = await response.json();

        if (!data.current_weather) throw new Error("No weather data");

        // ---- Current conditions ----
        const current = data.current_weather;
        const info = weatherInfo(current.weathercode);

        document.getElementById("weather-icon").textContent = info.icon;
        document.getElementById("weather-temp").textContent =
            `${Math.round(current.temperature)}°C`;
        document.getElementById("weather-desc").textContent = info.label;
        document.getElementById("weather-wind").textContent =
            `💨 ${Math.round(current.windspeed)} km/h`;

        // ---- 5-day forecast strip ----
        const daily = data.daily;
        const strip = document.getElementById("weather-forecast");

        strip.innerHTML = daily.time.slice(0, 5).map((dateStr, i) => {
            const d = new Date(dateStr);
            const dInfo = weatherInfo(daily.weathercode[i]);
            const max = Math.round(daily.temperature_2m_max[i]);
            const min = Math.round(daily.temperature_2m_min[i]);
            const rain = daily.precipitation_sum[i];

            return `
                <div class="weather-day">
                    <div class="wd-label">${i === 0 ? "Today" : DAY_NAMES[d.getDay()]}</div>
                    <div class="wd-icon">${dInfo.icon}</div>
                    <div class="wd-temp">${max}° <span>${min}°</span></div>
                    ${rain > 0 ? `<div class="wd-rain">💧${rain}mm</div>` : ""}
                </div>`;
        }).join("");

        card.style.display = "block";

    } catch (err) {
        console.error("Weather fetch error:", err);
        card.style.display = "none";
    }
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
   const {
    score,
    grade,
    components,
    coordinates,
    elapsed_seconds,
    recommended_crops,
    ai_summary
} = data;

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

   // ---- Crop Recommendation ----

if (recommended_crops) {

    document.getElementById("crop-card").style.display = "block";

    let html = `
        <div class="param-card">

            <h4>🥇 ${recommended_crops.primary.crop}</h4>

            <p>Suitability Score : ${recommended_crops.primary.score}%</p>

            <hr>

            <h4>🥈 ${recommended_crops.secondary.crop}</h4>

            <p>Suitability Score : ${recommended_crops.secondary.score}%</p>

        </div>
    `;

    document.getElementById("crop-result").innerHTML = html;

}

// ---- AI Land Cover (CNN) ----

if (data.land_cover) {

    document.getElementById("land-cover-card").style.display = "block";

    const lc = data.land_cover;
    const rows = Object.entries(lc.probabilities || {})
        .sort((a, b) => b[1] - a[1])
        .map(([label, pct]) => `
            <div class="weight-row">
                <span class="w-label">${label}</span>
                <div class="weight-bar">
                    <div class="weight-bar-inner" style="width:${pct}%;background:#22d3a5"></div>
                </div>
                <span class="w-val">${pct}%</span>
            </div>`)
        .join("");

    document.getElementById("land-cover-result").innerHTML = `
        <p style="margin:0 0 12px;font-size:0.86rem;font-weight:600;">
            ${lc.label} <span style="color:var(--text-muted);font-weight:400">(${lc.confidence}% confidence)</span>
        </p>
        <div class="weight-bar-wrap">${rows}</div>
    `;

} else {
    document.getElementById("land-cover-card").style.display = "none";
}

    // ---- Show panel ----
   // ---- AI Summary ----

if (ai_summary) {

    document.getElementById("ai-summary-card").style.display = "block";

    document.getElementById("ai-summary-result").innerHTML =
        "<ul>" +
        ai_summary.map(item => `<li>${item}</li>`).join("") +
        "</ul>";

}
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
/* ===================================================================
   Current Location Button
   =================================================================== */

function getCurrentLocation() {

    if (!navigator.geolocation) {
        alert("Geolocation is not supported by your browser.");
        return;
    }

    const btn = document.getElementById("location-btn");
    const originalText = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = "📍 Getting Location...";

    navigator.geolocation.getCurrentPosition(

        function(position) {

            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            document.getElementById("lat-input").value = lat.toFixed(6);
            document.getElementById("lng-input").value = lng.toFixed(6);

            placeMarker(lat, lng);
            map.setView([lat, lng], 15);
            fetchLocationDetails(lat, lng);
            fetchWeather(lat, lng);

            btn.disabled = false;
            btn.innerHTML = originalText;

        },

        function(error) {

            btn.disabled = false;
            btn.innerHTML = originalText;

            switch(error.code){

                case error.PERMISSION_DENIED:
                    alert("Location permission denied.");
                    break;

                case error.POSITION_UNAVAILABLE:
                    alert("Location unavailable.");
                    break;

                case error.TIMEOUT:
                    alert("Location request timed out.");
                    break;

                default:
                    alert("Unable to get current location.");
            }

            console.error(error);

        },

        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }

    );
}

// Attach click event
document.getElementById("location-btn").addEventListener("click", getCurrentLocation);
