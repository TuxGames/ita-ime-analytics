"""Import de ponta a ponta com números REAIS das planilhas do colégio.

Não são dados inventados: cada linha aqui foi copiada das planilhas do ITA S5 e
do IME S6, com as médias que o colégio publicou. O valor deste arquivo é que
ele falha se o app deixar de reproduzir um número que existe no mural.

Cobertura: as linhas que apareceram no material recebido, não a planilha
inteira. É o suficiente para travar os casos que importam — os extremos (linha
zerada), o gabarito do IME e as duas fórmulas do ITA.
"""

import json
from datetime import date

from app.models import SimuladoTurma
from app.simulado_turma_import import aplicar, parse

# ── ITA S5, bloco DISCURSIVO ──────────────────────────────────────────────
# Colunas na ordem da planilha: MAT · QUÍ · FIS · POR · RED · MÉDIA.
# Química ANTES de Física — a ordem varia entre planilhas, e é por isso que o
# prompt manda copiar o cabeçalho em vez de assumir.
ITA_S5_DISCURSIVO = {
    "tipo": "simulado", "fase": "discursiva", "banca": "ITA", "rotulo": "S5",
    "data": "2026-05-09", "data_secundaria": None, "turma": "veterana",
    "fonte": None,
    "materias": ["MAT", "QUIM", "FIS", "PORT", "RED"],
    "materias_media": None,
    "resultados": [
        {
            "nome": "PESSOA A DA PLANILHA REAL", "serie": "3º ANO",
            "status": "presente",
            "notas": {"MAT": 6.00, "QUIM": 6.35, "FIS": 3.40,
                      "PORT": 6.67, "RED": 7.20},
            "media_oficial": 5.67,        # (2·6,00+2·6,35+2·3,40+6,67+7,20)/8
            "media_final_oficial": 5.65,  # 0,8·5,67 + 0,2·5,56
        },
        {
            "nome": "PESSOA B DA PLANILHA REAL", "serie": "3º ANO",
            "status": "presente",
            "notas": {"MAT": 3.80, "QUIM": 4.35, "FIS": 4.30,
                      "PORT": 6.00, "RED": 5.00},
            "media_oficial": 4.49,
            # Média final DESCONHECIDA para esta pessoa. O material recebido
            # traz exemplos da fórmula do discursivo e exemplos da média final,
            # mas só a PESSOA A (5,67) aparece nas duas listas — as demais são
            # gente diferente. Emparelhar 4,49 com o 4,15 de outra linha seria
            # inventar dado, que é o oposto do que este arquivo existe para ser.
            "media_final_oficial": None,
        },
        {
            # O extremo que interessa: zerou quase tudo e MESMO ASSIM está na
            # lista, com média. A regra da 1ª fase recusaria esta linha.
            "nome": "PESSOA C DA PLANILHA REAL", "serie": "2º ANO",
            "status": "presente",
            "notas": {"MAT": 0.00, "QUIM": 0.00, "FIS": 0.20,
                      "PORT": 0.00, "RED": 0.00},
            "media_oficial": 0.05,        # 0,40/8
            "media_final_oficial": None,
        },
        {
            # Faltou a DISCURSIVA. O colégio ainda assim publicou média final
            # (0,00 e 3,61 → 0,72): ausência entra como ZERO, não como
            # exclusão. Como o número é copiado, o app não precisa saber disso
            # — mas o caso tem que atravessar o import sem quebrar.
            "nome": "PESSOA D DA PLANILHA REAL", "serie": "3º ANO",
            "status": "ausente",
        },
    ],
}

# A 1ª fase do ITA S5, com as notas que a planilha real mostra na coluna MÉDIA
# da objetiva (5,56 para a PESSOA A e 3,61 para a PESSOA B).
ITA_S5_OBJETIVA = {
    "tipo": "simulado", "fase": "objetiva", "banca": "ITA", "rotulo": "S5",
    "data": "2026-05-09", "turma": "veterana", "fonte": None,
    "materias": ["MAT", "QUIM", "FIS", "ING"],
    "materias_media": ["MAT", "QUIM", "FIS"],
    "questoes": None,
    "resultados": [
        {
            "nome": "PESSOA A DA PLANILHA REAL", "serie": "3º ANO",
            "status": "presente",
            "acertos": {"MAT": 7, "QUIM": 7, "FIS": 6, "ING": 9},
            "media_oficial": 5.56, "geral_oficial": 29,
        },
        {
            "nome": "PESSOA B DA PLANILHA REAL", "serie": "3º ANO",
            "status": "presente",
            "acertos": {"MAT": 5, "QUIM": 4, "FIS": 4, "ING": 8},
            "media_oficial": 3.61, "geral_oficial": 21,
        },
    ],
}

# ── IME S6, 1ª fase (OBJETIVA) ────────────────────────────────────────────
# Gabarito da planilha: MAT 15 · FÍS 15 · QUÍM 10 · ACERTOS 40 · MÉDIA 10,00.
IME_S6_OBJETIVA = {
    "tipo": "simulado", "fase": "objetiva", "banca": "IME", "rotulo": "S6",
    "data": "2026-07-04", "turma": "veterana", "fonte": None,
    "materias": ["MAT", "FIS", "QUIM"],
    "materias_media": ["MAT", "FIS", "QUIM"],
    "questoes": None,  # cai no QUESTOES_PADRAO do IME — que o gabarito confirma
    "resultados": [
        {
            "nome": "PEDRO GABRIEL VERAS DE OLIVEIRA", "serie": "3º ANO",
            "status": "presente",
            "acertos": {"MAT": 11, "FIS": 11, "QUIM": 4},
            "media_oficial": 6.50, "geral_oficial": 26,
        },
        {
            "nome": "EDUARDO HENRIQUE SILVA CAVALCANTI", "serie": "CURSO",
            "status": "presente",
            "acertos": {"MAT": 8, "FIS": 5, "QUIM": 5},
            "media_oficial": 4.50, "geral_oficial": 18,
        },
    ],
}

# ── IME S6, 2ª fase (DISCURSIVA) ──────────────────────────────────────────
# Seis matérias, inclusive ING — que a crença antiga dizia ser só da objetiva.
# Título com duas datas: "11/07/2026 - 14/04/2026".
IME_S6_DISCURSIVA = {
    "tipo": "simulado", "fase": "discursiva", "banca": "IME", "rotulo": "S6",
    "data": "2026-07-11", "data_secundaria": "2026-04-14", "turma": "veterana",
    "fonte": None,
    "materias": ["MAT", "FIS", "QUIM", "PORT", "ING", "RED"],
    "materias_media": None,
    "resultados": [
        {
            "nome": "PEDRO GABRIEL VERAS DE OLIVEIRA", "serie": "3º ANO",
            "status": "presente",
            "notas": {"MAT": 5.70, "FIS": 3.50, "QUIM": 5.70,
                      "PORT": 7.00, "ING": 8.50, "RED": 6.10},
            "media_oficial": 5.56, "media_final_oficial": None,
        },
        {
            "nome": "EDUARDO HENRIQUE SILVA CAVALCANTI", "serie": "CURSO",
            "status": "presente",
            "notas": {"MAT": 4.40, "FIS": 5.10, "QUIM": 3.80,
                      "PORT": 8.00, "ING": 7.50, "RED": 4.10},
            "media_oficial": 5.10, "media_final_oficial": None,
        },
    ],
}


def _parse(payload):
    return parse(json.dumps(payload))


# --------------------------------------------------------------------------
# IME 1ª fase: a régua do app contra o gabarito da planilha
# --------------------------------------------------------------------------


def test_a_media_da_1a_fase_do_ime_bate_com_a_planilha(app, db, admin):
    """`acertos/40×10`, conferido contra os números publicados: 26→6,50 e
    18→4,50. É a conta que `SimuladoTurma.nota_de` já fazia."""
    prova = aplicar(db, _parse(IME_S6_OBJETIVA), admin.id)
    db.session.commit()

    for nome, esperada in (("PEDRO", 6.50), ("EDUARDO", 4.50)):
        linha = next(ln for ln in prova.linhas if nome in ln.nome)
        assert prova.nota_de(linha, prova.materias) == esperada
        assert linha.media_oficial == esperada, "a planilha e o app divergem"


def test_o_gabarito_do_ime_confirma_questoes_padrao(app, db, admin):
    """Gabarito: MAT 15 · FÍS 15 · QUÍM 10, total 40. O JSON veio com
    "questoes": null, então isto é o padrão da banca sendo validado."""
    prova = aplicar(db, _parse(IME_S6_OBJETIVA), admin.id)
    db.session.commit()

    assert prova.questoes == {"MATEMATICA": 15, "FISICA": 15, "QUIMICA": 10}
    assert sum(prova.questoes.values()) == 40


# --------------------------------------------------------------------------
# IME 2ª fase: importa, e NÃO opina sobre a média
# --------------------------------------------------------------------------


def test_a_2a_fase_do_ime_importa_com_seis_materias(app, db, admin):
    """Seis matérias, com ING no bloco discursivo — o que derrubou a crença de
    que Inglês distingue as fases."""
    prova = aplicar(db, _parse(IME_S6_DISCURSIVA), admin.id)
    db.session.commit()

    nomes = {m.name for m in prova.materias}
    assert nomes == {"MATEMATICA", "FISICA", "QUIMICA", "PORTUGUES",
                     "INGLES", "REDACAO"}
    linha = next(ln for ln in prova.linhas if "PEDRO" in ln.nome)
    assert linha.notas["INGLES"] == 8.50
    assert linha.media_informada == 5.56


def test_o_app_nao_confere_a_media_do_ime(app):
    """Cinco famílias de hipótese morreram contra as 12 linhas do S6. Nenhum
    aviso, para não treinar o usuário a ignorar aviso."""
    assert _parse(IME_S6_DISCURSIVA)["avisos"] == []


def test_as_duas_fases_do_ime_tem_datas_diferentes(app, db, admin):
    """04/07 e 11/07. É por isso que o pareamento das fases é por
    (banca, rotulo) e não por data."""
    aplicar(db, _parse(IME_S6_OBJETIVA), admin.id)
    aplicar(db, _parse(IME_S6_DISCURSIVA), admin.id)
    db.session.commit()

    provas = db.session.scalars(db.select(SimuladoTurma)).all()
    assert len(provas) == 2
    assert {p.data for p in provas} == {date(2026, 7, 4), date(2026, 7, 11)}
    assert {p.rotulo for p in provas} == {"S6"}


def test_a_segunda_data_do_ime_nao_e_a_da_1a_fase(app, db, admin):
    """O título da 2ª fase diz "11/07 - 14/04", mas a 1ª fase é 04/07. A
    segunda data não aponta para a outra fase — guardada e ignorada."""
    objetiva = aplicar(db, _parse(IME_S6_OBJETIVA), admin.id)
    discursiva = aplicar(db, _parse(IME_S6_DISCURSIVA), admin.id)
    db.session.commit()

    assert discursiva.data_secundaria == date(2026, 4, 14)
    assert discursiva.data_secundaria != objetiva.data


# --------------------------------------------------------------------------
# ITA 2ª fase: as fórmulas fecham, e a MÉDIA FINAL vem copiada
# --------------------------------------------------------------------------


def test_a_formula_do_ita_fecha_em_todas_as_linhas_reais(app):
    """Se alguma linha real divergisse, sairia aviso. Nenhuma diverge —
    inclusive a que zerou quase tudo (0,40/8 = 0,05)."""
    assert _parse(ITA_S5_DISCURSIVO)["avisos"] == []


def test_a_linha_zerada_da_planilha_real_entra(app, db, admin):
    """A regra da 1ª fase ("zerou em tudo → marque ausente") recusaria esta
    pessoa, que existe e tem média publicada."""
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    linha = next(ln for ln in prova.linhas if "PESSOA C" in ln.nome)
    assert linha.status == "presente"
    assert linha.notas["FISICA"] == 0.20
    assert linha.media_informada == 0.05


def test_a_media_final_vem_copiada_da_planilha(app, db, admin):
    """O caso comum: a planilha de dois blocos JÁ TRAZ a coluna. Não há nada a
    combinar — é copiar."""
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    a = next(ln for ln in prova.linhas if "PESSOA A" in ln.nome)
    assert a.media_final_informada == 5.65
    # E a média do bloco discursivo, que é OUTRO número, no campo dela:
    assert a.media_informada == 5.67

    # A PESSOA B não tem média final no material recebido — e campo sem dado
    # fica nulo, nunca preenchido por dedução.
    b = next(ln for ln in prova.linhas if "PESSOA B" in ln.nome)
    assert b.media_final_informada is None


def test_sem_coluna_de_media_final_o_campo_fica_nulo(app, db, admin):
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    c = next(ln for ln in prova.linhas if "PESSOA C" in ln.nome)
    assert c.media_final_informada is None


def test_quem_faltou_a_discursiva_atravessa_o_import(app, db, admin):
    """O colégio publicou média final para quem faltou (0,00 e 3,61 → 0,72):
    ausência entra como ZERO na conta dele. Como o número é copiado, o app não
    precisa saber disso — mas a linha tem que atravessar sem quebrar."""
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    d = next(ln for ln in prova.linhas if "PESSOA D" in ln.nome)
    assert d.status == "ausente"
    assert d.notas == {}
    assert d.media_informada is None


def test_a_ordem_das_colunas_da_planilha_e_respeitada(app, db, admin):
    """ITA S5 vem MAT · QUÍ · FIS. Ler na ordem "natural" trocaria Física com
    Química, e nenhuma validação pegaria: as duas notas são baixas e válidas, e
    a média dá o mesmo. Só apareceria meses depois, no gráfico de evolução."""
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    linha = next(ln for ln in prova.linhas if "PESSOA A" in ln.nome)
    assert linha.notas["QUIMICA"] == 6.35
    assert linha.notas["FISICA"] == 3.40
