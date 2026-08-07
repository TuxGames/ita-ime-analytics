"""Exportação de dados (Fase F.2). Só leitura — nada aqui grava no banco.

Duas famílias de export:
  - `exportar_dados_usuario`: "baixar meus dados" — leitura solta, formato
    livre, pensado para o próprio usuário levar embora o que é dele.
  - `exportar_resultado_oficial` / `exportar_simulado_turma`: export do admin,
    no MESMO FORMATO que `oficiais_import.parse` / `simulado_turma_import.parse`
    aceitam — exportar e reimportar é ida e volta sem perda (requisito de
    aceite do F.2).
"""

from .extensions import db
from .models import (
    RegistroEstudo,
    ResultadoLinha,
    ResultadoOficial,
    Simulado,
    SimuladoTurma,
    SimuladoTurmaLinha,
    User,
    utcnow,
)


def exportar_dados_usuario(user: "User") -> dict:
    """{simulados, registros_estudo, resultados_oficiais, rankings_simulado}.

    "As linhas em que ele aparece" = ResultadoLinha/SimuladoTurmaLinha com
    user_id apontando para ele (F.2 do plano)."""
    simulados = db.session.scalars(db.select(Simulado).filter_by(user_id=user.id)).all()
    registros = db.session.scalars(db.select(RegistroEstudo).filter_by(user_id=user.id)).all()
    resultado_linhas = db.session.scalars(
        db.select(ResultadoLinha).filter_by(user_id=user.id)
    ).all()
    ranking_linhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(user_id=user.id)
    ).all()

    return {
        "usuario": user.username,
        "gerado_em": utcnow().isoformat(),
        "simulados": [
            {
                "concurso": s.concurso.nome,
                "rotulo": s.rotulo,
                "data_simulado": s.data_simulado.isoformat(),
                "nota_geral": s.nota_geral,
                "nota_automatica": s.nota_automatica,
                "posicao_estimada": s.posicao_estimada,
                "observacao": s.observacao,
                "origem": s.origem,
                "materias": [
                    {
                        "materia": m.materia.name,
                        "acertos": m.acertos,
                        "total_questoes": m.total_questoes,
                    }
                    for m in s.materias
                ],
            }
            for s in simulados
        ],
        "registros_estudo": [
            {
                "data": r.data.isoformat(),
                "materia": r.materia.name if r.materia else None,
                "questoes": r.questoes,
                "acertos": r.acertos,
            }
            for r in registros
        ],
        "resultados_oficiais": [
            {
                "concurso": ln.resultado.concurso_nome,
                "turma": ln.turma,
                "status": ln.status,
                "classificacao": ln.classificacao,
                "notas": ln.notas,
            }
            for ln in resultado_linhas
        ],
        "rankings_simulado": [
            {
                "prova": ln.turma_obj.nome,
                "data": ln.turma_obj.data.isoformat(),
                "turma": ln.turma,
                "status": ln.status,
                "acertos": ln.acertos,
            }
            for ln in ranking_linhas
        ],
    }


def exportar_resultado_oficial(resultado: "ResultadoOficial", turma: str) -> dict:
    """Uma turma do listão, no formato que `oficiais_import.parse` aceita."""
    linhas = [ln for ln in resultado.linhas if ln.turma == turma]
    return {
        "tipo": "oficial",
        "concurso": resultado.concurso_nome,
        "turma": turma,
        "fonte": resultado.fonte,
        "metrica": resultado.metrica,
        "data": resultado.data.isoformat() if resultado.data else None,
        "escala": resultado.escala,
        "materias": [m.name for m in resultado.materias],
        "resultados": [
            {
                "nome": ln.nome,
                "status": ln.status,
                "classificacao": ln.classificacao,
                "metrica": ln.metrica_valor,
                "notas": ln.notas,
            }
            for ln in linhas
        ],
    }


def exportar_simulado_turma(turma_obj: "SimuladoTurma", turma: str) -> dict:
    """Uma turma do ranking, no formato que `simulado_turma_import.parse` aceita."""
    linhas = [ln for ln in turma_obj.linhas if ln.turma == turma]
    return {
        "tipo": "simulado",
        "banca": turma_obj.banca,
        "rotulo": turma_obj.rotulo,
        "data": turma_obj.data.isoformat(),
        "turma": turma,
        "fonte": turma_obj.fonte,
        "fase": turma_obj.fase,
        "materias": [m.name for m in turma_obj.materias],
        "materias_media": [m.name for m in turma_obj.materias_media],
        "questoes": turma_obj.questoes,
        "resultados": [
            {
                "nome": ln.nome,
                "serie": ln.serie,
                "status": ln.status,
                "acertos": ln.acertos if ln.status == "presente" else None,
                "media_oficial": ln.media_oficial,
                "geral_oficial": ln.geral_oficial,
            }
            for ln in linhas
        ],
    }
