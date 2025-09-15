// SPA navigation
document.querySelectorAll(".nav-link").forEach(a => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelectorAll(".nav-link").forEach(x => x.classList.remove("active"));
    a.classList.add("active");
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    const target = a.dataset.target;
    document.getElementById(target).classList.add("active");
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
});

// Chart.js setup
const ctx = document.getElementById("sensorChart").getContext("2d");
const sensorChart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      { label: 'Temperature (°C)', data: [], borderColor: '#ff4d4d', tension: 0.3 },
      { label: 'Humidity (%)', data: [], borderColor: '#1d8fe5', tension: 0.3 },
      { label: 'Soil Moisture (%)', data: [], borderColor: '#3aa14f', tension: 0.3 },
      { label: 'Heat Index (°C)', data: [], borderColor: '#ffa726', tension: 0.3 }
    ]
  },
  options: {
    responsive: true,
    scales: { y: { beginAtZero: true, max: 100 } }
  }
});

// DOM elements
const elTemp = document.getElementById("temp");
const elHum = document.getElementById("humidity");
const elHeat = document.getElementById("heatIndex");
const elSoil = document.getElementById("soil");
const elTempBar = document.getElementById("tempBar");
const elHumBar = document.getElementById("humBar");
const elHeatBar = document.getElementById("heatBar");
const elSoilBar = document.getElementById("soilBar");
const elSoilStatus = document.getElementById("soilStatus");
const elCropName = document.getElementById("cropName");
const elCropDetails = document.getElementById("cropDetails");
const elDos = document.getElementById("dos");
const elDonts = document.getElementById("donts");
const downloadBtn = document.getElementById("downloadHistoryBtn");
const alertBanner = document.getElementById("alertBanner");

// Update UI from /recommend result
function updateUI(data) {
  elTemp.innerText = (data.temperature ?? "--") + " °C";
  elHum.innerText = (data.humidity ?? "--") + " %";
  elHeat.innerText = (data.heat_index ?? "--") + " °C";
  elSoil.innerText = (data.soil ?? "--") + " %";

  elTempBar.style.width = Math.min((data.temperature ?? 0) * 2, 100) + "%";
  elHumBar.style.width = (data.humidity ?? 0) + "%";
  elHeatBar.style.width = Math.min((data.heat_index ?? 0) * 2, 100) + "%";
  elSoilBar.style.width = (data.soil ?? 0) + "%";

  if (data.soil_status) {
    elSoilStatus.innerText = data.soil_status;
    elSoilStatus.className = "soil-status " + data.soil_status.toLowerCase();
  } else {
    elSoilStatus.innerText = "--";
    elSoilStatus.className = "soil-status";
  }

  elCropName.innerText = data.name ?? "--";
  elCropDetails.innerText = data.details ?? "No details available.";
  elDos.innerHTML = (data.dos || []).map(d => `<li>${d}</li>`).join("");
  elDonts.innerHTML = (data.donts || []).map(d => `<li>${d}</li>`).join("");

  // Banner alert if soil < 25
  if (data.soil !== undefined && data.soil !== null && data.soil < 25) {
    alertBanner.style.display = "block";
  } else {
    alertBanner.style.display = "none";
  }
}

// Fetch recommendation (latest)
async function fetchRecommend() {
  try {
    const res = await fetch("/recommend");
    if (!res.ok) throw new Error("No data");
    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.warn("recommend fetch failed", err);
  }
}

// Update chart with /history (history returns entries with IST 'time')
async function updateChart() {
  try {
    const res = await fetch("/history");
    if (!res.ok) throw new Error("No history");
    const hist = await res.json();
    sensorChart.data.labels = hist.map(h => h.time || '');
    sensorChart.data.datasets[0].data = hist.map(h => h.temperature ?? null);
    sensorChart.data.datasets[1].data = hist.map(h => h.humidity ?? null);
    sensorChart.data.datasets[2].data = hist.map(h => h.soil ?? null);
    sensorChart.data.datasets[3].data = hist.map(h => h.heat_index ?? null);
    sensorChart.update();
  } catch (err) {
    console.warn("chart update failed", err);
  }
}

// Download CSV (client-side)
async function downloadHistoryCSV() {
  try {
    const res = await fetch("/history");
    if (!res.ok) throw new Error("No history to download");
    const hist = await res.json();
    // build CSV
    const header = ["time","temperature","humidity","soil","soil_status","heat_index"];
    const rows = hist.map(r => [
      r.time ?? '',
      r.temperature ?? '',
      r.humidity ?? '',
      r.soil ?? '',
      r.soil_status ?? '',
      r.heat_index ?? ''
    ]);
    const csvContent = [header, ...rows].map(e => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const now = new Date().toISOString().slice(0,10);
    a.download = `sensor_history_${now}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.warn("Download failed", err);
    alert("Failed to download history. Try again.");
  }
}

// wire download button
downloadBtn.addEventListener('click', downloadHistoryCSV);

// start loops
fetchRecommend();
updateChart();
setInterval(fetchRecommend, 3000);
setInterval(updateChart, 5000);
