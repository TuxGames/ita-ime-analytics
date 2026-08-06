"""Fase E: evolução de um aluno ao longo dos simulados da turma."""

import json

from app.evolucao import evolucao_do_aluno
from app.models import Aluno, Materia, SimuladoTurmaLinha
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from tests.conftest import payload_simulado


def _aplicar(db, admin, dados):
    aplicar_simulado(db, parse_simulado(json.dumps(dados)), admin.id)
    db.session.commit()


def test_evolucao_sem_simulados_devolve_tem_dado_falso(app, db):
    aluno = Aluno(nome="NINGUÉM", nome_norm="NINGUEM")
    db.session.add(aluno)
    db.session.commit()

    dados = evolucao_do_aluno(aluno.id)
    assert dados["tem_dado"] is False
    assert dados["labels"] == []


def test_evolucao_calcula_percentil_e_serie_por_materia_em_ordem_cronologica(app, db, admin):
    # S3 (data 2026-04-11, default do fixture) e um S4 posterior. Mesmo aluno
    # nos dois, com desempenho melhorando de um para o outro.
    s3 = payload_simulado(rotulo="S3")
    s3["resultados"][0]["nome"] = "ALUNO EVOLUCAO UM"
    s3["resultados"][0]["acertos"] = {"MAT": 6, "FIS": 6, "QUIM": 6, "ING": 6}
    s3["resultados"][0]["media_oficial"] = 5.00
    s3["resultados"][0]["geral_oficial"] = 24
    _aplicar(db, admin, s3)

    s4 = payload_simulado(rotulo="S4", data="2026-05-11")
    s4["resultados"][0]["nome"] = "ALUNO EVOLUCAO UM"
    s4["resultados"][0]["acertos"] = {"MAT": 12, "FIS": 12, "QUIM": 12, "ING": 12}
    s4["resultados"][0]["media_oficial"] = 10.00
    s4["resultados"][0]["geral_oficial"] = 48
    _aplicar(db, admin, s4)

    linha = db.session.scalar(
        db.select(SimuladoTurmaLinha).filter_by(nome="ALUNO EVOLUCAO UM").limit(1)
    )
    aluno_id = linha.aluno_id

    dados = evolucao_do_aluno(aluno_id)
    assert dados["tem_dado"] is True
    assert len(dados["labels"]) == 2
    assert "S3" in dados["labels"][0]
    assert "S4" in dados["labels"][1]

    # Foi o único presente em cada prova (fixture cria só ele + 2 outros do
    # mesmo turma_import, mas com nomes diferentes) -> percentil 100 nos dois.
    assert dados["percentil"]["values"] == [100.0, 100.0]

    # Série por matéria: melhora de 50% pra 100% em MAT.
    assert dados["materias"]["MATEMATICA"]["valores"] == [50.0, 100.0]


def test_evolucao_respeita_filtro_de_materias(app, db, admin):
    dados_import = payload_simulado(rotulo="S5")
    dados_import["resultados"][0]["nome"] = "ALUNO EVOLUCAO DOIS"
    _aplicar(db, admin, dados_import)

    linha = db.session.scalar(
        db.select(SimuladoTurmaLinha).filter_by(nome="ALUNO EVOLUCAO DOIS")
    )
    dados = evolucao_do_aluno(linha.aluno_id, materias=[Materia.MATEMATICA])
    assert list(dados["materias"].keys()) == ["MATEMATICA"]


def test_rota_evolucao_pessoal_sem_dado(app, db, usuario, client, logar):
    logar(usuario)
    resposta = client.get("/evolucao")
    assert resposta.status_code == 200
    assert "Sem simulados da turma ainda".encode("utf-8") in resposta.data


def test_rota_evolucao_admin_exige_admin(app, db, usuario, client, logar):
    aluno = Aluno(nome="X", nome_norm="X")
    db.session.add(aluno)
    db.session.commit()

    logar(usuario)
    resposta = client.get(f"/admin/alunos/{aluno.id}/evolucao")
    assert resposta.status_code in (302, 403)


def test_evolucao_traz_mediana_da_turma_por_materia(app, db, admin):
    dados_import = payload_simulado(rotulo="S6")
    dados_import["resultados"][0]["nome"] = "ALUNO EVOLUCAO TRES"
    _aplicar(db, admin, dados_import)

    linha = db.session.scalar(
        db.select(SimuladoTurmaLinha).filter_by(nome="ALUNO EVOLUCAO TRES")
    )
    dados = evolucao_do_aluno(linha.aluno_id)
    # 3 pessoas no payload padrão (uma ausente): a mediana existe e é um número.
    assert dados["materias"]["MATEMATICA"]["mediana_turma"][0] is not None
