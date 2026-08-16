"""Área do professor: ficha do aluno. SÓ LEITURA, e só nota.

Papel distinto de admin: aqui não se importa, não se edita, não se apaga, não
se emite código e não se mescla aluno. O que o professor vê é o desempenho —
simulados e oficiais —, nunca estudo, treino ou registro de questões.
"""

from flask import Blueprint, abort, render_template, request

from ..decorators import professor_required
from ..extensions import db
from ..ficha import alunos_para_ficha, ficha_do_aluno
from ..models import MATERIAS_SIMULADO, Aluno
from ..oficiais_import import materias_da_query

professor_bp = Blueprint("professor", __name__)


@professor_bp.route("/")
@professor_required
def index():
    """Escolha do aluno. Só nome, turma e série — nada de desempenho aqui."""
    return render_template("professor/index.html", alunos=alunos_para_ficha())


@professor_bp.route("/aluno/<int:aluno_id>")
@professor_required
def ficha(aluno_id):
    aluno = db.session.get(Aluno, aluno_id)
    if aluno is None:
        abort(404)

    recorte = materias_da_query(request.args.get("materias"), MATERIAS_SIMULADO)
    return render_template("professor/ficha.html", ficha=ficha_do_aluno(aluno, recorte))
