"""Edição manual pelo admin (Fase B): rotas de edição, validação compartilhada
com o import e aviso de reimport sobre linha editada."""

import json

from app.models import ResultadoLinha, ResultadoOficial, SimuladoTurma, SimuladoTurmaLinha
from app.oficiais_import import aplicar as aplicar_oficial
from app.oficiais_import import parse as parse_oficial
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from tests.conftest import payload_oficial, payload_simulado


def _linha_oficial(db, nome):
    return db.session.scalar(db.select(ResultadoLinha).filter_by(nome=nome))


def _linha_simulado(db, nome):
    return db.session.scalar(db.select(SimuladoTurmaLinha).filter_by(nome=nome))


# --------------------------------------------------------------------------
# ResultadoLinha (oficiais)
# --------------------------------------------------------------------------


def test_editar_linha_oficial_valida_grava_editado_em_e_por(app, db, client, admin, logar):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    linha = _linha_oficial(db, "PESSOA NOVATA UM")
    assert linha.editado_em is None

    resposta = client.post(
        f"/oficiais/linha/{linha.id}/editar",
        data={
            "nome": "PESSOA NOVATA UM",
            "turma": "novata",
            "status": "classificado",
            "classificacao": "101",
            "metrica_valor": "7.5",
            "nota_MATEMATICA": "8.0",
            "nota_FISICA": "7.0",
        },
        follow_redirects=True,
    )
    assert resposta.status_code == 200

    linha = _linha_oficial(db, "PESSOA NOVATA UM")
    assert linha.classificacao == 101
    assert linha.metrica_valor == 7.5
    assert linha.notas["MATEMATICA"] == 8.0
    assert linha.editado_em is not None
    assert linha.editado_por == admin.id


def test_editar_linha_oficial_nota_fora_da_escala_mesma_mensagem_do_import(
    app, db, client, admin, logar
):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    linha = _linha_oficial(db, "PESSOA NOVATA UM")

    resposta = client.post(
        f"/oficiais/linha/{linha.id}/editar",
        data={
            "nome": "PESSOA NOVATA UM",
            "turma": "novata",
            "status": "classificado",
            "classificacao": "100",
            "nota_MATEMATICA": "99",
            "nota_FISICA": "7.0",
        },
        follow_redirects=True,
    )
    pagina = resposta.get_data(as_text=True)
    assert "fora da escala" in pagina

    linha = _linha_oficial(db, "PESSOA NOVATA UM")
    assert linha.editado_em is None, "edição inválida não grava nada"
    assert linha.notas["MATEMATICA"] != 99


def test_editar_linha_oficial_status_invalido_recusado(app, db, client, admin, logar):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    linha = _linha_oficial(db, "PESSOA NOVATA UM")

    resposta = client.post(
        f"/oficiais/linha/{linha.id}/editar",
        data={
            "nome": "PESSOA NOVATA UM",
            "turma": "novata",
            "status": "xpto",
            "nota_MATEMATICA": "7.0",
            "nota_FISICA": "7.0",
        },
        follow_redirects=True,
    )
    assert "status inválido" in resposta.get_data(as_text=True)


def test_editar_classificacao_duplicada_recusada_nomeando_outra_pessoa(
    app, db, client, admin, logar
):
    """A classificação é nacional: vale para o concurso inteiro, não só a turma."""
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("veterana"))), admin.id)
    db.session.commit()
    logar(admin)

    # PESSOA NOVATA UM é #100, PESSOA VETERANA UM é #200.
    veterana = _linha_oficial(db, "PESSOA VETERANA UM")
    resposta = client.post(
        f"/oficiais/linha/{veterana.id}/editar",
        data={
            "nome": "PESSOA VETERANA UM",
            "turma": "veterana",
            "status": "classificado",
            "classificacao": "100",
            "nota_MATEMATICA": "7.0",
            "nota_FISICA": "7.0",
        },
        follow_redirects=True,
    )
    pagina = resposta.get_data(as_text=True)
    assert "Classificação 100" in pagina
    assert "PESSOA NOVATA UM" in pagina

    veterana = _linha_oficial(db, "PESSOA VETERANA UM")
    assert veterana.classificacao == 200, "não foi gravado"


def test_editar_cabecalho_oficial_bloqueado_com_materias_e_linhas(
    app, db, client, admin, logar
):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))
    materias_antes = resultado.materias_csv

    resposta = client.post(
        f"/oficiais/{resultado.id}/editar",
        data={"fonte": "NOVA FONTE", "materias_csv": "MATEMATICA"},
        follow_redirects=True,
    )
    pagina = resposta.get_data(as_text=True)
    assert "reimporte" in pagina.lower()

    resultado = db.session.get(ResultadoOficial, resultado.id)
    assert resultado.materias_csv == materias_antes
    assert resultado.fonte != "NOVA FONTE", "o bloqueio recusa a edição inteira, não só o campo perigoso"


def test_editar_cabecalho_oficial_fonte_data_metrica_ok(app, db, client, admin, logar):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))

    client.post(
        f"/oficiais/{resultado.id}/editar",
        data={"fonte": "NOVA FONTE", "metrica": "MG", "data": "2027-01-10"},
    )
    resultado = db.session.get(ResultadoOficial, resultado.id)
    assert resultado.fonte == "NOVA FONTE"
    assert resultado.metrica == "MG"


# --------------------------------------------------------------------------
# Preview de import avisa sobre linha editada
# --------------------------------------------------------------------------


def test_preview_import_avisa_linhas_editadas(app, db, client, admin, logar):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(admin)

    linha = _linha_oficial(db, "PESSOA NOVATA UM")
    client.post(
        f"/oficiais/linha/{linha.id}/editar",
        data={
            "nome": "PESSOA NOVATA UM",
            "turma": "novata",
            "status": "classificado",
            "classificacao": "100",
            "nota_MATEMATICA": "9.0",
            "nota_FISICA": "9.0",
        },
    )
    linha = _linha_oficial(db, "PESSOA NOVATA UM")
    assert linha.editado_em is not None

    resposta = client.post(
        "/oficiais/importar",
        data={"payload": json.dumps(payload_oficial("novata")), "acao": "validar"},
    )
    pagina = resposta.get_data(as_text=True)
    assert "editada" in pagina.lower() or "editad" in pagina.lower()
    assert "PESSOA NOVATA UM" in pagina


# --------------------------------------------------------------------------
# SimuladoTurmaLinha (ranking de simulado)
# --------------------------------------------------------------------------


def test_editar_linha_simulado_valida_grava_editado_em_e_por(app, db, client, admin, logar):
    aplicar_simulado(db, parse_simulado(json.dumps(payload_simulado("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    linha = _linha_simulado(db, "ALUNO NOVATA UM")
    assert linha.editado_em is None

    resposta = client.post(
        f"/simulados/turma/linha/{linha.id}/editar",
        data={
            "nome": "ALUNO NOVATA UM",
            "turma": "novata",
            "serie": "3º ANO",
            "status": "presente",
            "acertos_MATEMATICA": "10",
            "acertos_FISICA": "5",
            "acertos_QUIMICA": "5",
            "acertos_INGLES": "11",
            "geral_oficial": "31",
        },
        follow_redirects=True,
    )
    assert resposta.status_code == 200

    linha = _linha_simulado(db, "ALUNO NOVATA UM")
    assert linha.acertos["MATEMATICA"] == 10
    assert linha.editado_em is not None
    assert linha.editado_por == admin.id


def test_editar_linha_simulado_acertos_acima_do_total_mesma_mensagem_do_import(
    app, db, client, admin, logar
):
    aplicar_simulado(db, parse_simulado(json.dumps(payload_simulado("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    linha = _linha_simulado(db, "ALUNO NOVATA UM")

    resposta = client.post(
        f"/simulados/turma/linha/{linha.id}/editar",
        data={
            "nome": "ALUNO NOVATA UM",
            "turma": "novata",
            "status": "presente",
            "acertos_MATEMATICA": "13",
            "acertos_FISICA": "5",
            "acertos_QUIMICA": "5",
            "acertos_INGLES": "11",
        },
        follow_redirects=True,
    )
    assert "12 questões" in resposta.get_data(as_text=True)

    linha = _linha_simulado(db, "ALUNO NOVATA UM")
    assert linha.editado_em is None


def test_editar_cabecalho_simulado_bloqueado_com_materias_e_linhas(
    app, db, client, admin, logar
):
    aplicar_simulado(db, parse_simulado(json.dumps(payload_simulado("novata"))), admin.id)
    db.session.commit()
    logar(admin)
    turma = db.session.scalar(db.select(SimuladoTurma))

    resposta = client.post(
        f"/simulados/turma/{turma.id}/editar",
        data={"fonte": "NOVA FONTE", "materias_csv": "MATEMATICA"},
        follow_redirects=True,
    )
    pagina = resposta.get_data(as_text=True)
    assert "reimporte" in pagina.lower()

    turma = db.session.get(SimuladoTurma, turma.id)
    assert turma.fonte != "NOVA FONTE"


def test_usuario_comum_nao_edita_linha(app, db, client, admin, usuario, logar):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()
    logar(usuario)
    linha = _linha_oficial(db, "PESSOA NOVATA UM")

    resposta = client.post(
        f"/oficiais/linha/{linha.id}/editar",
        data={"nome": "PESSOA NOVATA UM", "turma": "novata", "status": "classificado"},
    )
    assert resposta.status_code == 403
