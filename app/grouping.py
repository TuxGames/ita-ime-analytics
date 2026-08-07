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


def banca_curta(texto: str) -> str:
    """Só a banca, sem ano nem fase: "ITA 2027" e "ITA" viram "ITA".

    Casa o "ITA"/"IME" que vem solto no ranking do simulado (SimuladoTurma.banca)
    com o "ITA 2027" que sai de Concurso.banca (nome fatiado em SEP) — sem isso a
    sincronização em lote nunca casava nada automaticamente."""
    from .models import normalizar_nome

    primeiro_token = grupo_de(texto or "").split()[:1]
    return normalizar_nome(primeiro_token[0]) if primeiro_token else ""


def rotulo_curto(nome: str) -> str:
    """Nome sem o prefixo do grupo (para não repetir dentro do optgroup)."""
    partes = nome.split(SEP, 1)
    return partes[1].strip() if len(partes) == 2 else nome


def compor_titulo(banca_texto: str, rotulo: str | None, fase: str | None = None) -> str:
    """"ITA S5 · 1ª fase" — banca curta + rótulo + fase, cada pedaço opcional.

    Usada tanto por `Simulado.titulo_curto` (via concurso.nome) quanto pelo
    preview da sincronização (via SimuladoTurma.banca), para o título nunca
    divergir entre as duas telas."""
    from .models import FASE_LABEL

    partes = [banca_curta(banca_texto)]
    if rotulo:
        partes.append(rotulo)
    titulo = " ".join(p for p in partes if p)
    label = FASE_LABEL.get(fase) if fase else None
    if label:
        titulo += f" · {label}"
    return titulo


def agrupar(concursos):
    """Recebe concursos já ordenados por data_prova e devolve
    [(grupo, [concurso, ...]), ...] preservando a ordem cronológica dos grupos
    (cada grupo aparece na posição da sua prova mais próxima)."""
    grupos: dict[str, list] = {}
    for c in concursos:
        grupos.setdefault(grupo_de(c.nome), []).append(c)
    return list(grupos.items())
