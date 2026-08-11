"""Monograma: iniciais e cor derivadas do nome (app/monograma.py)."""

import pytest

from app.monograma import PALETA, indice_de_cor, iniciais


@pytest.mark.parametrize(
    "nome,esperado",
    [
        # O caso do backlog: partículas no meio não podem virar inicial.
        ("MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO", "MC"),
        ("ANA SILVA", "AS"),
        ("JOAO DA SILVA", "JS"),
        ("MARIA DOS SANTOS", "MS"),
        ("PEDRO E SOUZA", "PS"),
        ("LUIS VAN DER BERG", "LB"),
        # Acento e caixa vêm do normalizar_nome, não daqui.
        ("joão césar", "JC"),
        ("JOSÉ", "J"),
        # Degenerados: não pode explodir nem devolver vazio.
        ("", "?"),
        (None, "?"),
        ("   ", "?"),
        ("DE LA", "DL"),
    ],
)
def test_iniciais(nome, esperado):
    assert iniciais(nome) == esperado


def test_cor_e_deterministica():
    """Mesma pessoa, mesma cor — é o ponto do recurso."""
    nome = "MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO"
    assert indice_de_cor(nome) == indice_de_cor(nome)


def test_cor_ignora_acento_e_caixa():
    """O nome do listão e o do perfil divergem em acento; a cor não pode divergir."""
    assert indice_de_cor("joão césar") == indice_de_cor("JOAO CESAR")


def test_cor_cai_sempre_dentro_da_paleta():
    for i in range(200):
        assert 0 <= indice_de_cor(f"PESSOA NUMERO {i}") < len(PALETA)


def test_cor_nao_usa_o_hash_embutido():
    """`hash()` de str é aleatorizado por processo: a cor mudaria a cada restart
    do servidor. O valor abaixo foi gravado de uma execução e tem que se repetir
    em qualquer máquina e em qualquer processo."""
    assert indice_de_cor("ANA SILVA") == 4
    assert indice_de_cor("MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO") == 11


def test_cores_se_espalham_pela_paleta():
    """Se o hash fosse ruim, todo mundo cairia em duas ou três cores."""
    usadas = {indice_de_cor(f"ALUNO {i} DA SILVA") for i in range(100)}
    assert len(usadas) == len(PALETA)
