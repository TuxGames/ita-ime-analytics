from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..decorators import bloqueado_para_professor
from ..extensions import db
from ..forms import ConvidarMembroForm, GrupoEdicaoForm, GrupoForm
from ..grupo_evolucao import PERIODOS, evolucao_do_grupo, ranking_de_notas
from ..models import MATERIAS_SIMULADO, Grupo, GrupoMembro, User, utcnow
from ..oficiais_import import materias_da_query

grupos_bp = Blueprint("grupos", __name__)


def _meu_vinculo(grupo: "Grupo") -> "GrupoMembro | None":
    return next((m for m in grupo.membros if m.user_id == current_user.id), None)


def _get_grupo_visivel(grupo_id: int) -> tuple["Grupo", "GrupoMembro"]:
    """Carrega o grupo só se o usuário tiver algum vínculo com ele (dono,
    convidado ou ativo). "saiu" ou nenhum vínculo -> 404 (não confirma nem
    nega a existência do grupo para quem nunca fez parte dele)."""
    grupo = db.session.get(Grupo, grupo_id)
    if grupo is None:
        abort(404)
    vinculo = _meu_vinculo(grupo)
    if vinculo is None or vinculo.status == "saiu":
        abort(404)
    return grupo, vinculo


@grupos_bp.route("/")
@login_required
@bloqueado_para_professor
def listar():
    vinculos = db.session.scalars(
        db.select(GrupoMembro)
        .filter(GrupoMembro.user_id == current_user.id, GrupoMembro.status != "saiu")
        .order_by(GrupoMembro.status, GrupoMembro.convidado_em.desc())
    ).all()
    return render_template("grupos/listar.html", vinculos=vinculos)


@grupos_bp.route("/novo", methods=["GET", "POST"])
@login_required
@bloqueado_para_professor
def novo():
    form = GrupoForm()
    if form.validate_on_submit():
        grupo = Grupo(nome=form.nome.data.strip(), criado_por=current_user.id)
        db.session.add(grupo)
        db.session.flush()
        # O dono já entra como membro ativo — não faz sentido ele se convidar.
        db.session.add(
            GrupoMembro(
                grupo_id=grupo.id,
                user_id=current_user.id,
                status="ativo",
                convidado_em=utcnow(),
                respondido_em=utcnow(),
            )
        )
        db.session.commit()
        flash(f'Grupo "{grupo.nome}" criado.', "success")
        return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))
    return render_template("grupos/form.html", form=form)


@grupos_bp.route("/<int:grupo_id>")
@login_required
@bloqueado_para_professor
def detalhe(grupo_id):
    grupo, vinculo = _get_grupo_visivel(grupo_id)

    if vinculo.status == "convidado":
        return render_template("grupos/convite.html", grupo=grupo)

    periodo = request.args.get("periodo")
    if periodo not in PERIODOS:
        periodo = None  # cai no padrão (semana) dentro de evolucao_do_grupo

    recorte = materias_da_query(request.args.get("materias"), MATERIAS_SIMULADO)
    if recorte is None:
        recorte = current_user.materias or None

    dados_js = evolucao_do_grupo(grupo, periodo, recorte)
    eh_dono = grupo.criado_por == current_user.id
    convidar_form = ConvidarMembroForm() if eh_dono else None
    # Placar de notas só existe quando o dono liga; desligado, a tela fica
    # exatamente como era (evolução e volume de questões).
    notas = ranking_de_notas(grupo, periodo, recorte) if grupo.mostrar_ranking else None

    return render_template(
        "grupos/detalhe.html",
        grupo=grupo,
        eh_dono=eh_dono,
        dados_js=dados_js,
        periodo=dados_js["periodo"],
        convidar_form=convidar_form,
        notas=notas,
        membros=[m for m in grupo.membros if m.status != "saiu"],
    )


@grupos_bp.route("/<int:grupo_id>/editar", methods=["GET", "POST"])
@login_required
@bloqueado_para_professor
def editar(grupo_id):
    """Só o dono renomeia. Mesma validação da criação (o form é o mesmo), e sem
    histórico de nomes: o nome atual é a única verdade."""
    grupo, _ = _get_grupo_visivel(grupo_id)
    if grupo.criado_por != current_user.id:
        abort(403)

    form = GrupoEdicaoForm(obj=grupo)
    if form.validate_on_submit():
        grupo.nome = form.nome.data.strip()
        grupo.mostrar_ranking = bool(form.mostrar_ranking.data)
        db.session.commit()
        flash("Grupo atualizado.", "success")
        return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))

    return render_template("grupos/editar.html", form=form, grupo=grupo)


@grupos_bp.post("/<int:grupo_id>/convidar")
@login_required
@bloqueado_para_professor
def convidar(grupo_id):
    grupo, vinculo = _get_grupo_visivel(grupo_id)
    if grupo.criado_por != current_user.id:
        abort(403)

    form = ConvidarMembroForm()
    if not form.validate_on_submit():
        flash("Informe um usuário válido para convidar.", "error")
        return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))

    usuario = db.session.scalar(
        db.select(User).filter_by(username=form.username.data.strip())
    )
    if usuario is None:
        flash("Não achei esse usuário.", "error")
        return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))

    membro = next((m for m in grupo.membros if m.user_id == usuario.id), None)
    if membro is not None and membro.status == "ativo":
        flash(f"{usuario.username} já é membro do grupo.", "info")
        return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))

    if membro is None:
        db.session.add(
            GrupoMembro(
                grupo_id=grupo.id, user_id=usuario.id, status="convidado",
                convidado_em=utcnow(),
            )
        )
    else:
        # Já foi convidado antes (recusou ou saiu) — reabre o convite em vez
        # de violar o UNIQUE (grupo_id, user_id) tentando inserir de novo.
        membro.status = "convidado"
        membro.convidado_em = utcnow()
        membro.respondido_em = None

    db.session.commit()
    flash(f"{usuario.username} convidado.", "success")
    return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))


@grupos_bp.post("/<int:grupo_id>/aceitar")
@login_required
@bloqueado_para_professor
def aceitar(grupo_id):
    grupo, vinculo = _get_grupo_visivel(grupo_id)
    if vinculo.status != "convidado":
        abort(404)
    vinculo.status = "ativo"
    vinculo.respondido_em = utcnow()
    db.session.commit()
    flash(f'Você entrou no grupo "{grupo.nome}".', "success")
    return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))


@grupos_bp.post("/<int:grupo_id>/recusar")
@login_required
@bloqueado_para_professor
def recusar(grupo_id):
    grupo, vinculo = _get_grupo_visivel(grupo_id)
    if vinculo.status != "convidado":
        abort(404)
    vinculo.status = "saiu"
    vinculo.respondido_em = utcnow()
    db.session.commit()
    flash(f'Convite para "{grupo.nome}" recusado.', "info")
    return redirect(url_for("grupos.listar"))


@grupos_bp.post("/<int:grupo_id>/sair")
@login_required
@bloqueado_para_professor
def sair(grupo_id):
    grupo, vinculo = _get_grupo_visivel(grupo_id)
    vinculo.status = "saiu"
    vinculo.respondido_em = utcnow()
    db.session.commit()
    flash(f'Você saiu de "{grupo.nome}". Seus dados de estudo não foram tocados.', "info")
    return redirect(url_for("grupos.listar"))


@grupos_bp.post("/<int:grupo_id>/membro/<int:membro_id>/remover")
@login_required
@bloqueado_para_professor
def remover_membro(grupo_id, membro_id):
    grupo, _vinculo = _get_grupo_visivel(grupo_id)
    if grupo.criado_por != current_user.id:
        abort(403)
    membro = db.session.get(GrupoMembro, membro_id)
    if membro is None or membro.grupo_id != grupo.id:
        abort(404)
    if membro.user_id == current_user.id:
        flash("Use \"Apagar grupo\" para se desfazer do seu próprio grupo.", "error")
        return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))
    db.session.delete(membro)
    db.session.commit()
    flash("Membro removido.", "success")
    return redirect(url_for("grupos.detalhe", grupo_id=grupo.id))


@grupos_bp.post("/<int:grupo_id>/apagar")
@login_required
@bloqueado_para_professor
def apagar(grupo_id):
    grupo, _vinculo = _get_grupo_visivel(grupo_id)
    if grupo.criado_por != current_user.id:
        abort(403)
    nome = grupo.nome
    # cascade="all, delete-orphan" em Grupo.membros só remove GrupoMembro —
    # RegistroEstudo, Simulado e SessaoTreino não têm FK para cá.
    db.session.delete(grupo)
    db.session.commit()
    flash(f'Grupo "{nome}" apagado. Nenhum dado de estudo foi removido.', "success")
    return redirect(url_for("grupos.listar"))
