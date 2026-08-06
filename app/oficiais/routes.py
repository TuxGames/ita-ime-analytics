import os

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..decorators import admin_required
from ..extensions import db
from ..forms import ImportOficialForm
from ..models import TURMA_CURTO, ResultadoLinha, ResultadoOficial, turma_valida
from ..oficiais_import import ErroImport, aplicar, parse
from ..vinculo import nome_ja_usado, revincular

oficiais_bp = Blueprint("oficiais", __name__)

_PROMPT_CACHE = {}


def _prompt_extracao() -> str:
    """Texto de docs/PROMPT-EXTRACAO.md — fonte única do prompt mostrado ao admin."""
    if "texto" not in _PROMPT_CACHE:
        caminho = os.path.join(
            os.path.dirname(current_app.root_path), "docs", "PROMPT-EXTRACAO.md"
        )
        try:
            with open(caminho, encoding="utf-8") as arquivo:
                _PROMPT_CACHE["texto"] = arquivo.read()
        except OSError:
            _PROMPT_CACHE["texto"] = (
                "Arquivo docs/PROMPT-EXTRACAO.md não encontrado nesta instalação."
            )
    return _PROMPT_CACHE["texto"]


def _resultados():
    return db.session.scalars(
        db.select(ResultadoOficial).order_by(ResultadoOficial.concurso_nome)
    ).all()


@oficiais_bp.route("/")
@login_required
def index():
    resultados = _resultados()
    # As linhas do próprio usuário, para o destaque no topo.
    minhas = db.session.scalars(
        db.select(ResultadoLinha).filter_by(user_id=current_user.id)
    ).all()
    minhas.sort(key=lambda ln: (ln.resultado.concurso_nome, ln.turma))
    return render_template(
        "oficiais/index.html",
        resultados=resultados,
        minhas=minhas,
        sem_nome=not (current_user.nome_oficial or "").strip(),
        TURMA_CURTO=TURMA_CURTO,
    )


@oficiais_bp.route("/<int:resultado_id>")
@login_required
def detalhe(resultado_id):
    resultado = db.session.get(ResultadoOficial, resultado_id)
    if resultado is None:
        abort(404)
    # Filtro por query string (e não por JS): o link fica compartilhável e o
    # servidor continua sendo a fonte da verdade dos números. Valor inválido
    # cai em "Todos" sem reclamar.
    turma = turma_valida(request.args.get("turma"))
    return render_template(
        "oficiais/detalhe.html",
        r=resultado,
        materias=resultado.materias,
        turma=turma,
        turmas=resultado.turmas_presentes,
        TURMA_CURTO=TURMA_CURTO,
    )


@oficiais_bp.route("/importar", methods=["GET", "POST"])
@admin_required
def importar():
    """Duas etapas no mesmo endpoint: 'validar' mostra o preview, 'confirmar' grava.

    O JSON viaja de volta no próprio formulário (não cabe na sessão-cookie)."""
    form = ImportOficialForm()
    preview = None

    if form.validate_on_submit():
        try:
            dados = parse(form.payload.data)
        except ErroImport as exc:
            form.payload.errors.append(str(exc))
        else:
            if request.form.get("acao") == "confirmar":
                try:
                    resultado = aplicar(db, dados, current_user.id)
                except ErroImport as exc:
                    # Conflitos contra a OUTRA turma só aparecem aqui (o parse
                    # sozinho não conhece o que já está no banco).
                    db.session.rollback()
                    form.payload.errors.append(str(exc))
                else:
                    db.session.flush()
                    vinculadas = revincular()
                    db.session.commit()
                    flash(
                        f"Turma {dados['turma']} de {dados['concurso']} importada — "
                        f"{len(dados['linhas'])} pessoas, "
                        f"{vinculadas} vinculada(s) a perfis.",
                        "success",
                    )
                    return redirect(
                        url_for("oficiais.detalhe", resultado_id=resultado.id)
                    )

            existente = db.session.scalar(
                db.select(ResultadoOficial).filter_by(concurso_nome=dados["concurso"])
            )
            preview = {
                "dados": dados,
                "concurso": existente,
                # Só a turma do JSON é substituída; a outra fica onde está.
                "substitui_turma": bool(
                    existente
                    and any(ln.turma == dados["turma"] for ln in existente.linhas)
                ),
                "outras_turmas": [
                    t
                    for t in (existente.turmas_presentes if existente else [])
                    if t != dados["turma"]
                ],
            }

    return render_template(
        "oficiais/importar.html",
        form=form,
        preview=preview,
        prompt_extracao=_prompt_extracao(),
    )


@oficiais_bp.post("/<int:resultado_id>/excluir")
@admin_required
def excluir(resultado_id):
    """Exclui UMA turma (?turma=...) ou o concurso inteiro.

    Como agora o registro guarda as duas turmas, apagar tudo num clique seria
    destrutivo demais: o padrão é apagar só a turma pedida."""
    resultado = db.session.get(ResultadoOficial, resultado_id)
    if resultado is None:
        abort(404)

    turma = turma_valida(request.form.get("turma"))
    if turma is None:
        nome = resultado.concurso_nome
        db.session.delete(resultado)
        db.session.commit()
        flash(f"{nome} excluído por completo.", "success")
        return redirect(url_for("oficiais.index"))

    alvo = [ln for ln in resultado.linhas if ln.turma == turma]
    if not alvo:
        abort(404)
    for linha in alvo:
        resultado.linhas.remove(linha)
    db.session.flush()

    # Sem nenhuma turma, o cabeçalho não descreve mais nada: sai junto.
    if not resultado.linhas:
        db.session.delete(resultado)
        db.session.commit()
        flash(
            f"Turma {turma} excluída — era a última, então o concurso saiu junto.",
            "success",
        )
        return redirect(url_for("oficiais.index"))

    db.session.commit()
    flash(f"Turma {turma} excluída ({len(alvo)} pessoas).", "success")
    return redirect(url_for("oficiais.detalhe", resultado_id=resultado.id))


@oficiais_bp.post("/linha/<int:linha_id>/reivindicar")
@login_required
def reivindicar(linha_id):
    """'Sou eu': adota o nome da linha como nome_oficial e revincula tudo."""
    linha = db.session.get(ResultadoLinha, linha_id)
    if linha is None:
        abort(404)

    if nome_ja_usado(linha.nome_norm, current_user.id):
        flash("Esse nome já está vinculado a outra conta.", "error")
        return redirect(url_for("oficiais.detalhe", resultado_id=linha.resultado_id))

    current_user.nome_oficial = linha.nome
    revincular()
    db.session.commit()
    flash(f"Pronto — seus resultados oficiais estão ligados a {linha.nome}.", "success")
    return redirect(url_for("oficiais.detalhe", resultado_id=linha.resultado_id))
