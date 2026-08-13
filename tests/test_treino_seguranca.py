"""Guardas do treino: não perder trabalho por um clique.

O treino roda no navegador, então estes testes são estáticos — leem o CSS e o
JS e verificam invariantes. Não substituem a conferência no navegador (feita a
cada mexida), mas impedem que alguém desfaça sem perceber o que custou horas de
estudo de alguém.
"""

import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CSS = (RAIZ / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
JS = (RAIZ / "app" / "static" / "js" / "treino.js").read_text(encoding="utf-8")
HTML = (RAIZ / "app" / "templates" / "estudos" / "treino.html").read_text(encoding="utf-8")


def test_hidden_vence_qualquer_display():
    """A causa do bug: `.btn-block { display: flex }` derrotava o `hidden` do
    navegador, e "Iniciar sessão" ficava visível durante o treino, colado no
    "Registrar questão" — um clique trocado apagava tudo."""
    assert "[hidden] { display: none !important; }" in CSS


def test_botao_iniciar_e_escondido_durante_a_sessao():
    assert '$("btn-iniciar").hidden = true;' in JS


def test_descartar_pede_confirmacao():
    """"Começar outro" apaga o treino retomável: tem que perguntar."""
    trecho = JS[JS.index("function descartar()"):]
    trecho = trecho[: trecho.index("\n  }")]
    assert "window.confirm(" in trecho


def test_confirmacao_nao_usa_handler_inline():
    """A CSP é 'self' e bloqueia `onsubmit`/`onclick` embutido — já tivemos um
    botão de apagar que não confirmava nada por causa disso. `confirm()` de
    arquivo externo passa; handler inline não."""
    for arquivo, texto in (("treino.html", HTML), ("treino.js", JS)):
        assert "onsubmit=" not in texto, arquivo
        assert "onclick=" not in texto, arquivo


def test_mudar_tempo_padrao_nao_apaga_sessao():
    """Trocar uma preferência não pode destruir trabalho: antes caía direto em
    novaSessao(), que zera tudo."""
    trecho = JS[JS.index("function salvarPadrao()"):]
    trecho = trecho[: trecho.index("\n  function ")]
    assert 'if (estado === "idle" && feitas === 0)' in trecho, (
        "novaSessao() só pode ser chamada quando não há sessão em andamento"
    )


# --------------------------------------------------------------------------
# A retomada de 2.4.04 não pode regredir
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "trecho",
    [
        'document.addEventListener("visibilitychange"',
        'window.addEventListener("pagehide", salvarSessao)',
        "function salvarSessao()",
        "function lerSessao()",
        "function limparSessao()",
    ],
)
def test_persistencia_do_treino_continua_de_pe(trecho):
    assert trecho in JS


def test_retomada_volta_pausada():
    """Contar o tempo em que o navegador esteve fechado seria inventar dado."""
    trecho = JS[JS.index("function retomar()"):]
    trecho = trecho[: trecho.index("\n  function ")]
    assert 'estado = "paused"' in trecho


def test_beforeunload_continua_fora():
    """No celular ele frequentemente não dispara — o que vale é
    visibilitychange/pagehide."""
    linhas_de_codigo = [
        linha for linha in JS.splitlines()
        if "beforeunload" in linha and not linha.strip().startswith("//")
    ]
    assert not linhas_de_codigo, linhas_de_codigo


def test_sessao_limpa_ao_concluir():
    """Treino concluído não pode ressuscitar na próxima visita."""
    trecho = JS[JS.index("function finalizar()"):]
    trecho = trecho[: trecho.index("\n  function ")]
    assert "limparSessao()" in trecho
