"""Versão visível do app."""

import re

from app.versao import VERSAO


def test_formato_da_versao():
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", VERSAO), "esperado 'maior.menor' ou 'maior.menor.correcao'"


def test_constante_e_unica():
    """Um lugar só. Se alguém escrever a versão à mão num template, a próxima
    subida esquece esse pedaço e a tela passa a mentir."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parent.parent
    achados = []
    for caminho in list((raiz / "app").rglob("*.html")) + list((raiz / "app").rglob("*.py")):
        if caminho.name == "versao.py":
            continue
        texto = caminho.read_text(encoding="utf-8")
        if re.search(rf"\bv?{re.escape(VERSAO)}\b", texto):
            achados.append(str(caminho.relative_to(raiz)))
    assert not achados, f"versão escrita à mão em: {achados}"


def test_rodape_mostra_a_versao(client, usuario, logar):
    logar(usuario)

    corpo = client.get("/").get_data(as_text=True)

    assert f"v{VERSAO}" in corpo
    assert 'class="rodape"' in corpo


def test_perfil_mostra_a_versao(client, usuario, logar):
    logar(usuario)

    corpo = client.get("/perfil").get_data(as_text=True)

    assert f"Versão {VERSAO}" in corpo


def test_rodape_aparece_tambem_deslogado(client):
    """O rodapé vive no base.html, então vale para a tela de login também."""
    corpo = client.get("/login").get_data(as_text=True)

    assert f"v{VERSAO}" in corpo
