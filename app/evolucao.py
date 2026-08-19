"""Evolução de um aluno ao longo dos simulados da turma (Fase E).

Não guarda dado novo — tudo já está em `SimuladoTurmaLinha`; só faltava juntar
os simulados de uma pessoa em ordem cronológica. `evolucao_do_aluno()` é a
única função exportada, pura (só lê o banco, não grava nada), usada tanto pela
tela do próprio usuário quanto pela tela do admin sobre qualquer aluno — mesma
consulta, outro sujeito.
"""

from .extensions import db
from .grouping import compor_titulo
from .models import Materia, SimuladoTurma, SimuladoTurmaLinha


def _materias_do_recorte(turma: "SimuladoTurma", materias) -> list["Materia"]:
    """Matérias consideradas nesta prova: o recorte pedido (Fase D), restrito
    ao que a prova mediu; sem recorte (ou recorte que não sobra nada), cai na
    régua oficial de sempre (materias_media, senão todas da prova)."""
    if materias:
        recorte = [m for m in turma.materias if m in materias]
        if recorte:
            return recorte
    return turma.materias_media or turma.materias


def _percentil(posicao, total) -> float | None:
    """100 = melhor colocação, 0 = pior. Prova com 1 presença só não tem
    variação para calcular percentil (devolve 100, já que é o único)."""
    if posicao is None or not total:
        return None
    if total <= 1:
        return 100.0
    return round(100.0 * (total - posicao) / (total - 1), 1)


def _mediana(valores: list) -> float | None:
    limpos = sorted(v for v in valores if v is not None)
    if not limpos:
        return None
    n = len(limpos)
    meio = n // 2
    if n % 2:
        return round(limpos[meio], 1)
    return round((limpos[meio - 1] + limpos[meio]) / 2, 1)


def _valor_da_materia(turma: "SimuladoTurma", linha, materia_name: str) -> float | None:
    """Desempenho numa matéria, em régua única 0–100, seja qual for a fase.

    Sem isto, a 2ª fase sumia do gráfico por matéria em SILÊNCIO: a conta era
    `100 × certas / total_questoes`, e numa linha discursiva não há nem
    `certas` nem `total_questoes`, então o ponto virava None sem erro nenhum.

    A 2ª fase já vem em 0–10, então ×10 põe as duas fases na mesma escala e o
    gráfico fica comparável — que é o ponto de um gráfico de evolução."""
    if turma.fase == "discursiva":
        nota = linha.notas.get(materia_name)
        return None if nota is None else 10.0 * nota

    total_q = turma.questoes.get(materia_name)
    certas = linha.acertos.get(materia_name)
    if not total_q or certas is None:
        return None
    return 100.0 * certas / total_q


def _mediana_materia_da_turma(turma: "SimuladoTurma", materia_name: str) -> float | None:
    valores = [
        v
        for linha in turma.presentes()
        if (v := _valor_da_materia(turma, linha, materia_name)) is not None
    ]
    return _mediana(valores)


def _tendencia(valores: list) -> dict | None:
    """Regressão linear simples sobre o índice cronológico (ignora os None)."""
    pontos = [(i, v) for i, v in enumerate(valores) if v is not None]
    if len(pontos) < 2:
        return None
    n = len(pontos)
    mx = sum(p[0] for p in pontos) / n
    my = sum(p[1] for p in pontos) / n
    denom = sum((p[0] - mx) ** 2 for p in pontos)
    if denom == 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pontos) / denom
    intercept = my - slope * mx
    return {"valores": [round(slope * i + intercept, 1) for i in range(len(valores))]}


def linhas_do_aluno_em_ordem(aluno_id: int) -> list["SimuladoTurmaLinha"]:
    """As presenças do aluno nos rankings de simulado, mais antiga primeiro."""
    return db.session.scalars(
        db.select(SimuladoTurmaLinha)
        .join(SimuladoTurma, SimuladoTurmaLinha.turma_id == SimuladoTurma.id)
        .filter(SimuladoTurmaLinha.aluno_id == aluno_id, SimuladoTurmaLinha.status == "presente")
        # Desempate explícito: as duas fases da mesma prova têm a MESMA data, e
        # sem isto a ordem entre elas ficaria por conta do banco. Objetiva
        # antes de discursiva é a ordem em que a pessoa fez as provas.
        .order_by(SimuladoTurma.data, SimuladoTurma.fase.desc())
    ).all()


def evolucao_do_aluno(aluno_id: int, materias=None) -> dict:
    """Monta a série cronológica de um aluno: posição/percentil, acertos por
    matéria, e a mediana da turma por matéria (para comparar "fui mal em
    química" com "estou X% abaixo da mediana em química").

    `materias`: recorte da Fase D (lista de Materia) ou None para "todas"."""
    linhas = linhas_do_aluno_em_ordem(aluno_id)

    # A fase entra no rótulo porque as duas fases da mesma prova compartilham
    # banca, rótulo E data: sem ela o gráfico mostraria dois pontos escritos
    # exatamente igual, e ninguém saberia qual é qual. `compor_titulo` é a
    # mesma função que nomeia o simulado pessoal, para os nomes não divergirem.
    labels = [
        f"{compor_titulo(ln.turma_obj.banca, ln.turma_obj.rotulo, ln.turma_obj.fase)}"
        f" · {ln.turma_obj.data.strftime('%d/%m/%Y')}"
        for ln in linhas
    ]

    posicoes, percentis = [], []
    for ln in linhas:
        turma = ln.turma_obj
        ranking = turma.ranking(_materias_do_recorte(turma, materias))
        total = len(ranking)
        pos = next((p for p, l, _ in ranking if l.id == ln.id), None)
        posicoes.append(pos)
        percentis.append(_percentil(pos, total))

    # União (na ordem canônica do enum) das matérias que aparecem em qualquer
    # prova, dentro do recorte — cada prova pode ter medido matérias diferentes.
    vistas = set()
    for ln in linhas:
        vistas.update(m.name for m in _materias_do_recorte(ln.turma_obj, materias))
    nomes_materia = [m.name for m in Materia if m.name in vistas]

    materias_dados = {}
    for nome in nomes_materia:
        valores, medianas = [], []
        for ln in linhas:
            turma = ln.turma_obj
            valor = _valor_da_materia(turma, ln, nome)
            valores.append(None if valor is None else round(valor, 1))
            medianas.append(_mediana_materia_da_turma(turma, nome))
        materias_dados[nome] = {
            "label": Materia[nome].value,
            "valores": valores,
            "mediana_turma": medianas,
        }

    return {
        "labels": labels,
        "percentil": {"values": percentis, "tendencia": _tendencia(percentis)},
        "posicao": {"values": posicoes},
        "materias": materias_dados,
        "tem_dado": bool(linhas),
    }
