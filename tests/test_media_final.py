"""Média final: copiada primeiro, calculada só em último caso, IME nunca.

Todas as chamadas passam `admin` porque a 2ª fase é RESERVADA ao admin enquanto
a coordenação não confirmar como o colégio calcula — ver app/visibilidade.py.
Para qualquer outra conta a resposta é None, e `tests/test_2fase_so_admin.py` é
quem trava isso.

A regra em uma frase: se a planilha traz a coluna MÉDIA FINAL, é esse número e
acabou. O cálculo existe como plano B para planilha que não traga — e quando
ele roda, a tela precisa dizer que aquilo é calculado.

Por que a ordem importa: o colégio pode mudar o peso sem avisar. No dia em que
mudar, o copiado continua certo e o calculado passa a mentir em silêncio,
porque continua parecendo um número plausível.
"""

import json

import pytest

from app.media_final import media_final_da_linha
from app.simulado_turma_import import aplicar, parse

from .test_planilhas_reais import (
    IME_S6_DISCURSIVA,
    IME_S6_OBJETIVA,
    ITA_S5_DISCURSIVO,
    ITA_S5_OBJETIVA,
)


def _parse(payload):
    return parse(json.dumps(payload))


def _sem_coluna_final(payload):
    """A mesma planilha, mas sem a coluna MÉDIA FINAL — o caso do plano B."""
    copia = json.loads(json.dumps(payload))
    for r in copia["resultados"]:
        r.pop("media_final_oficial", None)
    return copia


def _linha(prova, nome_parcial):
    return next(ln for ln in prova.linhas if nome_parcial in ln.nome)


# --------------------------------------------------------------------------
# Caso 1: a planilha traz a coluna — é copiar, e acabou
# --------------------------------------------------------------------------


def test_media_final_da_planilha_e_copiada(app, db, admin):
    """O caso COMUM: a planilha de dois blocos do ITA S5 já traz a coluna."""
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PESSOA A"), admin) == (5.65, "copiada")
    # A PESSOA B não tem média final conhecida no material recebido — e sem a
    # outra fase importada não há como calcular. None é a resposta honesta.
    assert media_final_da_linha(_linha(prova, "PESSOA B"), admin) is None


def test_a_copiada_ganha_mesmo_com_as_duas_fases_importadas(app, db, admin):
    """Tendo as duas fases, dava para calcular. Não se calcula: o número do
    colégio manda, e o cálculo nem é tentado."""
    aplicar(db, _parse(ITA_S5_OBJETIVA), admin.id)
    prova = aplicar(db, _parse(ITA_S5_DISCURSIVO), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PESSOA A"), admin) == (5.65, "copiada")


def test_a_copiada_ganha_mesmo_se_discordar_da_formula(app, db, admin):
    """Se o colégio mudar o peso, a conta passa a divergir — e o número dele
    continua sendo o certo. Este teste trava exatamente esse dia."""
    payload = json.loads(json.dumps(ITA_S5_DISCURSIVO))
    payload["resultados"][0]["media_final_oficial"] = 9.99
    aplicar(db, _parse(ITA_S5_OBJETIVA), admin.id)
    prova = aplicar(db, _parse(payload), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PESSOA A"), admin) == (9.99, "copiada")


# --------------------------------------------------------------------------
# Caso 2: sem a coluna, ITA, duas fases — calcula e AVISA que calculou
# --------------------------------------------------------------------------


def test_sem_a_coluna_calcula_e_marca_como_calculada(app, db, admin):
    """0,8 × 5,67 + 0,2 × 5,56 = 5,65 — o mesmo número que a planilha publica,
    o que é a evidência de que o plano B está certo."""
    aplicar(db, _parse(ITA_S5_OBJETIVA), admin.id)
    prova = aplicar(db, _parse(_sem_coluna_final(ITA_S5_DISCURSIVO)), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PESSOA A"), admin) == (5.65, "calculada")
    # 0,8 × 4,49 + 0,2 × 3,61 = 4,31. Aqui a conta é do app, não da planilha:
    # esta pessoa não tem média final publicada no material recebido.
    assert media_final_da_linha(_linha(prova, "PESSOA B"), admin) == (4.31, "calculada")


def test_sem_a_outra_fase_nao_calcula_nada(app, db, admin):
    """Com uma fase só não há o que combinar — e inventar seria pior que nada."""
    prova = aplicar(db, _parse(_sem_coluna_final(ITA_S5_DISCURSIVO)), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PESSOA A"), admin) is None


def test_quem_nao_esta_na_outra_lista_nao_recebe_calculo(app, db, admin):
    """Não estar na lista é diferente de ter faltado: faltou vale zero, não
    estar não permite afirmar nada."""
    aplicar(db, _parse(ITA_S5_OBJETIVA), admin.id)
    prova = aplicar(db, _parse(_sem_coluna_final(ITA_S5_DISCURSIVO)), admin.id)
    db.session.commit()

    # PESSOA C só existe no bloco discursivo.
    assert media_final_da_linha(_linha(prova, "PESSOA C"), admin) is None


def test_ausente_na_discursiva_entra_como_zero(app, db, admin):
    """A planilha real prova: quem faltou recebeu média final (0,00 e 3,61 →
    0,72). Ausência vale ZERO, não "não conta"."""
    objetiva = json.loads(json.dumps(ITA_S5_OBJETIVA))
    objetiva["resultados"].append({
        "nome": "PESSOA D DA PLANILHA REAL", "serie": "3º ANO",
        "status": "presente",
        "acertos": {"MAT": 5, "QUIM": 4, "FIS": 4, "ING": 8},
        "media_oficial": 3.61, "geral_oficial": 21,
    })
    aplicar(db, _parse(objetiva), admin.id)
    prova = aplicar(db, _parse(_sem_coluna_final(ITA_S5_DISCURSIVO)), admin.id)
    db.session.commit()

    # 0,8 × 0 + 0,2 × 3,61 = 0,72 — o número que a planilha mostra.
    assert media_final_da_linha(_linha(prova, "PESSOA D"), admin) == (0.72, "calculada")


# --------------------------------------------------------------------------
# Caso 3: IME nunca
# --------------------------------------------------------------------------


def test_o_ime_nunca_recebe_media_final_calculada(app, db, admin):
    """Cinco famílias de hipótese morreram contra as 12 linhas do S6."""
    aplicar(db, _parse(IME_S6_OBJETIVA), admin.id)
    prova = aplicar(db, _parse(IME_S6_DISCURSIVA), admin.id)
    db.session.commit()

    for nome in ("PEDRO", "EDUARDO"):
        assert media_final_da_linha(_linha(prova, nome), admin) is None


def test_o_ime_ainda_exibe_a_coluna_se_a_planilha_trouxer(app, db, admin):
    """Não calcular não é o mesmo que não mostrar: se um dia a planilha do IME
    trouxer MÉDIA FINAL explícita, o número dela vale."""
    payload = json.loads(json.dumps(IME_S6_DISCURSIVA))
    payload["resultados"][0]["media_final_oficial"] = 4.87
    prova = aplicar(db, _parse(payload), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PEDRO"), admin) == (4.87, "copiada")


def test_a_1a_fase_nao_tem_media_final(app, db, admin):
    """A média final é da 2ª fase, onde a planilha a publica."""
    prova = aplicar(db, _parse(ITA_S5_OBJETIVA), admin.id)
    db.session.commit()

    assert media_final_da_linha(_linha(prova, "PESSOA A"), admin) is None


# --------------------------------------------------------------------------
# A tela precisa distinguir as duas
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "com_coluna,esperado",
    [(True, "final 5.65"), (False, "(calculada)")],
)
def test_a_tela_diz_se_o_numero_e_calculado(
    com_coluna, esperado, client, db, admin, logar
):
    """Sem o rótulo, um número de fórmula observada passa por número oficial do
    colégio — que é exatamente o erro que custou uma versão inteira antes."""
    aplicar(db, _parse(ITA_S5_OBJETIVA), admin.id)
    payload = ITA_S5_DISCURSIVO if com_coluna else _sem_coluna_final(ITA_S5_DISCURSIVO)
    prova = aplicar(db, _parse(payload), admin.id)
    db.session.commit()
    logar(admin)

    corpo = client.get(f"/simulados/turma/{prova.id}").get_data(as_text=True)

    assert esperado in corpo
    if com_coluna:
        # A PESSOA A veio copiada; nenhum "(calculada)" pode aparecer nela.
        trecho = corpo[corpo.index("PESSOA A"):corpo.index("PESSOA A") + 1200]
        assert "(calculada)" not in trecho
