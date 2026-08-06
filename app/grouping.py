"""Agrupamento de concursos por banca/edição, derivado do nome.

Convenção de nome: "<BANCA> <ANO>" opcionalmente seguido de " - <fase/dia>".
Ex.: "ITA 2027 - 2ª Fase, dia 1" → grupo "ITA 2027", rótulo curto "2ª Fase, dia 1".
     "AFA 2027"                  → grupo "AFA 2027", rótulo curto "AFA 2027".
O grupo é a parte antes do primeiro " - " (o app não tem campo separado de banca;
agrupar pelo nome mantém tudo funcionando com os dados que já existem).
"""

SEP = " - "


def grupo_de(nome: str) -> str:
    return nome.split(SEP, 1)[0].strip()


def rotulo_curto(nome: str) -> str:
    """Nome sem o prefixo do grupo (para não repetir dentro do optgroup)."""
    partes = nome.split(SEP, 1)
    return partes[1].strip() if len(partes) == 2 else nome


def agrupar(concursos):
    """Recebe concursos já ordenados por data_prova e devolve
    [(grupo, [concurso, ...]), ...] preservando a ordem cronológica dos grupos
    (cada grupo aparece na posição da sua prova mais próxima)."""
    grupos: dict[str, list] = {}
    for c in concursos:
        grupos.setdefault(grupo_de(c.nome), []).append(c)
    return list(grupos.items())
