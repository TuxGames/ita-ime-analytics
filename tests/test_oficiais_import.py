"""Import de resultado oficial: parse, aplicar por turma e conflitos entre turmas."""

import json

import pytest

from app.models import ResultadoOficial
from app.oficiais_import import ErroImport, aplicar, parse
from tests.conftest import payload_oficial


def _parse(dados):
    return parse(json.dumps(dados))


# --------------------------------------------------------------------------
# parse
# --------------------------------------------------------------------------


def test_parse_caminho_feliz(app):
    dados = _parse(payload_oficial())
    assert dados["concurso"] == "AFA 2027"
    assert dados["turma"] == "novata"
    assert dados["resumo"] == {
        "classificado": 1,
        "sem_aproveitamento": 1,
        "nao_encontrado": 1,
    }
    # A turma do cabeçalho é carimbada em cada pessoa.
    assert {ln["turma"] for ln in dados["linhas"]} == {"novata"}


def test_parse_recusa_turma_invalida(app):
    with pytest.raises(ErroImport, match="novata"):
        _parse(payload_oficial(turma="terceirona"))


def test_parse_recusa_nota_fora_da_escala(app):
    dados = payload_oficial()
    dados["resultados"][0]["notas"]["MAT"] = 99
    with pytest.raises(ErroImport, match="fora da escala"):
        _parse(dados)


def test_parse_recusa_materia_fora_do_cabecalho(app):
    dados = payload_oficial()
    dados["resultados"][0]["notas"]["QUIM"] = 5
    with pytest.raises(ErroImport, match="não está na lista"):
        _parse(dados)


def test_parse_recusa_classificado_sem_posicao(app):
    dados = payload_oficial()
    dados["resultados"][0]["classificacao"] = None
    with pytest.raises(ErroImport, match="classificacao"):
        _parse(dados)


def test_parse_recusa_classificacao_duplicada_no_mesmo_json(app):
    dados = payload_oficial()
    dados["resultados"][1] = dict(
        dados["resultados"][0], nome="OUTRA PESSOA", classificacao=100
    )
    with pytest.raises(ErroImport, match="mesma classificação"):
        _parse(dados)


# --------------------------------------------------------------------------
# aplicar — o coração da mudança
# --------------------------------------------------------------------------


def test_duas_turmas_no_mesmo_concurso(app, db, admin):
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    aplicar(db, _parse(payload_oficial("veterana")), admin.id)
    db.session.commit()

    registros = db.session.scalars(db.select(ResultadoOficial)).all()
    assert len(registros) == 1, "a classificação é nacional: um registro por concurso"
    resultado = registros[0]
    assert resultado.turmas_presentes == ["novata", "veterana"]
    assert resultado.total_de("novata") == 3
    assert resultado.total_de("veterana") == 3


def test_reimportar_novata_nao_apaga_veterana(app, db, admin):
    """O teste que mais importa: turmas são independentes dentro do concurso."""
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    aplicar(db, _parse(payload_oficial("veterana")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    ids_veterana = sorted(ln.id for ln in resultado.linhas if ln.turma == "veterana")

    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    assert sorted(ln.id for ln in resultado.linhas if ln.turma == "veterana") == (
        ids_veterana
    ), "as linhas da veterana não podem ser recriadas nem removidas"
    assert resultado.total_de("novata") == 3
    assert len(resultado.linhas) == 6


def test_reimportar_preserva_vinculo_da_outra_turma(app, db, admin, criar_usuario):
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    aplicar(db, _parse(payload_oficial("veterana")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    alvo = next(ln for ln in resultado.linhas if ln.turma == "veterana")
    dono = criar_usuario("veterano", nome_oficial=alvo.nome)
    alvo.user_id = dono.id
    db.session.commit()

    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    ainda = next(ln for ln in resultado.linhas if ln.nome == alvo.nome)
    assert ainda.user_id == dono.id


def test_materias_divergentes_entre_turmas(app, db, admin):
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    db.session.commit()

    outro = payload_oficial("veterana", materias=["MAT", "QUIM"])
    for pessoa in outro["resultados"]:
        if "notas" in pessoa:
            pessoa["notas"] = {"MAT": 5.0, "QUIM": 5.0}

    with pytest.raises(ErroImport, match="matérias"):
        aplicar(db, _parse(outro), admin.id)


def test_escala_divergente_entre_turmas(app, db, admin):
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    db.session.commit()

    outro = payload_oficial("veterana", escala=5)
    for pessoa in outro["resultados"]:
        if "notas" in pessoa:
            pessoa["notas"] = {"MAT": 4.0, "FIS": 4.0}

    with pytest.raises(ErroImport, match="escala"):
        aplicar(db, _parse(outro), admin.id)


def test_classificacao_duplicada_entre_turmas(app, db, admin):
    """A classificação é nacional: não pode repetir nem entre turmas."""
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    db.session.commit()

    outro = payload_oficial("veterana")
    outro["resultados"][0]["classificacao"] = 100  # mesma da novata

    with pytest.raises(ErroImport, match="Classificação 100"):
        aplicar(db, _parse(outro), admin.id)


def test_mesma_pessoa_em_duas_turmas(app, db, admin):
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    db.session.commit()

    outro = payload_oficial("veterana")
    outro["resultados"][0]["nome"] = "PESSOA NOVATA UM"

    with pytest.raises(ErroImport, match="aparece na turma"):
        aplicar(db, _parse(outro), admin.id)


def test_metadados_completam_sem_sobrescrever(app, db, admin):
    aplicar(db, _parse(payload_oficial("novata", fonte=None, metrica=None)), admin.id)
    db.session.commit()

    aplicar(db, _parse(payload_oficial("veterana", fonte="GGE", metrica="MP")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    assert resultado.fonte == "GGE", "campo vazio é preenchido pela outra turma"
    assert resultado.metrica == "MP"


# --------------------------------------------------------------------------
# Recortes do modelo
# --------------------------------------------------------------------------


def test_recortes_por_turma(app, db, admin):
    aplicar(db, _parse(payload_oficial("novata")), admin.id)
    aplicar(db, _parse(payload_oficial("veterana")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    assert len(resultado.classificados()) == 2
    assert len(resultado.classificados("novata")) == 1
    assert len(resultado.sem_aproveitamento("veterana")) == 1
    assert len(resultado.nao_encontrados()) == 2
    assert resultado.melhor_classificacao() == 100
    assert resultado.melhor_classificacao("veterana") == 200
