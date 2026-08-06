// Gráfico de questões por matéria na semana. Dados via <script id="estudo-data">.
(function () {
  "use strict";

  var el = document.getElementById("estudo-data");
  var canvas = document.getElementById("chart-estudo");
  if (!el || !canvas || typeof Chart === "undefined") return;

  var dados = JSON.parse(el.textContent);
  if (!dados.length) return;

  Chart.defaults.font.family =
    '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif';
  Chart.defaults.color = "#5B6470";

  new Chart(canvas, {
    type: "bar",
    data: {
      labels: dados.map(function (d) { return d.materia; }),
      datasets: [
        { label: "Questões", data: dados.map(function (d) { return d.questoes; }), backgroundColor: "#1D3557" },
        { label: "Acertos", data: dados.map(function (d) { return d.acertos; }), backgroundColor: "#8DA9C4" }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, boxHeight: 12, padding: 10, usePointStyle: true } },
        tooltip: { backgroundColor: "#1D3557", padding: 10 }
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: false } },
        y: { beginAtZero: true, ticks: { maxTicksLimit: 6, precision: 0 }, grid: { color: "#EDF0F4" } }
      }
    }
  });
})();
