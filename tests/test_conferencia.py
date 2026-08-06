"""Relatório de qualidade: os erros que nenhuma trava aritmética pega."""

import json

from app.conferencia import (
    contagem_por_turma,
    nomes_que_aparecem_uma_vez,
    pessoa_em_duas_turmas,
    relatorio,
    serie_que_regride,
    tem_alerta,
)
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from tests.conftest import payload_simulado


def _importar(db, admin, **ajustes):
    aplicar_simulado(db, parse_simulado(json.dumps(payload_simulado(**ajustes))), admin.id)
    db.session.commit()


def test_serie_que_regride_e_reportada(app, db, admin):
    _importar(db, admin, rotulo="S1", data="2026-03-01")

    # A MESMA pessoa aparece como 2º ANO num simulado POSTERIOR.
    depois = payload_simulado(rotulo="S2", data="2026-04-01")
    depois["resultados"][0]["serie"] = "2º ANO"
    aplicar_simulado(db, parse_simulado(json.dumps(depois)), admin.id)
    db.session.commit()

    avisos = serie_que_regride()
    assert len(avisos) == 1
    assert avisos[0]["nome"] == "ALUNO NOVATA UM"
    assert "3º ANO" in avisos[0]["de"] and "2º ANO" in avisos[0]["para"]


def test_serie_que_avanca_nao_e_reportada(app, db, admin):
    _importar(db, admin, rotulo="S1", data="2026-03-01")

    depois = payload_simulado(rotulo="S2", data="2026-04-01")
    depois["resultados"][0]["serie"] = "CURSO"  # 3º ANO -> CURSO é progressão
    aplicar_simulado(db, parse_simulado(json.dumps(depois)), admin.id)
    db.session.commit()

    assert serie_que_regride() == []


def test_nome_que_aparece_uma_vez_so(app, db, admin):
    _importar(db, admin, rotulo="S1", data="2026-03-01")

    # Nome truncado: vira "outra pessoa" que só aparece uma vez.
    depois = payload_simulado(rotulo="S2", data="2026-04-01")
    depois["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(depois)), admin.id)
    db.session.commit()

    solitarios = {item["nome"] for item in nomes_que_aparecem_uma_vez()}
    assert "ALUNO NOVATA U" in solitarios
    assert "ALUNO NOVATA UM" in solitarios
    assert "ALUNO NOVATA DOIS" not in solitarios, "esse aparece nos dois simulados"


def test_pessoa_em_duas_turmas_entre_provas(app, db, admin):
    """Dentro da mesma prova isso bloqueia; entre provas, vira aviso."""
    _importar(db, admin, turma="novata", rotulo="S1", data="2026-03-01")

    outra = payload_simulado(turma="veterana", rotulo="S2", data="2026-04-01")
    outra["resultados"][0]["nome"] = "ALUNO NOVATA UM"  # mesma pessoa, outra turma
    aplicar_simulado(db, parse_simulado(json.dumps(outra)), admin.id)
    db.session.commit()

    avisos = pessoa_em_duas_turmas()
    assert any(a["nome"] == "ALUNO NOVATA UM" for a in avisos)


def test_contagem_por_turma(app, db, admin):
    _importar(db, admin, turma="novata")
    _importar(db, admin, turma="veterana")

    contagem = contagem_por_turma()
    assert contagem["simulados"][0]["por_turma"] == {"Novatos": 3, "Veteranos": 3}


def test_relatorio_limpo_nao_alerta(app, db, admin):
    _importar(db, admin, rotulo="S1", data="2026-03-01")
    _importar(db, admin, rotulo="S2", data="2026-04-01")

    dados = relatorio()
    assert dados["serie_regride"] == []
    assert dados["duas_turmas"] == []
    assert dados["nomes_solitarios"] == []
    assert tem_alerta(dados) is False
