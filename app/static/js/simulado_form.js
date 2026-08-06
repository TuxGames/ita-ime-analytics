// Form de simulado: dois selects dependentes (banca -> fase/dia) e as matérias
// que caem na fase escolhida. Sem inline (CSP script-src 'self').
(function () {
  "use strict";

  var banca = document.getElementById("banca-sel");
  var etapa = document.getElementById("concurso_id");
  var mapEl = document.getElementById("materias-map");
  if (!banca || !etapa) return;

  var materias = mapEl ? JSON.parse(mapEl.textContent) : {};
  var opcoes = Array.prototype.slice.call(etapa.options);

  // Mostra no select "fase/dia" só as etapas da banca escolhida.
  function filtrarEtapas(mantemSelecao) {
    var b = banca.value;
    var atual = etapa.value;
    var primeiraVisivel = null;
    opcoes.forEach(function (op) {
      var pertence = op.getAttribute("data-banca") === b;
      op.hidden = !pertence;
      op.disabled = !pertence;
      if (pertence && primeiraVisivel === null) primeiraVisivel = op.value;
    });
    // se a seleção atual não é mais da banca, cai na primeira etapa visível
    var atualPertence = opcoes.some(function (op) {
      return op.value === atual && !op.hidden;
    });
    if (!(mantemSelecao && atualPertence)) {
      etapa.value = primeiraVisivel;
    }
  }

  // Mostra só as matérias que caem na etapa selecionada.
  function filtrarMaterias() {
    var permitidas = materias[etapa.value] || [];
    var set = Object.create(null);
    permitidas.forEach(function (n) {
      set[n] = true;
    });
    document.querySelectorAll("[data-materia]").forEach(function (el) {
      var mostra = !!set[el.getAttribute("data-materia")];
      el.style.display = mostra ? "" : "none";
      if (!mostra) {
        el.querySelectorAll("input").forEach(function (input) {
          input.value = "";
        });
      }
    });
    atualizarMedia();
  }

  // ---- Nota geral: modo automático x manual + preview da média ----
  var manualBox = document.getElementById("nota-manual");
  var autoBox = document.getElementById("nota-auto");
  var mediaPreview = document.getElementById("media-preview");
  var radios = document.querySelectorAll('input[name="modo_nota"]');

  function modoAtual() {
    var sel = document.querySelector('input[name="modo_nota"]:checked');
    return sel ? sel.value : "manual";
  }

  // Média simples dos % de acertos das matérias visíveis e preenchidas.
  function atualizarMedia() {
    if (!mediaPreview) return;
    var somaPerc = 0;
    var n = 0;
    document.querySelectorAll("label.mg-label").forEach(function (label) {
      if (label.style.display === "none") return; // matéria não cai no concurso
      var nome = label.getAttribute("data-materia");
      var ac = document.getElementById(nome.toLowerCase() + "-acertos");
      var tot = document.getElementById(nome.toLowerCase() + "-total_questoes");
      if (!ac || !tot || ac.value === "" || tot.value === "") return;
      var a = parseFloat(ac.value);
      var t = parseFloat(tot.value);
      if (isNaN(a) || isNaN(t) || t <= 0) return;
      somaPerc += (100 * a) / t;
      n += 1;
    });
    mediaPreview.textContent = n ? (somaPerc / n).toFixed(1) + "%" : "—";
  }

  function aplicarModo() {
    var auto = modoAtual() === "auto";
    if (manualBox) manualBox.style.display = auto ? "none" : "";
    if (autoBox) autoBox.style.display = auto ? "" : "none";
    if (auto) atualizarMedia();
  }

  radios.forEach(function (r) {
    r.addEventListener("change", aplicarModo);
  });
  // Recalcula a média ao mexer em qualquer campo de acertos/total
  document.querySelectorAll(".materias-grid input").forEach(function (inp) {
    inp.addEventListener("input", atualizarMedia);
  });

  banca.addEventListener("change", function () {
    filtrarEtapas(false);
    filtrarMaterias();
  });
  etapa.addEventListener("change", filtrarMaterias);

  // Estado inicial: se há concurso pré-selecionado (edição/atalho), casa a banca
  // com ele; senão usa a primeira banca da lista.
  var selecionado = etapa.getAttribute("data-selected");
  if (selecionado) {
    var op = opcoes.filter(function (o) {
      return o.value === selecionado;
    })[0];
    if (op) {
      banca.value = op.getAttribute("data-banca");
      filtrarEtapas(false);
      etapa.value = selecionado;
    } else {
      filtrarEtapas(false);
    }
  } else {
    filtrarEtapas(false);
  }
  filtrarMaterias();
  aplicarModo();
})();
