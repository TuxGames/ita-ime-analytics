"""grouping.py: derivação de banca/título a partir do nome do Concurso (Bloco 1)."""

from app.grouping import banca_curta, compor_titulo


def test_banca_curta_ignora_ano_e_fase():
    assert banca_curta("ITA 2027") == "ITA"
    assert banca_curta("ITA 2027 - 2ª Fase") == "ITA"
    assert banca_curta("ITA") == "ITA"


def test_banca_curta_normaliza_acento_e_caixa():
    assert banca_curta("ime 2027") == "IME"
    assert banca_curta("Época 2027") == "EPOCA"


def test_banca_curta_texto_vazio():
    assert banca_curta("") == ""
    assert banca_curta(None) == ""


def test_compor_titulo_com_fase():
    assert compor_titulo("ITA 2027", "S5", "objetiva") == "ITA S5 · 1ª fase"
    assert compor_titulo("IME 2027", "S6", "objetiva") == "IME S6 · 1ª fase"


def test_compor_titulo_sem_fase():
    assert compor_titulo("ITA 2027", "S3", None) == "ITA S3"


def test_compor_titulo_sem_rotulo():
    assert compor_titulo("ITA 2027", None, None) == "ITA"
