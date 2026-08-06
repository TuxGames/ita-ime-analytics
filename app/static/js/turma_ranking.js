// Ranking da turma com recorte de matérias.
// Reordena as linhas que o servidor já renderizou (não recria o HTML), então os
// botões "sou eu" e os chips continuam intactos a cada mudança.
(function () {
  "use strict";

  var bruto = document.getElementById("turma-data");
  var lista = document.getElementById("ranking-lista");
  var caixa = document.getElementById("recorte-checks");
  if (!bruto || !lista || !caixa) return;

  var dados = JSON.parse(bruto.textContent);
  var questoes = dados.questoes || {};
  var selecionadas = carregarSelecao();

  // ---------- Persistência da escolha ----------
  function carregarSelecao() {
    var salvo = null;
    try { salvo = localStorage.getItem(dados.chave); } catch (e) { salvo = null; }
    if (salvo) {
      var nomes = salvo.split(",").filter(function (n) {
        return dados.materias.some(function (m) { return m.name === n; });
      });
      if (nomes.length) return nomes;
    }
    return (dados.padrao || []).slice();
  }

  function salvarSelecao() {
    try { localStorage.setItem(dados.chave, selecionadas.join(",")); } catch (e) { /* ok */ }
  }

  // ---------- Cálculo ----------
  // Nota = média dos percentuais das matérias marcadas, em escala 0–10.
  // Peso igual entre matérias (regra da 1ª fase do IME; no ITA, com 12 questões
  // em tudo, dá exatamente a MÉDIA do colégio).
  function nota(acertos) {
    var soma = 0, n = 0;
    for (var i = 0; i < selecionadas.length; i++) {
      var nome = selecionadas[i];
      var total = questoes[nome];
      var certas = acertos[nome];
      if (total && certas !== undefined && certas !== null) {
        soma += certas / total;
        n += 1;
      }
    }
    return n ? Math.round((10 * soma / n) * 100) / 100 : null;
  }

  function ranquear() {
    var pares = [];
    dados.linhas.forEach(function (linha) {
      var valor = nota(linha.acertos);
      if (valor !== null) pares.push({ linha: linha, nota: valor });
    });
    pares.sort(function (a, b) { return b.nota - a.nota; });

    var anterior = null, posicao = 0;
    pares.forEach(function (par, indice) {
      if (par.nota !== anterior) { posicao = indice + 1; anterior = par.nota; }
      par.posicao = posicao;
    });
    return pares;
  }

  // ---------- Render ----------
  function fmt(valor) {
    return valor.toFixed(2);
  }

  function aplicar() {
    var pares = ranquear();
    var fragmento = document.createDocumentFragment();
    var minha = null, soma = 0;

    pares.forEach(function (par) {
      var el = lista.querySelector('[data-id="' + par.linha.id + '"]');
      if (!el) return;
      var posEl = el.querySelector(".of-linha-pos");
      var notaEl = el.querySelector(".of-linha-mp");
      if (posEl) posEl.textContent = par.posicao + "º";
      if (notaEl) notaEl.textContent = fmt(par.nota);
      fragmento.appendChild(el); // mover o nó já existente = reordenar
      soma += par.nota;
      if (par.linha.eu) minha = par;
    });
    lista.appendChild(fragmento);

    var posMinha = document.getElementById("minha-pos");
    if (posMinha) {
      posMinha.textContent = minha ? minha.posicao + "º" : "—";
      document.getElementById("minha-nota").textContent = minha ? fmt(minha.nota) : "—";
      document.getElementById("media-turma").textContent =
        pares.length ? fmt(soma / pares.length) : "—";
    }

    var resumo = document.getElementById("recorte-resumo");
    if (resumo) {
      var rotulos = dados.materias
        .filter(function (m) { return selecionadas.indexOf(m.name) !== -1; })
        .map(function (m) { return m.label; });
      resumo.textContent = rotulos.length ? rotulos.join(" + ") : "nenhuma matéria";
    }
    salvarSelecao();
  }

  // ---------- Checkboxes ----------
  dados.materias.forEach(function (materia) {
    var id = "rec-" + materia.name;
    var label = document.createElement("label");
    label.className = "recorte-opt";
    var input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    input.value = materia.name;
    input.checked = selecionadas.indexOf(materia.name) !== -1;
    input.addEventListener("change", function () {
      selecionadas = [].slice
        .call(caixa.querySelectorAll("input:checked"))
        .map(function (i) { return i.value; });
      aplicar();
    });
    var texto = document.createElement("span");
    texto.textContent = materia.label + " (" + (questoes[materia.name] || "?") + "q)";
    label.appendChild(input);
    label.appendChild(texto);
    caixa.appendChild(label);
  });

  function marcar(nomes) {
    selecionadas = nomes.slice();
    [].forEach.call(caixa.querySelectorAll("input"), function (input) {
      input.checked = selecionadas.indexOf(input.value) !== -1;
    });
    aplicar();
  }

  // ---------- Atalhos ----------
  [].forEach.call(document.querySelectorAll("[data-preset]"), function (botao) {
    botao.addEventListener("click", function () {
      if (botao.dataset.preset === "oficial") {
        marcar(dados.padrao || []);
      } else {
        marcar(dados.materias.map(function (m) { return m.name; }));
      }
    });
  });

  var seletor = document.getElementById("preset-concurso");
  if (seletor) {
    Object.keys(dados.porConcurso || {}).forEach(function (nome) {
      var opcao = document.createElement("option");
      opcao.value = nome;
      opcao.textContent = nome;
      seletor.appendChild(opcao);
    });
    seletor.addEventListener("change", function () {
      var nomes = dados.porConcurso[seletor.value];
      if (nomes) marcar(nomes);
      seletor.value = "";
    });
  }

  aplicar();
})();
