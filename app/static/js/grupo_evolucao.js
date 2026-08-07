// Gráfico de evolução do grupo (Bloco 2): questões por dia, uma linha por
// membro ativo. Nunca lê nada de tempo — o JSON que chega já não tem esse
// campo (ver app/grupo_evolucao.py).
(function () {
  "use strict";

  var dataEl = document.getElementById("grupo-evolucao-data");
  var el = document.getElementById("chart-grupo-questoes");
  if (!dataEl || !el || typeof Chart === "undefined") return;

  var data = JSON.parse(dataEl.textContent);
  var PALETA = ["#1D3557", "#B91C30", "#2A9D8F", "#8E44AD", "#E67E22", "#3E6390"];

  Chart.defaults.font.family =
    '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.color = "#5B6470";

  // Cada membro pode ter dias diferentes com registro; junta tudo num eixo só.
  var todosOsDias = [];
  data.membros.forEach(function (m) {
    m.labels.forEach(function (d) {
      if (todosOsDias.indexOf(d) === -1) todosOsDias.push(d);
    });
  });
  todosOsDias.sort();

  var datasets = data.membros.map(function (m, i) {
    var porDia = {};
    m.labels.forEach(function (d, idx) { porDia[d] = m.questoes_por_dia[idx]; });
    return {
      label: m.username,
      data: todosOsDias.map(function (d) { return porDia[d] !== undefined ? porDia[d] : null; }),
      borderColor: PALETA[i % PALETA.length],
      backgroundColor: PALETA[i % PALETA.length],
      spanGaps: true,
      tension: 0.25,
    };
  });

  new Chart(el, {
    type: "line",
    data: { labels: todosOsDias, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, boxHeight: 12, padding: 10, usePointStyle: true } },
        tooltip: { backgroundColor: "#1D3557", padding: 10 },
      },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#EDF0F4" } },
      },
    },
  });
})();
