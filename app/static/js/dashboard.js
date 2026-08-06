// Gráficos do dashboard. Dados vêm do <script type="application/json" id="chart-data">.
(function () {
  "use strict";

  var dataEl = document.getElementById("chart-data");
  if (!dataEl || typeof Chart === "undefined") return;

  var data = JSON.parse(dataEl.textContent);

  var AZUL = "#1D3557";
  var AZUL_CLARO = "#8DA9C4";
  var PALETA_MATERIAS = ["#1D3557", "#3E6390", "#2A9D8F", "#8E44AD", "#E67E22", "#B91C30"];

  Chart.defaults.font.family =
    '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.color = "#5B6470";

  var mobile = window.innerWidth < 480;

  // Opções pensadas para tela pequena: poucos ticks, tooltip acionável por toque
  function baseOptions(yTitle) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, boxHeight: 12, padding: 10, usePointStyle: true }
        },
        tooltip: {
          backgroundColor: "#1D3557",
          padding: 10,
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          displayColors: true
        }
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: mobile ? 5 : 9, maxRotation: 0 },
          grid: { display: false }
        },
        y: {
          ticks: { maxTicksLimit: 6 },
          grid: { color: "#EDF0F4" },
          title: yTitle ? { display: !mobile, text: yTitle } : undefined
        }
      }
    };
  }

  // 0) Evolução da posição (só se houver posições). Eixo Y invertido: posição
  // menor (melhor) fica mais em cima.
  var elPos = document.getElementById("chart-posicao");
  if (elPos && data.posicao) {
    new Chart(elPos, {
      type: "line",
      data: {
        labels: data.posicao.labels,
        datasets: [
          {
            label: "Posição",
            data: data.posicao.values,
            borderColor: "#B91C30",
            backgroundColor: "rgba(185, 28, 48, 0.08)",
            fill: true,
            tension: 0.25,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointBackgroundColor: "#B91C30"
          }
        ]
      },
      options: (function (o) {
        o.plugins.legend.display = false;
        o.scales.y.reverse = true;
        o.scales.y.ticks.precision = 0;
        o.plugins.tooltip.callbacks = {
          label: function (ctx) {
            return "Posição: #" + ctx.parsed.y;
          }
        };
        return o;
      })(baseOptions("Posição"))
    });
  }

  // 1) Evolução da nota geral
  var elNotas = document.getElementById("chart-notas");
  if (elNotas) {
    new Chart(elNotas, {
      type: "line",
      data: {
        labels: data.notas.labels,
        datasets: [
          {
            label: "Nota geral",
            data: data.notas.values,
            borderColor: AZUL,
            backgroundColor: "rgba(29, 53, 87, 0.08)",
            fill: true,
            tension: 0.25,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointBackgroundColor: AZUL
          }
        ]
      },
      options: (function (o) {
        o.plugins.legend.display = false;
        return o;
      })(baseOptions("Nota"))
    });
  }

  // 2) Desempenho por matéria (%) — com checkboxes para escolher quais mostrar
  var elMaterias = document.getElementById("chart-materias");
  if (elMaterias && data.materias.datasets.length) {
    var chartMaterias = new Chart(elMaterias, {
      type: "line",
      data: {
        labels: data.materias.labels,
        datasets: data.materias.datasets.map(function (ds, i) {
          return {
            label: ds.label,
            data: ds.data,
            borderColor: PALETA_MATERIAS[i % PALETA_MATERIAS.length],
            backgroundColor: PALETA_MATERIAS[i % PALETA_MATERIAS.length],
            spanGaps: true,
            tension: 0.25,
            pointRadius: 3,
            pointHoverRadius: 6
          };
        })
      },
      options: (function (o) {
        o.scales.y.min = 0;
        o.scales.y.max = 100;
        o.plugins.legend.display = false; // a lista de checkboxes substitui a legenda
        return o;
      })(baseOptions("% acertos"))
    });

    // Checkboxes (uma por matéria) que ligam/desligam cada linha do gráfico.
    var box = document.getElementById("materia-checks");
    if (box) {
      chartMaterias.data.datasets.forEach(function (ds, i) {
        var id = "mat-chk-" + i;
        var wrap = document.createElement("label");
        wrap.className = "check-chip";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.id = id;
        cb.addEventListener("change", function () {
          chartMaterias.setDatasetVisibility(i, cb.checked);
          chartMaterias.update();
        });
        var dot = document.createElement("span");
        dot.className = "check-dot";
        dot.style.background = ds.borderColor;
        var txt = document.createElement("span");
        txt.textContent = ds.label;
        wrap.appendChild(cb);
        wrap.appendChild(dot);
        wrap.appendChild(txt);
        box.appendChild(wrap);
      });
    }
  }

  // 3) Tendência até a prova (projeção linear)
  var elTend = document.getElementById("chart-tendencia");
  if (elTend && data.tendencia) {
    new Chart(elTend, {
      type: "line",
      data: {
        labels: data.tendencia.labels,
        datasets: [
          {
            label: "Nota geral",
            data: data.tendencia.notas,
            borderColor: AZUL,
            backgroundColor: AZUL,
            tension: 0.25,
            pointRadius: 4,
            pointHoverRadius: 7
          },
          {
            label: "Tendência",
            data: data.tendencia.trend,
            borderColor: AZUL_CLARO,
            backgroundColor: AZUL_CLARO,
            borderDash: [6, 5],
            pointRadius: 0,
            pointHoverRadius: 0
          }
        ]
      },
      options: baseOptions("Nota")
    });
  }
})();
