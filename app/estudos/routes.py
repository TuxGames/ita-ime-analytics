from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import PlanoEstudoForm, RegistroEstudoForm, SessaoTreinoForm
from ..models import (
    DIAS_SEMANA,
    Materia,
    PlanoEstudoDia,
    RegistroEstudo,
    SessaoTreino,
)

estudos_bp = Blueprint("estudos", __name__)


def _plano_do_usuario() -> dict:
    """{weekday: [Materia, ...]} do usuário logado."""
    linhas = db.session.scalars(
        db.select(PlanoEstudoDia).filter_by(user_id=current_user.id)
    ).all()
    plano = defaultdict(list)
    for ln in linhas:
        plano[ln.dia_semana].append(ln.materia)
    # ordena cada dia pela ordem do enum
    ordem = {m: i for i, m in enumerate(Materia)}
    for dia in plano:
        plano[dia].sort(key=lambda m: ordem[m])
    return plano


def _semana_atual():
    hoje = date.today()
    inicio = hoje - timedelta(days=hoje.weekday())  # segunda desta semana
    return inicio, inicio + timedelta(days=6)


@estudos_bp.route("/")
@login_required
def index():
    hoje = date.today()
    plano = _plano_do_usuario()

    # Registros da semana atual, agregados por matéria
    ini, fim = _semana_atual()
    registros = db.session.scalars(
        db.select(RegistroEstudo)
        .filter(
            RegistroEstudo.user_id == current_user.id,
            RegistroEstudo.data >= ini,
            RegistroEstudo.data <= fim,
        )
        .order_by(RegistroEstudo.data)
    ).all()

    por_materia = {}
    for r in registros:
        acc = por_materia.setdefault(r.materia, {"questoes": 0, "acertos": 0})
        acc["questoes"] += r.questoes
        acc["acertos"] += r.acertos

    total_q = sum(v["questoes"] for v in por_materia.values())
    total_a = sum(v["acertos"] for v in por_materia.values())
    resumo = {
        "questoes": total_q,
        "acertos": total_a,
        "percentual": round(100.0 * total_a / total_q, 1) if total_q else None,
        "por_materia": [
            {
                "materia": m.value,
                "questoes": por_materia[m]["questoes"],
                "acertos": por_materia[m]["acertos"],
            }
            for m in Materia
            if m in por_materia
        ],
    }

    planejado_hoje = plano.get(hoje.weekday(), [])
    return render_template(
        "estudos/index.html",
        hoje=hoje,
        dia_semana_hoje=DIAS_SEMANA[hoje.weekday()],
        planejado_hoje=planejado_hoje,
        plano=plano,
        dias_semana=DIAS_SEMANA,
        resumo=resumo,
        semana_ini=ini,
        semana_fim=fim,
    )


@estudos_bp.route("/registrar", methods=["GET", "POST"])
@login_required
def registrar():
    form = RegistroEstudoForm()
    data_str = request.args.get("data")

    if form.validate_on_submit():
        dia = form.data.data
        for enum_name, sub in form.materia_fields():
            materia = Materia[enum_name]
            existente = db.session.scalar(
                db.select(RegistroEstudo).filter_by(
                    user_id=current_user.id, data=dia, materia=materia
                )
            )
            if sub.preenchido:
                if existente:
                    existente.questoes = sub.questoes.data
                    existente.acertos = sub.acertos.data
                else:
                    db.session.add(
                        RegistroEstudo(
                            user_id=current_user.id,
                            data=dia,
                            materia=materia,
                            questoes=sub.questoes.data,
                            acertos=sub.acertos.data,
                        )
                    )
            elif existente:
                # limpou os campos → remove o registro daquele dia/matéria
                db.session.delete(existente)
        db.session.commit()
        flash("Estudo registrado!", "success")
        return redirect(url_for("estudos.index"))

    if request.method == "GET":
        try:
            dia = date.fromisoformat(data_str) if data_str else date.today()
        except ValueError:
            dia = date.today()
        if dia > date.today():
            dia = date.today()
        form.data.data = dia
        # pré-preenche com o que já foi registrado nesse dia
        existentes = {
            r.materia.name: r
            for r in db.session.scalars(
                db.select(RegistroEstudo).filter_by(user_id=current_user.id, data=dia)
            ).all()
        }
        for enum_name, sub in form.materia_fields():
            if enum_name in existentes:
                sub.questoes.data = existentes[enum_name].questoes
                sub.acertos.data = existentes[enum_name].acertos

    return render_template("estudos/registrar.html", form=form)


@estudos_bp.route("/treino")
@login_required
def treino():
    """Cronômetro de questões. O treino roda no navegador; ao finalizar, a pessoa
    pode salvar o resumo da sessão (com matéria e observações opcionais)."""
    form = SessaoTreinoForm()
    sessoes = db.session.scalars(
        db.select(SessaoTreino)
        .filter_by(user_id=current_user.id)
        .order_by(SessaoTreino.data.desc(), SessaoTreino.created_at.desc())
        .limit(30)
    ).all()
    return render_template("estudos/treino.html", form=form, sessoes=sessoes)


@estudos_bp.route("/treino/salvar", methods=["POST"])
@login_required
def treino_salvar():
    form = SessaoTreinoForm()
    if form.validate_on_submit():
        db.session.add(
            SessaoTreino(
                user_id=current_user.id,
                data=date.today(),
                materia=form.materia_enum(),
                questoes=form.questoes.data,
                tempo_total_seg=form.tempo_total_seg.data,
                tempo_padrao_seg=form.tempo_padrao_seg.data,
                observacao=(form.observacao.data or "").strip() or None,
            )
        )
        db.session.commit()
        flash("Sessão de treino salva!", "success")
    else:
        flash("Não foi possível salvar a sessão. Tente finalizar de novo.", "error")
    return redirect(url_for("estudos.treino"))


@estudos_bp.route("/treino/<int:sessao_id>/excluir", methods=["POST"])
@login_required
def treino_excluir(sessao_id):
    sessao = db.session.get(SessaoTreino, sessao_id)
    if sessao is None or sessao.user_id != current_user.id:
        abort(404)
    db.session.delete(sessao)
    db.session.commit()
    flash("Sessão de treino excluída.", "success")
    return redirect(url_for("estudos.treino"))


@estudos_bp.route("/plano", methods=["GET", "POST"])
@login_required
def plano():
    form = PlanoEstudoForm()

    if form.validate_on_submit():
        # substitui o plano inteiro do usuário
        db.session.execute(
            db.delete(PlanoEstudoDia).where(PlanoEstudoDia.user_id == current_user.id)
        )
        for weekday, campo in form.dia_fields():
            for nome in campo.data or []:
                if nome in Materia.__members__:
                    db.session.add(
                        PlanoEstudoDia(
                            user_id=current_user.id,
                            dia_semana=weekday,
                            materia=Materia[nome],
                        )
                    )
        db.session.commit()
        flash("Plano de estudos atualizado.", "success")
        return redirect(url_for("estudos.index"))

    if request.method == "GET":
        plano = _plano_do_usuario()
        for weekday, campo in form.dia_fields():
            campo.data = [m.name for m in plano.get(weekday, [])]

    return render_template("estudos/plano.html", form=form, dias_semana=DIAS_SEMANA)
