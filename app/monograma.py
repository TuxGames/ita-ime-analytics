"""Monograma: iniciais e cor derivadas do NOME, nunca da conta.

São 73 alunos para 7 contas de usuário. Se a identidade visual saísse do
`User`, nove em cada dez linhas do ranking ficariam sem nada e o ganho de
reconhecimento se perderia — então tudo aqui parte do nome normalizado, que
existe para todo mundo que aparece num listão.

Sem upload, sem armazenamento, sem escolha: mesma pessoa, mesma cor, sempre.
"""

import hashlib

from .models import normalizar_nome

# Partículas que não valem como sobrenome na hora de montar as iniciais.
# "MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO" -> "MC".
PARTICULAS = {
    "DE", "DA", "DO", "DAS", "DOS", "E",
    "DI", "DEL", "DELLA", "LA", "LE", "VAN", "VON", "Y",
}

# Doze cores fechadas, todas com contraste >= 4,5:1 contra texto branco (o pior
# caso é o teal, 5,47:1). A ORDEM É PARTE DO CONTRATO: mexer na posição de uma
# cor troca a cor de todo mundo que caiu nela. Para acrescentar, some no fim.
PALETA = [
    "#1D3557",  # azul do projeto
    "#B91C30",  # vermelho do projeto
    "#166534",  # verde do projeto
    "#7C2D12",  # marrom
    "#4C1D95",  # violeta
    "#0F766E",  # teal
    "#9A3412",  # laranja escuro
    "#1E40AF",  # azul vivo
    "#831843",  # vinho
    "#3F6212",  # oliva
    "#155E75",  # ciano escuro
    "#5B21B6",  # roxo
]


def _palavras(nome) -> list[str]:
    """Palavras do nome normalizado, já sem as partículas."""
    todas = normalizar_nome(nome).split()
    uteis = [p for p in todas if p not in PARTICULAS]
    # Nome que só tem partícula ("DE LA") é melhor mostrar do que engolir.
    return uteis or todas


def iniciais(nome) -> str:
    """Primeiro nome + último sobrenome. Nome de uma palavra só devolve uma letra."""
    palavras = _palavras(nome)
    if not palavras:
        return "?"
    if len(palavras) == 1:
        return palavras[0][0]
    return palavras[0][0] + palavras[-1][0]


def indice_de_cor(nome) -> int:
    """Posição na PALETA, estável entre processos e entre máquinas.

    Usa sha1 em vez do `hash()` embutido de propósito: o hash de str do Python
    é aleatorizado por processo (PYTHONHASHSEED), então a cor de cada pessoa
    mudaria a cada restart do servidor.
    """
    chave = normalizar_nome(nome).encode("utf-8")
    return int.from_bytes(hashlib.sha1(chave).digest()[:4], "big") % len(PALETA)
