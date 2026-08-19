"""Ranking de simulado da turma: parse, aplicar por turma, fase e ranking filtrado."""

import json
from datetime import date

import pytest

from app.models import SimuladoTurma
from app.oficiais_import import ErroImport
from app.simulado_turma_import import aplicar, parse
from tests.conftest import payload_simulado, payload_simulado_discursivo


def _parse(dados, data_padrao=None):
    return parse(json.dumps(dados), data_padrao=data_padrao)


# --------------------------------------------------------------------------
# parse
# --------------------------------------------------------------------------


def test_parse_caminho_feliz(app):
    dados = _parse(payload_simulado())
    assert dados["fase"] == "objetiva"
    assert dados["resumo"] == {"presente": 2, "ausente": 1}
    # Os totais vêm do padrão da banca, não do JSON.
    assert dados["questoes"] == {
        "MATEMATICA": 12,
        "FISICA": 12,
        "QUIMICA": 12,
        "INGLES": 12,
    }
    assert {ln["turma"] for ln in dados["linhas"]} == {"novata"}


def test_parse_aceita_fase_discursiva(app):
    dados = _parse(payload_simulado_discursivo())
    assert dados["fase"] == "discursiva"


def test_parse_recusa_fase_desconhecida(app):
    with pytest.raises(ErroImport, match="Fase"):
        _parse(payload_simulado(fase="terceira"))


def test_parse_usa_data_do_formulario_quando_json_vem_nulo(app):
    dados = _parse(payload_simulado(data=None), data_padrao=date(2026, 5, 10))
    assert dados["data"] == date(2026, 5, 10)


def test_parse_exige_data_de_algum_lugar(app):
    with pytest.raises(ErroImport, match="data"):
        _parse(payload_simulado(data=None))


def test_parse_aceita_geral_oficial_nulo(app):
    """Planilhas de "1ª e 2ª fase" não têm coluna de total de acertos."""
    dados = payload_simulado()
    for pessoa in dados["resultados"]:
        if pessoa["status"] == "presente":
            pessoa["geral_oficial"] = None
    assert _parse(dados)["linhas"][0]["geral_oficial"] is None


def test_parse_recusa_geral_que_nao_bate_com_a_soma(app):
    dados = payload_simulado()
    dados["resultados"][0]["geral_oficial"] = 99
    with pytest.raises(ErroImport, match="GERAL"):
        _parse(dados)


def test_parse_recusa_acerto_acima_do_total_da_prova(app):
    dados = payload_simulado()
    dados["resultados"][0]["acertos"]["MAT"] = 13
    with pytest.raises(ErroImport, match="12 questões"):
        _parse(dados)


def test_parse_recusa_presente_zerado_em_tudo(app):
    dados = payload_simulado()
    dados["resultados"][0]["acertos"] = {"MAT": 0, "FIS": 0, "QUIM": 0, "ING": 0}
    dados["resultados"][0]["geral_oficial"] = 0
    with pytest.raises(ErroImport, match="ausente"):
        _parse(dados)


def test_parse_recusa_banca_desconhecida_sem_questoes(app):
    with pytest.raises(ErroImport, match="questoes"):
        _parse(payload_simulado(banca="EFOMM"))


def test_parse_aceita_banca_desconhecida_com_questoes(app):
    dados = payload_simulado(
        banca="EFOMM", questoes={"MAT": 20, "FIS": 20, "QUIM": 20, "ING": 20}
    )
    assert _parse(dados)["questoes"]["MATEMATICA"] == 20


# --------------------------------------------------------------------------
# aplicar
# --------------------------------------------------------------------------


def test_duas_turmas_na_mesma_prova(app, db, admin):
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    aplicar(db, _parse(payload_simulado("veterana")), admin.id)
    db.session.commit()

    provas = db.session.scalars(db.select(SimuladoTurma)).all()
    assert len(provas) == 1
    assert provas[0].turmas_presentes == ["novata", "veterana"]


def test_reimportar_novata_nao_apaga_veterana(app, db, admin):
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    aplicar(db, _parse(payload_simulado("veterana")), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    ids_veterana = sorted(ln.id for ln in prova.linhas if ln.turma == "veterana")

    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    assert sorted(ln.id for ln in prova.linhas if ln.turma == "veterana") == ids_veterana
    assert len(prova.linhas) == 6


def test_mesmo_rotulo_em_datas_diferentes_sao_provas_distintas(app, db, admin):
    """"S5" repete todo ano: a data faz parte da chave."""
    aplicar(db, _parse(payload_simulado(data="2026-04-11")), admin.id)
    aplicar(db, _parse(payload_simulado(data="2027-04-11")), admin.id)
    db.session.commit()

    assert len(db.session.scalars(db.select(SimuladoTurma)).all()) == 2


def test_mesma_pessoa_em_duas_turmas(app, db, admin):
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()

    outro = payload_simulado("veterana")
    outro["resultados"][0]["nome"] = "ALUNO NOVATA UM"
    with pytest.raises(ErroImport, match="aparece na turma"):
        aplicar(db, _parse(outro), admin.id)


def test_as_duas_fases_sao_provas_distintas(app, db, admin):
    """Antes da 2ª fase existir, importar a discursiva por cima da objetiva era
    um erro ("já foi importado como fase X"). Agora é o caso normal: a planilha
    "ITA S5 - 1ª e 2ª fase" traz as duas, e elas viram duas provas.

    O que NÃO pode acontecer é a segunda apagar a primeira — era exatamente
    isso que o ramo de reimport de `aplicar()` faria se a busca ignorasse a
    fase.
    """
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()
    linhas_da_objetiva = len(
        db.session.scalar(db.select(SimuladoTurma)).linhas
    )

    aplicar(db, _parse(payload_simulado_discursivo("novata")), admin.id)
    db.session.commit()

    provas = db.session.scalars(
        db.select(SimuladoTurma).order_by(SimuladoTurma.fase)
    ).all()
    assert [p.fase for p in provas] == ["discursiva", "objetiva"]
    objetiva = next(p for p in provas if p.fase == "objetiva")
    assert len(objetiva.linhas) == linhas_da_objetiva, (
        "importar a 2ª fase apagou as linhas da 1ª"
    )


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------


def test_ranking_filtrado_renumera_do_primeiro(app, db, admin):
    """Numa lista só de veteranos, o primeiro é 1º — e não 3º."""
    aplicar(db, _parse(payload_simulado("novata")), admin.id)

    veterana = payload_simulado("veterana")
    # Notas baixas de propósito: sem filtro, os veteranos ficam atrás.
    veterana["resultados"][0]["acertos"] = {"MAT": 3, "FIS": 3, "QUIM": 3, "ING": 3}
    veterana["resultados"][0]["media_oficial"] = 2.5
    veterana["resultados"][0]["geral_oficial"] = 12
    veterana["resultados"][1]["acertos"] = {"MAT": 2, "FIS": 2, "QUIM": 2, "ING": 2}
    veterana["resultados"][1]["media_oficial"] = 1.67
    veterana["resultados"][1]["geral_oficial"] = 8
    aplicar(db, _parse(veterana), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    materias = prova.materias_media

    geral = prova.ranking(materias)
    assert [pos for pos, _, _ in geral] == [1, 2, 3, 4]
    assert geral[2][1].turma == "veterana", "veteranos ficam atrás no ranking geral"

    so_veteranos = prova.ranking(materias, "veterana")
    assert [pos for pos, _, _ in so_veteranos] == [1, 2], "renumera dentro do recorte"
    assert all(ln.turma == "veterana" for _, ln, _ in so_veteranos)


def test_ranking_mantem_empate_na_mesma_posicao(app, db, admin):
    dados = payload_simulado()
    # Duas pessoas com os mesmos acertos nas matérias da média.
    dados["resultados"][1]["acertos"] = {"MAT": 9, "FIS": 5, "QUIM": 5, "ING": 2}
    dados["resultados"][1]["media_oficial"] = 5.28
    dados["resultados"][1]["geral_oficial"] = 21
    aplicar(db, _parse(dados), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    posicoes = [pos for pos, _, _ in prova.ranking(prova.materias_media)]
    assert posicoes == [1, 1]


def test_nota_reproduz_a_media_do_colegio_no_ita(app, db, admin):
    """No ITA (12 questões em tudo), a média de percentuais é a MÉDIA do mural."""
    aplicar(db, _parse(payload_simulado()), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    linha = next(ln for ln in prova.linhas if ln.media_oficial == 5.28)
    assert prova.nota_de(linha, prova.materias_media) == pytest.approx(5.28, abs=0.01)


def test_nota_e_proporcional_ao_numero_de_questoes_no_ime(app, db, admin):
    """IME: MAT e FIS têm 15 questões, QUIM tem 10 — pesos diferentes.

    Acertos 11+11+4 = 26 de 40 questões -> 26/40*10 = 6,50, que é exatamente o
    que a planilha do colégio imprime (peso igual daria 6,22)."""
    dados = payload_simulado(
        banca="IME",
        rotulo="S6",
        materias=["MAT", "FIS", "QUIM"],
        materias_media=["MAT", "FIS", "QUIM"],
        questoes=None,
        resultados=[
            {
                "nome": "ALUNO IME UM",
                "serie": "3º ANO",
                "status": "presente",
                "acertos": {"MAT": 11, "FIS": 11, "QUIM": 4},
                "media_oficial": 6.50,
                "geral_oficial": 26,
            },
        ],
    )
    aplicar(db, _parse(dados), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    assert prova.questoes == {"MATEMATICA": 15, "FISICA": 15, "QUIMICA": 10}
    linha = prova.linhas[0]
    assert prova.nota_de(linha, prova.materias_media) == pytest.approx(6.50, abs=0.01)


def test_presentes_e_ausentes_aceitam_filtro(app, db, admin):
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    aplicar(db, _parse(payload_simulado("veterana")), admin.id)
    db.session.commit()

    prova = db.session.scalar(db.select(SimuladoTurma))
    assert len(prova.presentes()) == 4
    assert len(prova.presentes("novata")) == 2
    assert len(prova.ausentes("veterana")) == 1
