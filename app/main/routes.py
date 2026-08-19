import calendar as _calendar
import json
from datetime import date

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..evolucao import evolucao_do_aluno
from ..visibilidade import so_linhas_visiveis
from ..exportacao import exportar_dados_usuario
from ..extensions import db
from ..forms import MateriasPerfilForm
from ..models import (
    Aluno,
    Concurso,
    MATERIAS_SIMULADO,
    Materia,
    ResultadoLinha,
    Simulado,
    SimuladoTurmaLinha,
    normalizar_nome,
)
from ..oficiais_import import materias_da_query
from ..vinculo import nome_ja_usado, revincular

main_bp = Blueprint("main", __name__)

_MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _calendario(ano: int, mes: int, hoje: date):
    """Grade mensal (semanas de datas, começando na segunda) com as provas marcadas."""
    provas = db.session.scalars(
        db.select(Concurso).order_by(Concurso.data_prova)
    ).all()
    por_dia = {}
    for c in provas:
        for d in c.dias_prova:
            por_dia.setdefault(d, []).append(c.nome)

    cal = _calendar.Calendar(firstweekday=0)  # 0 = segunda
    semanas = []
    for semana in cal.monthdatescalendar(ano, mes):
        linha = []
        for dia in semana:
            linha.append(
                {
                    "dia": dia.day,
                    "no_mes": dia.month == mes,
                    "hoje": dia == hoje,
                    "provas": por_dia.get(dia, []),
                }
            )
        semanas.append(linha)

    prev_mes = (date(ano, mes, 1) - _calendar.datetime.timedelta(days=1)).replace(day=1)
    prox_mes = (date(ano, mes, 28) + _calendar.datetime.timedelta(days=10)).replace(day=1)
    return {
        "titulo": f"{_MESES_PT[mes - 1]} {ano}",
        "semanas": semanas,
        "prev": f"{prev_mes.year}-{prev_mes.month:02d}",
        "prox": f"{prox_mes.year}-{prox_mes.month:02d}",
        "dias_semana": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
    }


def _linreg(xs, ys):
    """Regressão linear simples; retorna (slope, intercept) ou None se degenerada."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope, my - slope * mx


def _fmt(d: date) -> str:
    return d.strftime("%d/%m")


def _label(simulado) -> str:
    """Rótulo do simulado nos gráficos: 'S3' quando existe, senão a data."""
    return (simulado.rotulo or "").strip() or _fmt(simulado.data_simulado)


@main_bp.route("/")
@login_required
def dashboard():
    hoje = date.today()

    concurso_id = request.args.get("concurso", type=int)
    query = (
        db.select(Simulado)
        .filter_by(user_id=current_user.id)
        .order_by(Simulado.data_simulado, Simulado.id)
    )
    if concurso_id:
        query = query.filter_by(concurso_id=concurso_id)
    simulados = db.session.scalars(query).all()

    # Concursos em que o usuário tem simulados (para o filtro do dashboard)
    meus_concursos = db.session.scalars(
        db.select(Concurso)
        .join(Simulado, Simulado.concurso_id == Concurso.id)
        .filter(Simulado.user_id == current_user.id)
        .distinct()
        .order_by(Concurso.data_prova)
    ).all()

    # Alvo do countdown: concurso filtrado, senão a próxima prova futura
    if concurso_id:
        alvo = db.session.get(Concurso, concurso_id)
    else:
        alvo = db.session.scalar(
            db.select(Concurso)
            .filter(Concurso.data_prova >= hoje)
            .order_by(Concurso.data_prova)
        )
    dias_restantes = (alvo.data_prova - hoje).days if alvo else None

    # Calendário mensal (navegável por ?cal=YYYY-MM). Default: mês da próxima prova.
    cal_str = request.args.get("cal")
    cal_ano, cal_mes = None, None
    if cal_str:
        try:
            partes = cal_str.split("-")
            cal_ano, cal_mes = int(partes[0]), int(partes[1])
            if not 1 <= cal_mes <= 12:
                cal_ano = None
        except (ValueError, IndexError):
            cal_ano = None
    if cal_ano is None:
        base = alvo.data_prova if alvo else hoje
        cal_ano, cal_mes = base.year, base.month
    calendario = _calendario(cal_ano, cal_mes, hoje)

    chart_data = None
    stats = None
    if simulados:
        labels = [_label(s) for s in simulados]
        notas = [round(s.nota_geral, 2) for s in simulados]

        # Série por matéria: % de acertos, null quando o simulado não teve a matéria
        materia_datasets = []
        for materia in Materia:
            pontos = []
            tem_dado = False
            for s in simulados:
                registro = next((m for m in s.materias if m.materia == materia), None)
                if registro is not None:
                    pontos.append(registro.percentual)
                    tem_dado = True
                else:
                    pontos.append(None)
            if tem_dado:
                materia_datasets.append({"label": materia.value, "data": pontos})

        # Tendência: regressão linear da nota geral projetada até a data da prova
        ordinais = [s.data_simulado.toordinal() for s in simulados]
        reg = _linreg(ordinais, notas)
        tendencia = None
        if reg and alvo and alvo.data_prova > simulados[-1].data_simulado:
            slope, intercept = reg
            trend_labels = labels + [_fmt(alvo.data_prova)]
            trend_x = ordinais + [alvo.data_prova.toordinal()]
            tendencia = {
                "labels": trend_labels,
                "notas": notas + [None],
                "trend": [round(slope * x + intercept, 2) for x in trend_x],
                "alvo": alvo.nome,
            }

        # Evolução da posição estimada — só os simulados em que o usuário informou.
        pos_sims = [s for s in simulados if s.posicao_estimada is not None]
        posicao = None
        if pos_sims:
            posicao = {
                "labels": [_label(s) for s in pos_sims],
                "values": [s.posicao_estimada for s in pos_sims],
            }

        chart_data = {
            "posicao": posicao,
            "notas": {"labels": labels, "values": notas},
            "materias": {"labels": labels, "datasets": materia_datasets},
            "tendencia": tendencia,
        }
        stats = {
            "total": len(simulados),
            "ultima": notas[-1],
            "melhor": max(notas),
            "ritmo_semana": round(reg[0] * 7, 1) if reg else None,
        }

    return render_template(
        "dashboard.html",
        simulados=simulados,
        meus_concursos=meus_concursos,
        concurso_id=concurso_id,
        alvo=alvo,
        dias_restantes=dias_restantes,
        calendario=calendario,
        chart_data=chart_data,
        stats=stats,
    )


@main_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    total_simulados = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter_by(user_id=current_user.id)
    )
    materias_form = MateriasPerfilForm()

    if request.form.get("acao") == "materias" and materias_form.validate_on_submit():
        current_user.set_materias([Materia[n] for n in materias_form.materias.data or []])
        db.session.commit()
        flash("Matérias do perfil atualizadas.", "success")
        return redirect(url_for("main.perfil"))

    # O campo "meu nome nas listas" saiu: o vínculo conta ↔ aluno passa a sair só
    # do código de convite ou da mão do admin. Sem entrada nova de
    # `nome_oficial`, nenhum vínculo por nome pode nascer — o casamento
    # automático morre por falta de entrada, e `revincular()` fica intocado
    # para não desligar quem já está ligado.
    if request.method == "GET":
        materias_form.materias.data = [m.name for m in current_user.materias]

    aluno_vinculado = db.session.scalar(
        db.select(Aluno).filter(Aluno.user_id == current_user.id)
    )

    total_oficiais = db.session.scalar(
        db.select(db.func.count(ResultadoLinha.id)).filter_by(user_id=current_user.id)
    )
    total_rankings = db.session.scalar(
        # Até a CONTAGEM vaza: "você aparece em 4 rankings" com 3 visíveis
        # conta que existe um quarto.
        so_linhas_visiveis(
            db.select(db.func.count(SimuladoTurmaLinha.id)).filter_by(
                user_id=current_user.id
            )
        )
    )
    return render_template(
        "perfil.html",
        total_simulados=total_simulados,
        aluno_vinculado=aluno_vinculado,
        materias_form=materias_form,
        total_oficiais=total_oficiais,
        total_rankings=total_rankings,
    )


@main_bp.route("/evolucao")
@login_required
def evolucao():
    """Evolução do próprio usuário ao longo dos simulados da turma (Fase E).

    Respeita o mesmo filtro de matérias do ranking (Fase D): ?materias=... ou,
    sem query, o recorte do perfil."""
    aluno = db.session.scalar(db.select(Aluno).filter_by(user_id=current_user.id))
    recorte = materias_da_query(request.args.get("materias"), MATERIAS_SIMULADO)
    if recorte is None:
        recorte = current_user.materias or None

    dados = evolucao_do_aluno(aluno.id, recorte) if aluno else None
    return render_template(
        "evolucao.html",
        titulo=f"Evolução — {current_user.username}",
        dados_js=dados,
        voltar_url=url_for("main.dashboard"),
    )


@main_bp.route("/meus-dados")
@login_required
def baixar_meus_dados():
    """"Baixar meus dados" (Fase F.2): simulados, registros de estudo e as
    linhas em que o usuário aparece, num JSON só para leitura."""
    dados = exportar_dados_usuario(current_user)
    corpo = json.dumps(dados, ensure_ascii=False, indent=2)
    resposta = Response(corpo, mimetype="application/json")
    resposta.headers["Content-Disposition"] = (
        f'attachment; filename="itaime-{current_user.username}.json"'
    )
    return resposta


@main_bp.route("/termos")
def termos():
    """Termos de uso e aviso de privacidade. PÚBLICA, sem login.

    Sem `@login_required` de propósito: o caso central é a seção 5 — alguém que
    aparece num ranking importado, nunca criou conta aqui e quer entender o que
    o site faz com o nome dele. Exigir conta para ler isso seria exatamente o
    contrário do que o texto promete.
    """
    return render_template("termos.html")
