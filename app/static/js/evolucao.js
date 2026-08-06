// Gráficos da evolução (Fase E). Dados vêm de <script id="evolucao-data">.
// Mesmo estilo visual do dashboard.js (cores, opções base).
(function () {
  "use strict";

  var dataEl = document.getElementById("evolucao-data");
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
        tooltip: { backgroundColor: "#1D3557", padding: 10, titleFont: { size: 12 }, bodyFont: { size: 12 } }
      },
      scales: {
        x: { ticks: { maxTicksLimit: mobile ? 5 : 9, maxRotation: 0 }, grid: { display: false } },
        y: { ticks: { maxTicksLimit: 6 }, grid: { color: "#EDF0F4" }, title: yTitle ? { display: !mobile, text: yTitle } : undefined }
      }
    };
  }

  // 1) Percentil na turma, com tendência
  var elPercentil = document.getElementById("chart-percentil");
  if (elPercentil) {
    var datasets = [
      {
        label: "Percentil",
        data: data.percentil.values,
        borderColor: AZUL,
        backgroundColor: "rgba(29, 53, 87, 0.08)",
        fill: true,
        spanGaps: true,
        tension: 0.25,
        pointRadius: 4,
        pointHoverRadius: 7
      }
    ];
    if (data.percentil.tendencia) {
      datasets.push({
        label: "Tendência",
        data: data.percentil.tendencia.valores,
        borderColor: AZUL_CLARO,
        backgroundColor: AZUL_CLARO,
        borderDash: [6, 5],
        pointRadius: 0,
        pointHoverRadius: 0
      });
    }
    new Chart(elPercentil, {
      type: "line",
      data: { labels: data.labels, datasets: datasets },
      options: (function (o) {
        o.scales.y.min = 0;
        o.scales.y.max = 100;
        return o;
      })(baseOptions("Percentil"))
    });
  }

  // 2) Acertos por matéria, com checkboxes
  var nomesMateria = Object.keys(data.materias);
  var elMaterias = document.getElementById("chart-materias");
  if (elMaterias && nomesMateria.length) {
    var chartMaterias = new Chart(elMaterias, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: nomesMateria.map(function (nome, i) {
          var serie = data.materias[nome];
          return {
            label: serie.label,
            data: serie.valores,
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
        o.plugins.legend.display = false;
        return o;
      })(baseOptions("% acertos"))
    });

    var box = document.getElementById("materia-checks");
    if (box) {
      chartMaterias.data.datasets.forEach(function (ds, i) {
        var wrap = document.createElement("label");
        wrap.className = "check-chip";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
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

  // 3) Você x mediana da turma, uma matéria por vez (select)
  var seletor = document.getElementById("materia-comparacao");
  var elComp = document.getElementById("chart-comparacao");
  if (seletor && elComp && nomesMateria.length) {
    nomesMateria.forEach(function (nome) {
      var opcao = document.createElement("option");
      opcao.value = nome;
      opcao.textContent = data.materias[nome].label;
      seletor.appendChild(opcao);
    });

    var chartComp = new Chart(elComp, {
      type: "line",
      data: { labels: data.labels, datasets: [] },
      options: (function (o) {
        o.scales.y.min = 0;
        o.scales.y.max = 100;
        return o;
      })(baseOptions("% acertos"))
    });

    function render(nome) {
      var serie = data.materias[nome];
      chartComp.data.datasets = [
        {
          label: "Você",
          data: serie.valores,
          borderColor: AZUL,
          backgroundColor: AZUL,
          spanGaps: true,
          tension: 0.25,
          pointRadius: 4,
          pointHoverRadius: 7
        },
        {
          label: "Mediana da turma",
          data: serie.mediana_turma,
          borderColor: "#8E44AD",
          backgroundColor: "#8E44AD",
          borderDash: [6, 5],
          spanGaps: true,
          pointRadius: 0,
          pointHoverRadius: 0
        }
      ];
      chartComp.update();
    }

    seletor.addEventListener("change", function () {
      render(seletor.value);
    });
    seletor.value = nomesMateria[0];
    render(nomesMateria[0]);
  }
})();
