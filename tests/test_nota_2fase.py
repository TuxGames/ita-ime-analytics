"""Nota decimal da 2ª fase: coluna separada, e média que NINGUÉM calcula.

Duas regras que este arquivo protege:

1. Nota decimal não mora em `acertos_json`. Lá são questões CERTAS sobre um
   total; aqui a nota já nasce em 0–10 e não há total. Misturar faria cada
   leitor precisar saber a fase, e quem errasse mostraria "5.7/12" na tela.

2. A média é COPIADA da planilha, nunca calculada. As fórmulas observadas
   entram só como conferência de leitura — o colégio pode mudar o peso sem
   avisar, e aí o número copiado continua certo e o calculado não.
"""

from datetime import date

from app.models import Materia, SimuladoTurma, SimuladoTurmaLinha

# ITA S5, bloco discursivo: MAT QUÍ FIS POR RED (sem Inglês).
MATERIAS_DISCURSIVA = [
    Materia.MATEMATICA, Materia.QUIMICA, Materia.FISICA,
    Materia.PORTUGUES, Materia.REDACAO,
]


def _prova_discursiva(db, admin, **kw):
    prova = SimuladoTurma(
        banca="ITA", rotulo="S5", data=date(2026, 5, 9), fase="discursiva",
        created_by=admin.id, **kw,
    )
    prova.set_materias(MATERIAS_DISCURSIVA)
    db.session.add(prova)
    return prova


def _linha(prova, nome, notas, **kw):
    linha = SimuladoTurmaLinha(
        nome=nome, nome_norm=nome, turma="veterana", status="presente", **kw
    )
    linha.set_notas(notas)
    prova.linhas.append(linha)
    return linha


# --------------------------------------------------------------------------
# A coluna separada
# --------------------------------------------------------------------------


def test_nota_decimal_nao_encosta_em_acertos(app, db, admin):
    """O ponto inteiro da coluna nova: quem lê `acertos` não vê nota decimal."""
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {"MATEMATICA": 5.7, "FISICA": 3.5})
    db.session.commit()

    assert linha.notas == {"MATEMATICA": 5.7, "FISICA": 3.5}
    assert linha.acertos == {}, "nota decimal vazou para o campo de acertos"
    assert linha.acertos_json is None


def test_leitor_que_nao_conhece_a_2a_fase_some_em_vez_de_mentir(app, db, admin):
    """Os ~14 leitores de `acertos` desenham "X/Y". Numa linha discursiva eles
    têm que não desenhar nada — nunca "5.7/12"."""
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {"MATEMATICA": 5.7})
    db.session.commit()

    assert linha.acertos.get("MATEMATICA") is None
    assert not linha.acertos


def test_notas_sobrevive_ao_banco(app, db, admin):
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {"MATEMATICA": 0.0, "REDACAO": 10.0})
    db.session.commit()
    db.session.expire_all()

    recarregada = db.session.get(SimuladoTurmaLinha, linha.id)
    assert recarregada.notas == {"MATEMATICA": 0.0, "REDACAO": 10.0}


def test_zero_nao_e_ausencia(app, db, admin):
    """Zerar tudo na discursiva é legítimo e acontece — a planilha do ITA S5
    tem uma linha 0,00 0,00 0,20 0,00 0,00. Não pode virar `notas` vazio."""
    prova = _prova_discursiva(db, admin)
    zeros = {m.name: 0.0 for m in MATERIAS_DISCURSIVA}
    linha = _linha(prova, "PESSOA UM", zeros)
    db.session.commit()

    assert linha.notas == zeros
    assert linha.notas_json is not None


# --------------------------------------------------------------------------
# As matérias diferem entre as fases do mesmo simulado
# --------------------------------------------------------------------------


def test_as_duas_fases_tem_materias_diferentes(app, db, admin):
    """ITA S5: o discursivo tem POR e RED e não tem ING; a objetiva tem ING e
    não tem POR nem RED. O modelo guarda as matérias por prova, então cada
    fase carrega o próprio conjunto sem conflito."""
    discursiva = _prova_discursiva(db, admin)

    objetiva = SimuladoTurma(
        banca="ITA", rotulo="S5", data=date(2026, 5, 9), fase="objetiva",
        created_by=admin.id,
    )
    objetiva.set_materias([
        Materia.MATEMATICA, Materia.QUIMICA, Materia.FISICA, Materia.INGLES,
    ])
    objetiva.set_questoes(
        {"MATEMATICA": 12, "QUIMICA": 12, "FISICA": 12, "INGLES": 12}
    )
    db.session.add(objetiva)
    db.session.commit()

    nomes_disc = {m.name for m in discursiva.materias}
    nomes_obj = {m.name for m in objetiva.materias}

    assert "PORTUGUES" in nomes_disc and "REDACAO" in nomes_disc
    assert "INGLES" not in nomes_disc
    assert "INGLES" in nomes_obj
    assert "PORTUGUES" not in nomes_obj and "REDACAO" not in nomes_obj


# --------------------------------------------------------------------------
# nota_de: régua do recorte, não a média do colégio
# --------------------------------------------------------------------------


def test_nota_de_na_discursiva_e_media_simples_do_recorte(app, db, admin):
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {
        "MATEMATICA": 6.0, "QUIMICA": 6.35, "FISICA": 3.4,
        "PORTUGUES": 6.67, "REDACAO": 7.2,
    })
    db.session.commit()

    # (6.00 + 6.35 + 3.40 + 6.67 + 7.20) / 5
    assert prova.nota_de(linha, MATERIAS_DISCURSIVA) == 5.92
    # Recorte só das exatas: (6.00 + 6.35 + 3.40) / 3
    assert prova.nota_de(
        linha, [Materia.MATEMATICA, Materia.QUIMICA, Materia.FISICA]
    ) == 5.25


def test_nota_de_nao_finge_ser_a_media_da_planilha(app, db, admin):
    """A média oficial do discursivo do ITA pesa exatas em dobro, e dá 5,67
    nesta linha real. `nota_de` dá a média simples, 5,92. A diferença é
    proposital: o número do colégio é `media_informada`, copiado."""
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {
        "MATEMATICA": 6.0, "QUIMICA": 6.35, "FISICA": 3.4,
        "PORTUGUES": 6.67, "REDACAO": 7.2,
    }, media_informada=5.67)
    db.session.commit()

    assert prova.nota_de(linha, MATERIAS_DISCURSIVA) != linha.media_informada
    assert linha.media_informada == 5.67


def test_nota_de_da_objetiva_nao_mudou(app, db, admin):
    """A 1ª fase continua proporcional às questões — a régua velha intacta."""
    prova = SimuladoTurma(
        banca="IME", rotulo="S3", data=date(2026, 4, 11), fase="objetiva",
        created_by=admin.id,
    )
    prova.set_materias([Materia.MATEMATICA, Materia.FISICA, Materia.QUIMICA])
    prova.set_questoes({"MATEMATICA": 15, "FISICA": 15, "QUIMICA": 10})
    db.session.add(prova)
    linha = SimuladoTurmaLinha(
        nome="PESSOA UM", nome_norm="PESSOA UM", turma="veterana",
        status="presente",
    )
    linha.set_acertos({"MATEMATICA": 11, "FISICA": 11, "QUIMICA": 4})
    prova.linhas.append(linha)
    db.session.commit()

    # 26/40 * 10 = 6,50 — o exemplo que está no docstring do modelo.
    assert prova.nota_de(linha, prova.materias) == 6.5


def test_ranking_da_discursiva_ordena_por_nota(app, db, admin):
    prova = _prova_discursiva(db, admin)
    _linha(prova, "MEDIANA", {m.name: 5.0 for m in MATERIAS_DISCURSIVA})
    _linha(prova, "MELHOR", {m.name: 9.0 for m in MATERIAS_DISCURSIVA})
    _linha(prova, "PIOR", {m.name: 1.0 for m in MATERIAS_DISCURSIVA})
    db.session.commit()

    ordem = [ln.nome for _, ln, _ in prova.ranking(MATERIAS_DISCURSIVA)]

    assert ordem == ["MELHOR", "MEDIANA", "PIOR"]


# --------------------------------------------------------------------------
# As médias copiadas
# --------------------------------------------------------------------------


def test_media_informada_e_media_final_sao_campos_distintos(app, db, admin):
    """No ITA S5 a planilha traz as duas: a média do bloco discursivo e a
    MÉDIA FINAL das duas fases. Guardar as duas no mesmo campo perderia uma."""
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {"MATEMATICA": 6.0},
                   media_informada=5.67, media_final_informada=5.65)
    db.session.commit()

    assert linha.media_informada == 5.67
    assert linha.media_final_informada == 5.65


def test_media_informada_nao_contamina_media_oficial(app, db, admin):
    """`media_oficial` tem contrato exato (a média da objetiva, conferida
    contra a soma dos acertos). O número de significado desconhecido fica fora
    dela."""
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {"MATEMATICA": 6.0}, media_informada=5.56)
    db.session.commit()

    assert linha.media_oficial is None
    assert linha.geral_oficial is None


def test_sem_coluna_de_media_o_campo_fica_nulo(app, db, admin):
    """Nunca calculada: sem a coluna na planilha, o campo fica NULL."""
    prova = _prova_discursiva(db, admin)
    linha = _linha(prova, "PESSOA UM", {"MATEMATICA": 6.0})
    db.session.commit()

    assert linha.media_informada is None
    assert linha.media_final_informada is None


def test_a_segunda_data_do_titulo_e_guardada(app, db, admin):
    """O título "Simulado IME S6 - 11/07/2026 - 14/04/2026" traz duas datas. A
    segunda é a pista para descobrir o que a coluna de média do IME significa;
    descartar seria perder a evidência."""
    prova = _prova_discursiva(db, admin, data_secundaria=date(2026, 4, 14))
    db.session.commit()

    assert prova.data_secundaria == date(2026, 4, 14)


def test_prova_sem_segunda_data_fica_nula(app, db, admin):
    prova = _prova_discursiva(db, admin)
    db.session.commit()

    assert prova.data_secundaria is None
