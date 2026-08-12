"""Sincronização em lote: traz para o perfil todas as linhas do ranking da
turma em que o usuário aparece, sem apagar nem sobrescrever nada (Fase C).

É a versão em lote de `simulados.turma_trazer` — mesma conta de nota/posição,
mesma regra de não sobrescrever registro manual — mas percorrendo TODAS as
turmas de uma vez, em vez de uma prova por clique.

Idempotência: `Simulado.turma_linha_id` aponta para a `SimuladoTurmaLinha` que
originou o registro. `linhas_pendentes()` já exclui o que tem essa marca, então
sincronizar de novo não recria nada — não tem "atualizar", só "pular" (C.2 do
plano: nenhuma ressincronização com atualização nesta fase).

Nada aqui dá commit: quem comita é a rota, como no resto do projeto.
"""

from .extensions import db
from .grouping import banca_curta, casar_concurso
from .models import Concurso, Simulado, SimuladoMateria, SimuladoTurma, SimuladoTurmaLinha


def linhas_pendentes(user_id: int) -> list["SimuladoTurmaLinha"]:
    """Linhas do ranking em que o usuário está presente e ainda não trouxe.

    "Ainda não trouxe" = não existe Simulado do usuário com turma_linha_id
    apontando pra ela."""
    ja_trazidas = db.session.scalars(
        db.select(Simulado.turma_linha_id).filter(
            Simulado.user_id == user_id, Simulado.turma_linha_id.isnot(None)
        )
    ).all()
    query = (
        db.select(SimuladoTurmaLinha)
        .join(SimuladoTurma, SimuladoTurmaLinha.turma_id == SimuladoTurma.id)
        .filter(
            SimuladoTurmaLinha.user_id == user_id,
            SimuladoTurmaLinha.status == "presente",
        )
        .order_by(SimuladoTurma.data)
    )
    if ja_trazidas:
        query = query.filter(SimuladoTurmaLinha.id.notin_(ja_trazidas))
    return db.session.scalars(query).all()


def concursos_por_banca() -> dict:
    """{banca_curta: [Concurso, ...]} — para casar a banca da turma com concursos.

    `Concurso.banca` inclui o ano ("ITA 2027"); `SimuladoTurma.banca` não ("ITA").
    `banca_curta()` normaliza os dois lados para o mesmo token antes de comparar
    — sem isso o casamento automático nunca acontecia."""
    mapa = {}
    for concurso in db.session.scalars(db.select(Concurso).order_by(Concurso.data_prova)):
        mapa.setdefault(banca_curta(concurso.nome), []).append(concurso)
    return mapa


def sugerir_concurso(linha: "SimuladoTurmaLinha", mapa_bancas: dict) -> "Concurso | None":
    """Concurso sugerido para a linha, ou None quando continua ambíguo.

    Banca com um concurso só resolve direto; com mais de um, a fase do ranking
    desempata (objetiva → 1ª fase, discursiva → 2ª). A regra mora em
    `casar_concurso` para esta tela e a de detalhe do ranking não divergirem."""
    turma = linha.turma_obj
    candidatos = mapa_bancas.get(banca_curta(turma.banca)) or []
    return casar_concurso(candidatos, turma.banca, turma.fase)[1]


def opcoes_de_concurso(turma: "SimuladoTurma", concursos: list) -> tuple:
    """`(compativeis, outros, sugestao)` para montar o `<select>` de concurso.

    Os dois grupos juntos são sempre a lista completa: filtrar não pode impedir
    a pessoa de escolher outro concurso, só empurrar o provável para cima.
    `compativeis` vazio significa nenhuma correspondência de banca — a tela
    mostra a lista inteira, sem agrupar."""
    compativeis, sugestao = casar_concurso(concursos, turma.banca, turma.fase)
    ids = {c.id for c in compativeis}
    return compativeis, [c for c in concursos if c.id not in ids], sugestao


def valores_do_ranking(linha: "SimuladoTurmaLinha", concurso: "Concurso"):
    """O que o ranking diz HOJE sobre esta linha: `(notas, nota_geral, posicao)`.

    `notas` é [(Materia, acertos, total)] só das matérias que caem no concurso.
    Devolve None quando nenhuma matéria do concurso caiu nesta prova.

    Existe separado de `sincronizar_linha` porque a ressincronização precisa
    COMPARAR antes de gravar: se a conta ficasse só lá dentro, o preview teria
    que reimplementá-la e os dois divergiriam no primeiro ajuste de fórmula.
    """
    turma = linha.turma_obj
    permitidas = {m.name for m in concurso.materias}

    notas, percentuais = [], []
    for materia in turma.materias:
        certas = linha.acertos.get(materia.name)
        total = turma.questoes.get(materia.name)
        if certas is None or not total or materia.name not in permitidas:
            continue
        notas.append((materia, certas, total))
        percentuais.append(100.0 * certas / total)
    if not percentuais:
        return None

    nota_geral = round(sum(percentuais) / len(percentuais), 2)
    posicao = next(
        (pos for pos, ln, _ in turma.ranking([m for m, _, _ in notas]) if ln.id == linha.id),
        None,
    )
    return notas, nota_geral, posicao


def sincronizar_linha(linha: "SimuladoTurmaLinha", concurso: "Concurso", user_id: int):
    """Cria (ou reaproveita) o Simulado da linha para `concurso`. Não comita.

    Devolve None (e não mexe em nada) quando: nenhuma matéria do concurso caiu
    nesta prova, ou já existe um simulado MANUAL do usuário com o mesmo rótulo
    (nunca sobrescreve o que a pessoa digitou à mão)."""
    turma = linha.turma_obj
    calculado = valores_do_ranking(linha, concurso)
    if calculado is None:
        return None
    notas, nota_geral, posicao = calculado

    existente = db.session.scalar(
        db.select(Simulado).filter_by(user_id=user_id, rotulo=turma.rotulo)
    )
    if existente is not None and not existente.veio_de_import:
        return None  # registro manual: não toca

    simulado = existente or Simulado(user_id=user_id)
    simulado.concurso_id = concurso.id
    simulado.rotulo = turma.rotulo
    simulado.fase = turma.fase
    simulado.data_simulado = turma.data
    simulado.origem = "import"
    simulado.turma_linha_id = linha.id
    simulado.nota_geral = nota_geral
    simulado.nota_automatica = True
    simulado.posicao_estimada = posicao
    if existente is None:
        db.session.add(simulado)

    simulado.materias.clear()
    db.session.flush()
    for materia, certas, total in notas:
        simulado.materias.append(
            SimuladoMateria(materia=materia, acertos=certas, total_questoes=total)
        )
    return simulado


# --------------------------------------------------------------------------
# Ressincronização: atualizar o que já foi trazido, quando a origem mudou.
# --------------------------------------------------------------------------
#
# O "Sincronizar" só ADICIONA. Quando o admin corrige um ranking já importado
# (nome trocado, acerto digitado errado), quem já tinha trazido aquela prova
# ficava com o número velho para sempre. Isto resolve — mas com preview
# obrigatório, porque aqui se mexe em registro que JÁ ESTÁ no perfil da
# pessoa, o que é diferente de sincronizar.


def _rotulo_materia(materia) -> str:
    return materia.value


def _linha_de_origem(simulado: "Simulado"):
    """A SimuladoTurmaLinha que originou o registro, ou None.

    Busca pelo id em vez de relationship: a FK existe desde a Fase C, mas o
    modelo nunca declarou o lado inverso, e criar um agora mudaria o mapeamento
    (cascata, lazy) de uma tabela quente por uma conveniência de leitura.
    """
    if not simulado.turma_linha_id:
        return None
    return db.session.get(SimuladoTurmaLinha, simulado.turma_linha_id)


def diferencas_do_simulado(simulado: "Simulado") -> list[dict]:
    """O que mudaria neste simulado se ele fosse regravado a partir do ranking.

    Devolve [] quando nada mudou. Cada item é
    `{"campo": ..., "de": ..., "para": ...}`, pronto para a tela mostrar valor
    a valor — nunca "algo mudou".

    A `observacao` NUNCA entra: ela é do usuário, não do import.
    """
    linha = _linha_de_origem(simulado)
    if linha is None or simulado.concurso is None:
        return []
    calculado = valores_do_ranking(linha, simulado.concurso)
    if calculado is None:
        return []
    notas, nota_geral, posicao = calculado

    mudancas = []
    if round(simulado.nota_geral or 0, 2) != nota_geral:
        mudancas.append({"campo": "Nota", "de": simulado.nota_geral, "para": nota_geral})
    if simulado.posicao_estimada != posicao:
        mudancas.append(
            {"campo": "Posição", "de": simulado.posicao_estimada, "para": posicao}
        )

    atuais = {m.materia: (m.acertos, m.total_questoes) for m in simulado.materias}
    novas = {materia: (certas, total) for materia, certas, total in notas}
    for materia in sorted(set(atuais) | set(novas), key=lambda m: m.name):
        antes, depois = atuais.get(materia), novas.get(materia)
        if antes == depois:
            continue
        mudancas.append({
            "campo": _rotulo_materia(materia),
            "de": f"{antes[0]}/{antes[1]}" if antes else "—",
            "para": f"{depois[0]}/{depois[1]}" if depois else "—",
        })
    return mudancas


def simulados_desatualizados(user_id: int) -> list[dict]:
    """Simulados do usuário cuja linha de origem mudou desde que foi trazida.

    Só entra o que veio de import E ainda aponta para a linha de origem:
    registro digitado ou editado à mão não é candidato, nem por engano.
    """
    candidatos = db.session.scalars(
        db.select(Simulado)
        .filter(
            Simulado.user_id == user_id,
            Simulado.origem == "import",
            Simulado.turma_linha_id.isnot(None),
        )
        .order_by(Simulado.data_simulado.desc())
    ).all()

    saida = []
    for simulado in candidatos:
        mudancas = diferencas_do_simulado(simulado)
        if mudancas:
            saida.append({"simulado": simulado, "mudancas": mudancas})
    return saida


def ressincronizar_simulado(simulado: "Simulado") -> bool:
    """Regrava o simulado a partir da linha de origem. Não comita.

    Devolve False sem tocar em nada quando o simulado não é candidato (não veio
    de import, perdeu a linha de origem) ou quando o ranking não tem mais o que
    calcular. A `observacao` fica como está — é o único campo que o import não
    manda em registro nenhum.
    """
    linha = _linha_de_origem(simulado)
    if simulado.origem != "import" or linha is None or simulado.concurso is None:
        return False
    calculado = valores_do_ranking(linha, simulado.concurso)
    if calculado is None:
        return False
    notas, nota_geral, posicao = calculado

    simulado.nota_geral = nota_geral
    simulado.nota_automatica = True
    simulado.posicao_estimada = posicao
    simulado.materias.clear()
    db.session.flush()
    for materia, certas, total in notas:
        simulado.materias.append(
            SimuladoMateria(materia=materia, acertos=certas, total_questoes=total)
        )
    return True
