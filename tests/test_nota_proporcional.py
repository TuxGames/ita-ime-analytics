"""Uma régua só para a nota: proporcional às questões.

O simulado pessoal usava média simples dos percentuais e o ranking da turma,
proporcional. No ITA (12 questões em tudo) as duas coincidem; no IME (15/15/10)
divergem, e a mesma prova aparecia como 48,9 numa tela e 5,00 na outra.

Agora a conta é uma só (`models.nota_proporcional`); o que muda é a escala:
100 no simulado pessoal (mostrado como %), 10 no ranking (mural do colégio).
"""

import json
from datetime import date, timedelta

import pytest

from app.models import Concurso, Materia, Simulado, SimuladoTurma, SimuladoTurmaLinha
from app.models import nota_proporcional
from app.simulado_sync import sincronizar_linha
from app.simulado_turma_import import aplicar, parse

from .conftest import payload_simulado


# --------------------------------------------------------------------------
# A conta
# --------------------------------------------------------------------------


def test_proporcional_com_pesos_diferentes():
    """IME 15/15/10, acertos 11+11+4 = 26/40 -> 6,50 (o exemplo do modelo)."""
    pares = [(11, 15), (11, 15), (4, 10)]

    assert nota_proporcional(pares, escala=10.0) == 6.5
    assert nota_proporcional(pares, escala=100.0) == 65.0


def test_o_caso_do_relato():
    """20 de 40 no IME: 50% / 5,00 — e NÃO 48,89, que era a média simples."""
    pares = [(8, 15), (8, 15), (4, 10)]
    media_simples = round(sum(100.0 * a / t for a, t in pares) / len(pares), 2)

    assert media_simples == 48.89, "a conta antiga, para o contraste"
    assert nota_proporcional(pares, escala=100.0) == 50.0
    assert nota_proporcional(pares, escala=10.0) == 5.0


def test_com_pesos_iguais_as_duas_formulas_coincidem():
    """ITA: 12 questões em tudo. É por isso que o problema passou despercebido."""
    pares = [(9, 12), (7, 12), (6, 12)]
    media_simples = round(sum(100.0 * a / t for a, t in pares) / len(pares), 2)

    assert nota_proporcional(pares, escala=100.0) == media_simples


@pytest.mark.parametrize(
    "pares", [[], [(0, 0)], [(None, 12)], [(5, None)]]
)
def test_sem_questao_devolve_none(pares):
    assert nota_proporcional(pares) is None


def test_escala_padrao_e_100():
    assert nota_proporcional([(1, 2)]) == 50.0


# --------------------------------------------------------------------------
# As duas telas contam a mesma história
# --------------------------------------------------------------------------


def _prova_ime(db, admin):
    """Ranking do IME (15/15/10), onde as fórmulas divergiam."""
    dados = payload_simulado("novata", banca="IME")
    dados["materias"] = ["MAT", "FIS", "QUIM"]
    dados["materias_media"] = ["MAT", "FIS", "QUIM"]
    dados["questoes"] = {"MAT": 15, "FIS": 15, "QUIM": 10}
    for r in dados["resultados"]:
        if r["status"] == "presente":
            r["acertos"] = {"MAT": 8, "FIS": 8, "QUIM": 4}
            r.pop("media_oficial", None)
            r.pop("geral_oficial", None)
    aplicar(db, parse(json.dumps(dados)), admin.id)
    db.session.commit()
    return db.session.scalar(db.select(SimuladoTurma))


def test_ranking_e_simulado_pessoal_dao_o_mesmo_resultado(app, db, admin):
    """5,00 no ranking e 50,0% no perfil — o mesmo número, duas apresentações."""
    turma = _prova_ime(db, admin)
    concurso = Concurso(
        nome="IME - 1ª Fase",
        data_prova=date.today() + timedelta(days=90),
        created_by=admin.id,
        materias_csv="MATEMATICA,FISICA,QUIMICA",
    )
    db.session.add(concurso)
    db.session.commit()

    linha = db.session.scalar(
        db.select(SimuladoTurmaLinha).filter_by(turma_id=turma.id).order_by(SimuladoTurmaLinha.id)
    )
    linha.user_id = admin.id
    db.session.commit()

    simulado = sincronizar_linha(linha, concurso, admin.id)
    db.session.commit()

    nota_ranking = next(
        nota for _, ln, nota in turma.ranking(turma.materias_media) if ln.id == linha.id
    )
    assert nota_ranking == 5.0
    assert simulado.nota_geral == 50.0
    assert simulado.nota_geral == nota_ranking * 10, "mesma régua, escalas diferentes"


def test_ranking_da_turma_continua_em_0_a_10(app, db, admin):
    """O mural do colégio não pode mudar de escala."""
    turma = _prova_ime(db, admin)

    notas = [nota for _, _, nota in turma.ranking(turma.materias_media)]

    assert notas, "a prova tem gente"
    assert all(0 <= n <= 10 for n in notas), notas


# --------------------------------------------------------------------------
# As telas
# --------------------------------------------------------------------------


def test_telas_do_simulado_pessoal_mostram_porcentagem(client, db, admin, logar):
    concurso = Concurso(
        nome="ITA - 1ª Fase",
        data_prova=date.today() + timedelta(days=90),
        created_by=admin.id,
    )
    db.session.add(concurso)
    db.session.commit()
    simulado = Simulado(
        user_id=admin.id,
        concurso_id=concurso.id,
        data_simulado=date.today(),
        nota_geral=50.0,
        nota_automatica=True,
    )
    db.session.add(simulado)
    db.session.commit()
    logar(admin)

    lista = client.get("/simulados/").get_data(as_text=True)
    detalhe = client.get(f"/simulados/{simulado.id}").get_data(as_text=True)

    assert "50.0%" in lista
    assert "50.0%" in detalhe


def test_nenhuma_tela_afirma_escala_0_a_10_para_nota_pessoal():
    """O dashboard dizia "na escala 0–10" embaixo de um número que não estava
    nessa escala. O ranking da turma pode continuar dizendo — é a escala dele."""
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parent.parent
    js = (raiz / "app" / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

    # Só o texto que o usuário lê (as legendas `nota:`), não os comentários —
    # um comentário PODE citar 0–10 para explicar a escala do ranking.
    legendas = re.findall(r'nota:\s*"([^"]+)"', js)

    assert legendas, "não achei as legendas do dashboard"
    erradas = [x for x in legendas if "0–10" in x or "0-10" in x]
    assert not erradas, f"legenda afirma escala errada: {erradas}"
