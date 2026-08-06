// Treino de questões: cronômetro com tempo cumulativo (rollover) entre questões.
// Tudo client-side. Tempo padrão no localStorage; sons via Web Audio (CSP-safe).
(function () {
  "use strict";

  var KEY = "itaime_treino_seg"; // tempo padrão por questão, em segundos
  var $ = function (id) { return document.getElementById(id); };

  var setupBox = $("treino-setup");
  var mainBox = $("treino-main");
  var resumoBox = $("treino-resumo");
  if (!setupBox || !mainBox) return;

  // ---------- Estado ----------
  var defaultSec = 300; // 5 min (sobrescrito pelo localStorage)
  var estado = "idle";  // idle | running | paused
  var budgetSec = 300;  // tempo permitido para a questão atual (default + sobra)
  var accumMs = 0;      // tempo já decorrido na questão atual (segmentos pausados)
  var segStart = 0;     // início do segmento em andamento (Date.now)
  var feitas = 0;
  var totalMs = 0;      // soma do tempo das questões já registradas
  var alerted = false;  // já tocou o alerta de "acabou o tempo" nesta questão?
  var mute = false;
  var tickTimer = null;

  // ---------- Áudio (Web Audio, sem arquivos) ----------
  var actx = null;
  function ctx() {
    if (!actx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) actx = new AC();
    }
    return actx;
  }
  function beep(freq, durMs, type) {
    if (mute) return;
    var c = ctx();
    if (!c) return;
    var o = c.createOscillator();
    var g = c.createGain();
    o.type = type || "sine";
    o.frequency.value = freq;
    o.connect(g);
    g.connect(c.destination);
    var t = c.currentTime;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.3, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + durMs / 1000);
    o.start(t);
    o.stop(t + durMs / 1000);
  }
  function somSucesso() {
    beep(880, 120, "sine");
    setTimeout(function () { beep(1175, 160, "sine"); }, 130);
  }
  function somAlerta() {
    beep(300, 450, "square");
  }

  // ---------- Formatação ----------
  function fmt(sec) {
    var neg = sec < 0;
    var s = Math.abs(Math.round(sec));
    var m = Math.floor(s / 60);
    var ss = s % 60;
    return (neg ? "-" : "") + (m < 10 ? "0" : "") + m + ":" + (ss < 10 ? "0" : "") + ss;
  }

  function elapsedSec() {
    var extra = estado === "running" ? Date.now() - segStart : 0;
    return (accumMs + extra) / 1000;
  }

  // ---------- Render ----------
  function render() {
    var el = elapsedSec();
    var remaining = budgetSec - el;
    var remEl = $("remaining");
    remEl.textContent = fmt(remaining);
    remEl.classList.toggle("treino-over", remaining < 0);

    $("budget-atual").textContent = fmt(budgetSec);
    $("tempo-total").textContent = fmt((totalMs + accumMs + (estado === "running" ? Date.now() - segStart : 0)) / 1000);

    if (remaining <= 0 && !alerted && estado === "running") {
      alerted = true;
      somAlerta();
    }
  }

  function startTick() {
    stopTick();
    tickTimer = setInterval(render, 200);
  }
  function stopTick() {
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null; }
  }

  // ---------- Ações ----------
  function iniciar() {
    if (ctx()) ctx().resume(); // desbloqueia o áudio dentro do gesto do usuário
    budgetSec = defaultSec;
    accumMs = 0;
    segStart = Date.now();
    estado = "running";
    feitas = 0;
    totalMs = 0;
    alerted = false;
    $("feitas").textContent = "0";
    $("questao-info").textContent = "Questão 1";
    $("btn-iniciar").hidden = true;
    $("btn-registrar").hidden = false;
    $("row-secundario").hidden = false;
    setPausarLabel();
    startTick();
    render();
  }

  function registrar() {
    if (estado === "idle") return;
    // congela o tempo desta questão
    if (estado === "running") {
      accumMs += Date.now() - segStart;
    }
    var elSec = accumMs / 1000;
    var dentroDoPrazo = elSec <= budgetSec;
    if (dentroDoPrazo) somSucesso();

    var sobra = budgetSec - elSec; // pode ser negativa (passou do tempo)
    totalMs += accumMs;
    feitas += 1;

    // próxima questão: tempo padrão + sobra (desconta se foi negativa)
    budgetSec = defaultSec + sobra;
    accumMs = 0;
    segStart = Date.now();
    estado = "running";
    alerted = false;
    $("feitas").textContent = String(feitas);
    $("questao-info").textContent = "Questão " + (feitas + 1);
    setPausarLabel();
    render();
  }

  function pausar() {
    if (estado === "running") {
      accumMs += Date.now() - segStart;
      estado = "paused";
    } else if (estado === "paused") {
      segStart = Date.now();
      estado = "running";
    }
    setPausarLabel();
    render();
  }
  function setPausarLabel() {
    $("btn-pausar").textContent = estado === "paused" ? "Retomar" : "Pausar";
  }

  function finalizar() {
    // A questão em andamento (não registrada) é descartada: o total e a média
    // consideram só as questões efetivamente registradas.
    estado = "idle";
    stopTick();
    var totalSec = Math.round(totalMs / 1000);
    $("res-feitas").textContent = String(feitas);
    $("res-total").textContent = fmt(totalSec);
    $("res-media").textContent = feitas ? fmt(totalSec / feitas) : "—";

    // Preenche os campos ocultos do formulário de salvar (só se houve questões).
    var salvarForm = $("treino-salvar-form");
    if (salvarForm) {
      var podeSalvar = feitas > 0;
      salvarForm.hidden = !podeSalvar;
      if (podeSalvar) {
        $("save-questoes").value = String(feitas);
        $("save-total").value = String(totalSec);
        $("save-padrao").value = String(defaultSec);
      }
    }

    mainBox.hidden = true;
    resumoBox.hidden = false;
  }

  function novaSessao() {
    resumoBox.hidden = true;
    mainBox.hidden = false;
    estado = "idle";
    accumMs = 0;
    budgetSec = defaultSec;
    $("btn-iniciar").hidden = false;
    $("btn-registrar").hidden = true;
    $("row-secundario").hidden = true;
    $("feitas").textContent = "0";
    $("questao-info").textContent = "Pronto para começar";
    $("remaining").textContent = fmt(defaultSec);
    $("remaining").classList.remove("treino-over");
    $("budget-atual").textContent = fmt(defaultSec);
    $("tempo-total").textContent = "00:00";
  }

  // ---------- Tempo padrão (setup) ----------
  function mostrarSetup(prefill) {
    if (prefill) {
      $("setup-min").value = Math.floor(defaultSec / 60);
      $("setup-seg").value = defaultSec % 60;
    }
    mainBox.hidden = true;
    resumoBox.hidden = true;
    setupBox.hidden = false;
  }

  function salvarPadrao() {
    var m = parseInt($("setup-min").value, 10) || 0;
    var s = parseInt($("setup-seg").value, 10) || 0;
    var total = m * 60 + s;
    if (total < 5) total = 5; // mínimo de 5s para evitar zero
    defaultSec = total;
    try { localStorage.setItem(KEY, String(total)); } catch (e) { /* modo privado */ }
    setupBox.hidden = true;
    novaSessao();
    $("padrao-label").textContent = fmt(defaultSec);
  }

  function toggleMute() {
    mute = !mute;
    var b = $("btn-mute");
    b.textContent = mute ? "🔇 Som desligado" : "🔊 Som ligado";
    b.setAttribute("aria-pressed", mute ? "true" : "false");
  }

  // ---------- Ligações ----------
  $("setup-salvar").addEventListener("click", salvarPadrao);
  $("mudar-padrao").addEventListener("click", function () { mostrarSetup(true); });
  $("btn-iniciar").addEventListener("click", iniciar);
  $("btn-registrar").addEventListener("click", registrar);
  $("btn-pausar").addEventListener("click", pausar);
  $("btn-finalizar").addEventListener("click", finalizar);
  $("btn-nova").addEventListener("click", novaSessao);
  $("btn-mute").addEventListener("click", toggleMute);

  // ---------- Início ----------
  var salvo = null;
  try { salvo = localStorage.getItem(KEY); } catch (e) { salvo = null; }
  if (salvo && parseInt(salvo, 10) > 0) {
    defaultSec = parseInt(salvo, 10);
    $("padrao-label").textContent = fmt(defaultSec);
    novaSessao(); // mostra o painel principal, estado ocioso
  } else {
    mostrarSetup(false); // primeira vez: pede o tempo padrão
  }
})();
