"""Evolução do grupo: quanto cada membro estudou no período (Bloco 2).

Fontes: `RegistroEstudo` (questões feitas/acertadas, dá para calcular
percentual — volume puro premiaria quem faz muita questão fácil) e `Simulado`
(contagem no período, incluindo os trazidos do ranking da turma).

`SessaoTreino` NUNCA entra aqui: ela guarda `tempo_total_seg` na mesma linha
de `questoes`, e tempo de estudo está fora do escopo do grupo — é o vazamento
mais fácil de acontecer por conveniência, então nem é importada neste módulo.

Tudo aqui é leitura pura; nada grava no banco."""

from datetime import date, timedelta

from .extensions import db
from .models import Grupo, GrupoMembro, RegistroEstudo, Simulado, User

PERIODOS = ("semana", "30dias")


def intervalo_do_periodo(periodo: str | None) -> tuple[date, date]:
    """Sempre por período, nunca acumulado: acumulado premia quem criou conta
    primeiro. "semana" (padrão) = desta segunda até hoje; "30dias" = últimos 30."""
    hoje = date.today()
    if periodo == "30dias":
        return hoje - timedelta(days=29), hoje
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    return inicio_semana, hoje


def membros_ativos(grupo: "Grupo") -> list["GrupoMembro"]:
    """Só quem aceitou o convite — "convidado" e "saiu" não aparecem em nada."""
    return [m for m in grupo.membros if m.status == "ativo"]


def _registros_do_periodo(user_id: int, inicio: date, fim: date, materias):
    query = db.select(RegistroEstudo).filter(
        RegistroEstudo.user_id == user_id,
        RegistroEstudo.data >= inicio,
        RegistroEstudo.data <= fim,
    )
    if materias:
        query = query.filter(RegistroEstudo.materia.in_(materias))
    return db.session.scalars(query.order_by(RegistroEstudo.data)).all()


def evolucao_do_membro(user: "User", inicio: date, fim: date, materias=None) -> dict:
    """Questões por dia, percentual de acerto e nº de simulados no período —
    NUNCA tempo. É a mesma forma de dado usada no placar (`evolucao_do_grupo`),
    só muda o que a tela destaca."""
    registros = _registros_do_periodo(user.id, inicio, fim, materias)

    por_dia: dict[str, dict] = {}
    for reg in registros:
        chave = reg.data.isoformat()
        acumulado = por_dia.setdefault(chave, {"questoes": 0, "acertos": 0})
        acumulado["questoes"] += reg.questoes
        acumulado["acertos"] += reg.acertos

    dias = sorted(por_dia)
    questoes_totais = sum(v["questoes"] for v in por_dia.values())
    acertos_totais = sum(v["acertos"] for v in por_dia.values())
    percentual = (
        round(100.0 * acertos_totais / questoes_totais, 1) if questoes_totais else None
    )

    simulados_feitos = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter(
            Simulado.user_id == user.id,
            Simulado.data_simulado >= inicio,
            Simulado.data_simulado <= fim,
        )
    )

    return {
        "user_id": user.id,
        "username": user.username,
        "labels": dias,
        "questoes_por_dia": [por_dia[d]["questoes"] for d in dias],
        "questoes_totais": questoes_totais,
        "percentual_acerto": percentual,
        "simulados_feitos": simulados_feitos,
    }


def evolucao_do_grupo(grupo: "Grupo", periodo: str | None, materias=None) -> dict:
    """A evolução de cada membro ativo, mais o placar — mesma consulta, só a
    ordenação/destaque muda entre "acompanhamento" e "quem estudou mais"."""
    inicio, fim = intervalo_do_periodo(periodo)
    membros = [
        evolucao_do_membro(m.user, inicio, fim, materias) for m in membros_ativos(grupo)
    ]
    placar = sorted(membros, key=lambda m: -m["questoes_totais"])

    return {
        "periodo": periodo if periodo in PERIODOS else "semana",
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "membros": membros,
        "placar": placar,
    }
