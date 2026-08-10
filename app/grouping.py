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


# Fase do ranking (SimuladoTurma.fase) → como a etapa aparece no nome do
# concurso. "objetiva" é a 1ª fase; "discursiva", a 2ª. Comparado normalizado,
# então "1ª Fase", "1a fase" e "1ª FASE" contam como a mesma coisa.
FASE_ETAPA = {"objetiva": "1A FASE", "discursiva": "2A FASE"}


def etapa_casa_fase(etapa: str, fase: str | None) -> bool:
    """A etapa do concurso corresponde à fase do ranking?

    Compara por prefixo para "2ª Fase, dia 1" continuar casando com a
    discursiva. Etapa vazia ("AFA") e etapa de dia ("Dia 1", "Dia 2") nunca
    casam: essas bancas não têm noção de 1ª/2ª fase, e aí quem decide é o
    filtro por banca."""
    from .models import normalizar_nome

    alvo = FASE_ETAPA.get(fase or "")
    if not alvo or not etapa:
        return False
    return normalizar_nome(etapa).startswith(alvo)


def casar_concurso(concursos, banca: str, fase: str | None = None):
    """Devolve `(compativeis, sugestao)` para um ranking de turma.

    - `compativeis`: os concursos da mesma banca do ranking, na ordem recebida.
      Vem vazio quando nenhum concurso é dessa banca — aí a tela mostra a lista
      inteira, como antes.
    - `sugestao`: o concurso a pré-selecionar, ou None quando continua ambíguo.

    A fase desempata dentro da banca: com vários concursos da mesma banca
    (o caso de produção — "IME - 1ª Fase" e "IME - 2ª Fase"), só é sugerido o
    que tiver a etapa correspondente, e só se for um único. Sem isso o
    `<select>` vinha com o primeiro concurso da lista, que quase nunca é o
    certo, e um toque distraído arquivava o simulado no concurso errado."""
    alvo = banca_curta(banca or "")
    if not alvo:
        return [], None
    por_banca = [c for c in concursos if banca_curta(c.nome) == alvo]
    if not por_banca:
        return [], None

    por_fase = [c for c in por_banca if etapa_casa_fase(c.etapa, fase)]
    if len(por_fase) == 1:
        return por_banca, por_fase[0]
    # Banca com um concurso só continua resolvendo sozinha (comportamento do
    # Bloco 1); mais de um sem fase que desempate fica para escolha manual.
    if len(por_banca) == 1:
        return por_banca, por_banca[0]
    return por_banca, None


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
