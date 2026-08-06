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
    """{banca_upper: [Concurso, ...]} — para casar a banca da turma com concursos."""
    mapa = {}
    for concurso in db.session.scalars(db.select(Concurso).order_by(Concurso.data_prova)):
        mapa.setdefault(concurso.banca.upper(), []).append(concurso)
    return mapa


def sugerir_concurso(linha: "SimuladoTurmaLinha", mapa_bancas: dict) -> "Concurso | None":
    """Concurso sugerido para a linha: só quando a banca casa com UM só concurso.

    Duas ou mais fases da mesma banca (ex.: ITA 1ª/2ª fase) são ambíguas — fica
    pendente de escolha manual, como o C.3 do plano pede."""
    candidatos = mapa_bancas.get(linha.turma_obj.banca.upper())
    if candidatos and len(candidatos) == 1:
        return candidatos[0]
    return None


def sincronizar_linha(linha: "SimuladoTurmaLinha", concurso: "Concurso", user_id: int):
    """Cria (ou reaproveita) o Simulado da linha para `concurso`. Não comita.

    Devolve None (e não mexe em nada) quando: nenhuma matéria do concurso caiu
    nesta prova, ou já existe um simulado MANUAL do usuário com o mesmo rótulo
    (nunca sobrescreve o que a pessoa digitou à mão)."""
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

    existente = db.session.scalar(
        db.select(Simulado).filter_by(user_id=user_id, rotulo=turma.rotulo)
    )
    if existente is not None and not existente.veio_de_import:
        return None  # registro manual: não toca

    simulado = existente or Simulado(user_id=user_id)
    simulado.concurso_id = concurso.id
    simulado.rotulo = turma.rotulo
    simulado.data_simulado = turma.data
    simulado.origem = "import"
    simulado.turma_linha_id = linha.id
    simulado.nota_geral = round(sum(percentuais) / len(percentuais), 2)
    simulado.nota_automatica = True
    simulado.posicao_estimada = next(
        (pos for pos, ln, _ in turma.ranking([m for m, _, _ in notas]) if ln.id == linha.id),
        None,
    )
    if existente is None:
        db.session.add(simulado)

    simulado.materias.clear()
    db.session.flush()
    for materia, certas, total in notas:
        simulado.materias.append(
            SimuladoMateria(materia=materia, acertos=certas, total_questoes=total)
        )
    return simulado
