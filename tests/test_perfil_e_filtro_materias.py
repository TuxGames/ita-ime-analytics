"""Fase D: matérias do perfil (D.1) e filtro "mostrar apenas" do ranking (D.2)."""

import json

from app.models import Materia, SimuladoTurma
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from tests.conftest import payload_simulado


def _semear(db, admin):
    aplicar_simulado(db, parse_simulado(json.dumps(payload_simulado())), admin.id)
    db.session.commit()
    return db.session.scalar(db.select(SimuladoTurma))


# --------------------------------------------------------------------------
# D.1 — matérias do perfil
# --------------------------------------------------------------------------


def test_set_materias_grava_e_le_de_volta(app, db, usuario):
    usuario.set_materias([Materia.MATEMATICA, Materia.FISICA])
    db.session.commit()
    db.session.refresh(usuario)
    assert usuario.materias == [Materia.MATEMATICA, Materia.FISICA]


def test_set_materias_vazio_grava_null(app, db, usuario):
    usuario.set_materias([Materia.MATEMATICA])
    db.session.commit()
    usuario.set_materias([])
    db.session.commit()
    db.session.refresh(usuario)
    assert usuario.materias_csv is None
    assert usuario.materias == []


def test_rota_perfil_salva_materias(app, db, usuario, client, logar):
    logar(usuario)
    resposta = client.post(
        "/perfil",
        data={"acao": "materias", "materias": ["MATEMATICA", "QUIMICA"]},
    )
    assert resposta.status_code == 302
    db.session.refresh(usuario)
    assert usuario.materias == [Materia.MATEMATICA, Materia.QUIMICA]


# --------------------------------------------------------------------------
# D.2 — filtro de ranking por matérias
# --------------------------------------------------------------------------


def test_filtro_query_string_recalcula_e_renumera(app, db, admin, usuario, client, logar):
    turma = _semear(db, admin)
    logar(usuario)

    resposta = client.get(f"/simulados/turma/{turma.id}?materias=MAT")
    assert resposta.status_code == 200
    # Recorte só com Matemática: deve aparecer o aviso de classificação filtrada.
    assert "filtrada pelas suas matérias".encode("utf-8") in resposta.data


def test_filtro_default_vem_do_perfil_quando_sem_query(app, db, admin, usuario, client, logar):
    turma = _semear(db, admin)
    usuario.set_materias([Materia.MATEMATICA])
    db.session.commit()
    logar(usuario)

    resposta = client.get(f"/simulados/turma/{turma.id}")
    assert resposta.status_code == 200
    assert "filtrada pelas suas matérias".encode("utf-8") in resposta.data


def test_filtro_todas_ignora_o_recorte_do_perfil(app, db, admin, usuario, client, logar):
    """"TODAS" é o escape explícito: ignora o perfil (só MAT) e usa as 4
    matérias da prova inteira — não fica preso ao recorte cadastrado."""
    turma = _semear(db, admin)
    usuario.set_materias([Materia.MATEMATICA])
    db.session.commit()
    logar(usuario)

    resposta = client.get(f"/simulados/turma/{turma.id}?materias=TODAS")
    assert resposta.status_code == 200
    texto = resposta.data.decode("utf-8")
    inicio = texto.index('id="turma-data"')
    bruto = texto[texto.index(">", inicio) + 1: texto.index("</script>", inicio)]
    dados = json.loads(bruto)
    assert dados["padrao"] == ["MATEMATICA", "FISICA", "QUIMICA", "INGLES"]


def test_ranking_com_recorte_renumera_a_partir_de_1(app, db, admin):
    turma = _semear(db, admin)
    so_matematica = turma.ranking([Materia.MATEMATICA])
    posicoes = [pos for pos, _, _ in so_matematica]
    assert posicoes[0] == 1
