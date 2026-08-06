// Botão "Copiar prompt" da página de importação (só isso).
(function () {
  "use strict";

  var botao = document.getElementById("copiar-prompt");
  var pre = document.getElementById("prompt-texto");
  if (!botao || !pre) return;

  botao.addEventListener("click", function () {
    var texto = pre.textContent;
    var aviso = function (msg) {
      botao.textContent = msg;
      setTimeout(function () { botao.textContent = "Copiar prompt"; }, 1800);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(
        function () { aviso("Copiado!"); },
        function () { aviso("Copie manualmente"); }
      );
      return;
    }
    // Fallback para navegadores sem Clipboard API (ou fora de HTTPS).
    var area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      aviso(document.execCommand("copy") ? "Copiado!" : "Copie manualmente");
    } catch (e) {
      aviso("Copie manualmente");
    }
    document.body.removeChild(area);
  });
})();
