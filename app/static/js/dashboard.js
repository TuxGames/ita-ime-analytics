// Gráfico único do Início, com seletor de métrica (Nota / Posição / Projeção).
// Substitui os quatro gráficos empilhados do modelo anterior.
// Dados vêm do <script type="application/json" id="chart-data"> — mesmo formato
// de antes, montado por app/main/routes.py.
(function () {
  "use strict";

  var dataEl = document.getElementById("chart-data");
  var canvas = document.getElementById("chart-metric");
  if (!dataEl || !canvas || typeof Chart === "undefined") return;

  var data = JSON.parse(dataEl.textContent);
  var AZUL = "#1D3557";
  var VERMELHO = "#B91C30";
  var VERDE = "#166534";

  Chart.defaults.font.family =
    '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.color = "#8B93A0";

  var mobile = window.innerWidth < 480;

  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0C1B2E",
          padding: 10,
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          displayColors: false
        }
      },
      scales: {
        x: { ticks: { maxTicksLimit: mobile ? 5 : 9, maxRotation: 0 }, grid: { display: false } },
        y: { ticks: { maxTicksLimit: 5 }, grid: { color: "#EDF0F4" }, border: { display: false } }
      }
    };
  }

  function linha(label, valores, cor, preenche) {
    return {
      label: label,
      data: valores,
      borderColor: cor,
      backgroundColor: preenche ? "rgba(29, 53, 87, 0.06)" : "transparent",
      fill: !!preenche,
      tension: 0.25,
      pointRadius: 3,
      pointHoverRadius: 7,
      pointBackgroundColor: cor,
      spanGaps: true
    };
  }

  // --- Definição de cada métrica -------------------------------------------

  var metricas = {};

  if (data.notas) {
    var notas = data.notas.values;
    metricas.notas = {
      titulo: notas[notas.length - 1].toFixed(1).replace(".", ",") + "%",
      // Porcentagem de acertos, proporcional às questões. O ranking da turma
      // mostra o MESMO resultado em 0–10, porque reproduz o mural do colégio.
      nota: "Acertos no último simulado, em % do total de questões.",
      build: function () {
        var o = baseOptions();
        o.scales.y.suggestedMin = 0;
        o.scales.y.suggestedMax = 100;
        return {
          type: "line",
          data: { labels: data.notas.labels, datasets: [linha("Nota", notas, AZUL, true)] },
          options: o
        };
      }
    };
  }

  if (data.posicao) {
    var pos = data.posicao.values;
    metricas.posicao = {
      titulo: "#" + pos[pos.length - 1],
      nota: "Posição estimada que você informou. O eixo é invertido: mais acima é melhor colocação.",
      build: function () {
        var o = baseOptions();
        o.scales.y.reverse = true;
        o.scales.y.ticks.precision = 0;
        return {
          type: "line",
          data: { labels: data.posicao.labels, datasets: [linha("Posição", pos, VERMELHO, false)] },
          options: o
        };
      }
    };
  }

  if (data.tendencia) {
    var t = data.tendencia;
    var proj = t.trend[t.trend.length - 1];
    metricas.tendencia = {
      titulo: proj.toFixed(1).replace(".", ","),
      nota: "Projeção linear da sua nota no dia da prova de " + t.alvo + ", mantido o ritmo atual.",
      build: function () {
        var o = baseOptions();
        o.scales.y.suggestedMin = 0;
        o.scales.y.suggestedMax = 100;
        var reta = linha("Projeção", t.trend, VERDE, false);
        reta.borderDash = [6, 5];
        reta.pointRadius = 0;
        return {
          type: "line",
          data: { labels: t.labels, datasets: [linha("Nota", t.notas, AZUL, true), reta] },
          options: o
        };
      }
    };
  }

  // --- Troca de métrica ----------------------------------------------------

  var elValor = document.getElementById("metric-value");
  var elNota = document.getElementById("metric-nota");
  var botoes = Array.prototype.slice.call(document.querySelectorAll("[data-metric]"));
  var grafico = null;

  botoes.forEach(function (b) {
    var chave = b.getAttribute("data-metric");
    if (metricas[chave]) b.hidden = false;
    b.addEventListener("click", function () {
      mostrar(chave);
    });
  });

  function mostrar(chave) {
    var m = metricas[chave];
    if (!m) return;
    botoes.forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-metric") === chave ? "true" : "false");
    });
    if (elValor) elValor.textContent = m.titulo;
    if (elNota) elNota.textContent = m.nota;
    if (grafico) grafico.destroy();
    grafico = new Chart(canvas, m.build());
  }

  mostrar(metricas.notas ? "notas" : Object.keys(metricas)[0]);
})();
