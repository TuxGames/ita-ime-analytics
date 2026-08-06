// Comportamentos globais (sem inline scripts — CSP script-src 'self')
(function () {
  "use strict";

  // Confirmação antes de submits destrutivos: <form data-confirm="mensagem">
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Selects que aplicam filtro ao mudar: <select data-autosubmit>
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () {
      select.form.submit();
    });
  });
})();
