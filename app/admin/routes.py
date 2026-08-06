"""Área do admin: turmas, alunos e a curadoria de identidade (merge).

Existe porque a Fase A criou o Aluno a partir dos nomes das planilhas — e nome
lido por OCR varia. A data migration cria um aluno por grafia distinta, então
duplicatas nascem junto; sem uma tela para juntá-las, a lista de turma nasce
errada. Por isso merge faz parte da mesma entrega, e não de um "depois".
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..alunos import (
    ErroMerge,
    candidatos_a_merge,
    contar_linhas,
    linhas_do_aluno,
    mesclar,
)
from ..decorators import admin_required
from ..extensions import db
from ..forms import AlunoForm
from ..models import (
    TURMA_CURTO,
    TURMAS,
    Aluno,
    AlunoApelido,
    ResultadoLinha,
    SimuladoTurmaLinha,
    normalizar_nome,
    turma_valida,
)
from ..vinculo import revincular

admin_bp = Blueprint("admin", __name__)

# Turma pode ser nula (aluno que só apareceu num listão sem turma definida).
SEM_TURMA = "sem-turma"


def _get_aluno(aluno_id: int) -> Aluno:
    aluno = db.session.get(Aluno, aluno_id)
    if aluno is None:
        abort(404)
    return aluno


def _resumo(aluno: Aluno) -> dict:
    """Números derivados do aluno.

    Calculados na hora de propósito: guardar média no Aluno desatualizaria no
    primeiro import."""
    linhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(aluno_id=aluno.id, status="presente")
    ).all()
    medias = [ln.media_oficial for ln in linhas if ln.media_oficial is not None]
    return {
        "simulados": len(linhas),
        # A média do colégio, copiada da planilha — não a métrica própria do app,
        # para o número da tela bater com o mural sem depender de fórmula nossa.
        "media": round(sum(medias) / len(medias), 2) if medias else None,
    }


@admin_bp.route("/")
@admin_required
def index():
    return redirect(url_for("admin.turmas"))


@admin_bp.route("/turmas")
@admin_required
def turmas():
    grupos = []
    for turma in TURMAS:
        total = db.session.scalar(
            db.select(db.func.count(Aluno.id)).filter_by(turma=turma)
        )
        grupos.append({"chave": turma, "nome": TURMA_CURTO[turma], "total": total})
    sem_turma = db.session.scalar(
        db.select(db.func.count(Aluno.id)).filter(Aluno.turma.is_(None))
    )
    if sem_turma:
        grupos.append(
            {"chave": SEM_TURMA, "nome": "Sem turma definida", "total": sem_turma}
        )
    return render_template(
        "admin/turmas.html",
        grupos=grupos,
        total_alunos=db.session.scalar(db.select(db.func.count(Aluno.id))),
        candidatos=len(candidatos_a_merge()),
    )


@admin_bp.route("/turmas/<turma>")
@admin_required
def alunos_da_turma(turma):
    filtro = turma_valida(turma)
    if filtro is None and turma != SEM_TURMA:
        abort(404)

    query = db.select(Aluno)
    query = query.filter(Aluno.turma.is_(None)) if filtro is None else query.filter_by(
        turma=filtro
    )
    alunos = db.session.scalars(query).all()

    itens = [{"aluno": a, **_resumo(a)} for a in alunos]
    ordem = request.args.get("ordem", "nome")
    if ordem == "media":
        # Quem não tem média vai para o fim, não para o topo.
        itens.sort(key=lambda i: (i["media"] is None, -(i["media"] or 0)))
    else:
        ordem = "nome"
        itens.sort(key=lambda i: i["aluno"].nome)

    return render_template(
        "admin/alunos.html",
        itens=itens,
        turma=filtro,
        rotulo=TURMA_CURTO[filtro] if filtro else "Sem turma definida",
        ordem=ordem,
    )


@admin_bp.route("/alunos/<int:aluno_id>", methods=["GET", "POST"])
@admin_required
def aluno_detalhe(aluno_id):
    aluno = _get_aluno(aluno_id)
    form = AlunoForm(obj=aluno)

    if form.validate_on_submit():
        chave = normalizar_nome(form.nome.data)
        conflito = db.session.scalar(
            db.select(Aluno).filter(Aluno.nome_norm == chave, Aluno.id != aluno.id)
        )
        apelido_alheio = db.session.scalar(
            db.select(AlunoApelido).filter(
                AlunoApelido.nome_norm == chave, AlunoApelido.aluno_id != aluno.id
            )
        )
        if conflito is not None or apelido_alheio is not None:
            dono = conflito or apelido_alheio.aluno
            form.nome.errors.append(
                f"Esse nome já é de {dono.nome}. Se são a mesma pessoa, use o merge."
            )
        else:
            aluno.nome = form.nome.data.strip()
            aluno.nome_norm = chave
            aluno.turma = form.turma.data or None
            aluno.serie = form.serie.data.strip() or None
            aluno.ativo = form.ativo.data
            revincular()  # o nome mudou: o vínculo pode ter mudado junto
            db.session.commit()
            flash("Aluno atualizado.", "success")
            return redirect(url_for("admin.aluno_detalhe", aluno_id=aluno.id))

    if request.method == "GET":
        form.turma.data = aluno.turma or ""

    linhas = linhas_do_aluno(aluno)
    return render_template(
        "admin/aluno.html",
        aluno=aluno,
        form=form,
        resumo=_resumo(aluno),
        linhas_ranking=sorted(
            linhas[SimuladoTurmaLinha], key=lambda ln: ln.turma_obj.data, reverse=True
        ),
        linhas_oficiais=linhas[ResultadoLinha],
    )


@admin_bp.post("/alunos/<int:aluno_id>/apelidos/<int:apelido_id>/remover")
@admin_required
def remover_apelido(aluno_id, apelido_id):
    aluno = _get_aluno(aluno_id)
    apelido = db.session.get(AlunoApelido, apelido_id)
    if apelido is None or apelido.aluno_id != aluno.id:
        abort(404)
    # Não separa as linhas de volta: elas já apontam para este aluno. Só solta a
    # grafia, para um import futuro com ela criar um aluno novo.
    db.session.delete(apelido)
    db.session.commit()
    flash(
        "Apelido removido. As linhas continuam neste aluno; um import futuro com "
        "aquela grafia vai criar um aluno separado.",
        "info",
    )
    return redirect(url_for("admin.aluno_detalhe", aluno_id=aluno.id))


@admin_bp.route("/merge", methods=["GET", "POST"])
@admin_required
def merge():
    if request.method == "POST":
        sobrevivente = db.session.get(Aluno, request.form.get("sobrevivente", type=int))
        absorvido = db.session.get(Aluno, request.form.get("absorvido", type=int))
        if sobrevivente is None or absorvido is None:
            abort(404)
        try:
            migradas = mesclar(sobrevivente, absorvido)
        except ErroMerge as exc:
            db.session.rollback()
            flash(str(exc), "error")
        else:
            revincular()
            db.session.commit()
            flash(
                f"{absorvido.nome} virou apelido de {sobrevivente.nome} — "
                f"{migradas} linha(s) migradas, nenhuma apagada.",
                "success",
            )
        return redirect(url_for("admin.merge"))

    pares = candidatos_a_merge()
    for par in pares:
        par["linhas_a"] = contar_linhas(par["a"])
        par["linhas_b"] = contar_linhas(par["b"])
    return render_template(
        "admin/merge.html",
        pares=pares,
        todos=db.session.scalars(db.select(Aluno).order_by(Aluno.nome)).all(),
    )
