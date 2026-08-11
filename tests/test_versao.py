"""Versão visível do app."""

import re

from app.versao import VERSAO


def test_formato_da_versao():
    """`x.y.NN` — o terceiro componente tem SEMPRE dois dígitos."""
    assert re.fullmatch(r"\d+\.\d+\.\d{2}", VERSAO), f"esperado x.y.NN, veio {VERSAO!r}"


def test_correcao_ordena_como_texto():
    """O zero à esquerda existe para a versão ordenar certo como string.

    Sem ele, "2.3.2" > "2.3.18" alfabeticamente, e é assim que versão acaba
    sendo comparada em nome de arquivo, log e listagem.
    """
    maior, menor, _ = VERSAO.split(".")
    versoes = [f"{maior}.{menor}.{n:02d}" for n in (0, 2, 9, 10, 18, 99)]

    assert sorted(versoes) == versoes, "ordenação alfabética tem que bater com a numérica"


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
