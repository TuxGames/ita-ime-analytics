"""Tela de Oficiais: a colocação aparece uma vez só.

A colocação nacional vinha duas vezes — num número gigante dentro da superfície
escura e, logo abaixo, no card de resultados do usuário. Sobrou o card, que tem
espaço para dizer que aquilo é posição entre todos os candidatos e não dentro
do colégio.
"""

import json
import re

from app.models import ResultadoLinha
from app.oficiais_import import aplicar, parse

from .conftest import payload_oficial


def _importar(db, admin, turma="novata"):
    aplicar(db, parse(json.dumps(payload_oficial(turma))), admin.id)
    db.session.commit()


def _virar_meu(db, usuario, classificacao=None):
    """Vincula ao usuário uma linha classificada do listão.

    Por padrão pega a PIOR colocação, não a melhor: o card do listão mostra
    "melhor #N" do colégio inteiro, e se a minha coincidisse com ela o teste de
    duplicação não saberia distinguir os dois números.
    """
    query = db.select(ResultadoLinha).filter(ResultadoLinha.status == "classificado")
    if classificacao is not None:
        query = query.filter(ResultadoLinha.classificacao == classificacao)
    linha = db.session.scalars(
        query.order_by(ResultadoLinha.classificacao.desc())
    ).first()
    linha.user_id = usuario.id
    db.session.commit()
    return linha


def test_colocacao_aparece_uma_vez_so(client, db, admin, logar):
    _importar(db, admin)
    _importar(db, admin, "veterana")
    linha = _virar_meu(db, admin)  # a pior, para não colidir com "melhor #N"
    logar(admin)

    corpo = client.get("/oficiais/").get_data(as_text=True)

    ocorrencias = len(re.findall(rf"\b{linha.classificacao}\b", corpo))
    assert ocorrencias == 1, f"a colocação {linha.classificacao} apareceu {ocorrencias}x"


def test_board_nao_tem_mais_celula_de_colocacao(client, db, admin, logar):
    _importar(db, admin)
    _virar_meu(db, admin)
    logar(admin)

    corpo = client.get("/oficiais/").get_data(as_text=True)
    board = corpo.split('<section class="board"')[1].split("</section>")[0]

    assert "board-cell" not in board


def test_card_diz_que_a_posicao_e_nacional(client, db, admin, logar):
    """O critério da escolha: o que sobrou tem que deixar claro o que é."""
    _importar(db, admin)
    linha = _virar_meu(db, admin)
    logar(admin)

    corpo = client.get("/oficiais/").get_data(as_text=True)

    assert "Sua colocação nacional" in corpo
    assert "não é a sua posição dentro do colégio" in corpo
    assert f"#{linha.classificacao}" in corpo


def test_sem_vinculo_a_tela_segue_de_pe(client, db, admin, logar):
    """Sem linha vinculada não há card nenhum — e a tela não pode quebrar."""
    _importar(db, admin)
    logar(admin)

    resposta = client.get("/oficiais/")

    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Sua colocação nacional" not in corpo
    assert "board-cell" not in corpo
