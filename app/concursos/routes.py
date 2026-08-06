from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..decorators import admin_required
from ..extensions import db
from ..forms import ConcursoForm
from ..grouping import agrupar
from ..models import MATERIAS_PRINCIPAIS, Concurso, Simulado

concursos_bp = Blueprint("concursos", __name__)


@concursos_bp.route("/")
@login_required
def listar():
    concursos = db.session.scalars(
        db.select(Concurso).order_by(Concurso.data_prova)
    ).all()
    hoje = date.today()
    meus_totais = dict(
        db.session.execute(
            db.select(Simulado.concurso_id, db.func.count(Simulado.id))
            .filter_by(user_id=current_user.id)
            .group_by(Simulado.concurso_id)
        ).all()
    )
    grupos = agrupar(concursos)
    return render_template(
        "concursos/list.html",
        grupos=grupos,
        total=len(concursos),
        hoje=hoje,
        meus_totais=meus_totais,
    )


def _bancas_existentes():
    """Bancas já cadastradas (para o datalist do campo Banca)."""
    concursos = db.session.scalars(db.select(Concurso).order_by(Concurso.data_prova)).all()
    vistas, out = set(), []
    for c in concursos:
        if c.banca not in vistas:
            vistas.add(c.banca)
            out.append(c.banca)
    return out


@concursos_bp.route("/novo", methods=["GET", "POST"])
@admin_required
def novo():
    form = ConcursoForm()
    if request.method == "GET":
        # Novo concurso: marca as principais por padrão
        form.load_materias(MATERIAS_PRINCIPAIS)
    if form.validate_on_submit():
        nome = form.nome_composto()
        existente = db.session.scalar(db.select(Concurso).filter_by(nome=nome))
        if existente:
            form.etapa.errors.append("Já existe um concurso com essa banca + fase.")
        else:
            concurso = Concurso(
                nome=nome,
                data_prova=form.data_prova.data,
                data_fim=form.data_fim.data or None,
                created_by=current_user.id,
            )
            concurso.set_materias(form.selected_materias())
            db.session.add(concurso)
            db.session.commit()
            flash("Concurso criado.", "success")
            return redirect(url_for("concursos.listar"))
    return render_template(
        "concursos/form.html",
        form=form,
        titulo="Novo concurso",
        bancas=_bancas_existentes(),
    )


@concursos_bp.route("/<int:concurso_id>/editar", methods=["GET", "POST"])
@admin_required
def editar(concurso_id):
    concurso = db.session.get(Concurso, concurso_id)
    if concurso is None:
        abort(404)
    form = ConcursoForm(obj=concurso)
    if request.method == "GET":
        form.load_materias(concurso.materias)
    if form.validate_on_submit():
        nome = form.nome_composto()
        duplicado = db.session.scalar(
            db.select(Concurso).filter(
                Concurso.nome == nome, Concurso.id != concurso.id
            )
        )
        if duplicado:
            form.etapa.errors.append("Já existe um concurso com essa banca + fase.")
        else:
            concurso.nome = nome
            concurso.data_prova = form.data_prova.data
            concurso.data_fim = form.data_fim.data or None
            concurso.set_materias(form.selected_materias())
            db.session.commit()
            flash("Concurso atualizado.", "success")
            return redirect(url_for("concursos.listar"))
    return render_template(
        "concursos/form.html",
        form=form,
        titulo="Editar concurso",
        concurso=concurso,
        bancas=_bancas_existentes(),
    )


@concursos_bp.post("/<int:concurso_id>/deletar")
@admin_required
def deletar(concurso_id):
    concurso = db.session.get(Concurso, concurso_id)
    if concurso is None:
        abort(404)
    tem_simulados = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter_by(concurso_id=concurso.id)
    )
    if tem_simulados:
        flash("Não dá para excluir: há simulados registrados nesse concurso.", "error")
        return redirect(url_for("concursos.listar"))
    db.session.delete(concurso)
    db.session.commit()
    flash("Concurso excluído.", "success")
    return redirect(url_for("concursos.listar"))
