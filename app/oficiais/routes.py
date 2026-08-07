import json
import os
from datetime import date

from flask import (
    Blueprint,
    Response,
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
from ..models import (
    TURMA_CURTO,
    HistoricoImport,
    ResultadoLinha,
    ResultadoOficial,
    normalizar_nome,
    turma_valida,
    utcnow,
)
from ..exportacao import exportar_resultado_oficial
from ..oficiais_import import ErroImport, aplicar, parse
from ..validacao import (
    _texto,
    validar_classificacao,
    validar_classificacao_unica,
    validar_nome_unico,
    validar_nota,
    validar_status,
)
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


@oficiais_bp.route("/<int:resultado_id>/exportar")
@admin_required
def exportar(resultado_id):
    """Exporta uma turma do listão no MESMO formato que o importador aceita
    (Fase F.2) — exportar e reimportar é ida e volta sem perda."""
    resultado = db.session.get(ResultadoOficial, resultado_id)
    if resultado is None:
        abort(404)
    turma = turma_valida(request.args.get("turma"))
    if turma is None:
        abort(404)
    dados = exportar_resultado_oficial(resultado, turma)
    corpo = json.dumps(dados, ensure_ascii=False, indent=2)
    resposta = Response(corpo, mimetype="application/json")
    nome = f"{resultado.concurso_nome}-{turma}".replace(" ", "-").replace("/", "-")
    resposta.headers["Content-Disposition"] = f'attachment; filename="{nome}.json"'
    return resposta


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
                    db.session.add(
                        HistoricoImport(
                            tipo="oficial",
                            alvo=f"{dados['concurso']} - {dados['turma']}",
                            created_by=current_user.id,
                            payload_json=form.payload.data,
                        )
                    )
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
            # Linhas da turma que SERÁ substituída e que o admin já corrigiu à
            # mão: o import não bloqueia, só avisa — quem decide é o admin.
            linhas_editadas = []
            if existente is not None:
                linhas_editadas = [
                    ln.nome
                    for ln in existente.linhas
                    if ln.turma == dados["turma"] and ln.editado_em is not None
                ]
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
                "linhas_editadas": linhas_editadas,
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


# --------------------------------------------------------------------------
# Edição manual pelo admin (Fase B do plano) — correção pontual sem reimportar.
# --------------------------------------------------------------------------


def _aplicar_edicao_linha(linha: ResultadoLinha, form) -> None:
    """Valida e grava os campos editáveis de uma ResultadoLinha. Não comita.

    Usa as mesmas funções de app/validacao.py que `parse()` usa no import —
    é o requisito de aceite: mesmo erro de valor, mesma mensagem."""
    resultado = linha.resultado
    onde = "edição"

    nome = _texto(form.get("nome"), "nome", 120)
    nome_norm = normalizar_nome(nome)

    turma = turma_valida(form.get("turma"))
    if turma is None:
        raise ErroImport('O campo "turma" precisa ser "novata" ou "veterana".')

    status = validar_status(
        form.get("status"), ResultadoLinha.STATUS, onde, nome, com_underscore=True
    )

    classificacao = None
    if status == "classificado":
        bruto = (form.get("classificacao") or "").strip()
        classificacao = int(bruto) if bruto.lstrip("-").isdigit() else None
        validar_classificacao(classificacao, onde, nome)

    metrica_valor = None
    bruto_metrica = (form.get("metrica_valor") or "").strip()
    if bruto_metrica:
        try:
            metrica_valor = float(bruto_metrica.replace(",", "."))
        except ValueError:
            raise ErroImport(f'{onde} ({nome}): "metrica" precisa ser número.')

    notas = {}
    for materia in resultado.materias:
        bruto_nota = (form.get(f"nota_{materia.name}") or "").strip()
        if not bruto_nota:
            continue
        try:
            nota = float(bruto_nota.replace(",", "."))
        except ValueError:
            raise ErroImport(f"{onde} ({nome}): nota de {materia.value} precisa ser número.")
        validar_nota(nota, resultado.escala, materia, onde, nome)
        notas[materia.name] = nota

    # Escopo é o CONCURSO INTEIRO (todas as turmas) — a classificação e o nome
    # não são exclusividade de uma turma (ver B.3 do plano).
    validar_nome_unico(resultado.linhas, nome, nome_norm, turma, linha_id=linha.id)
    if status == "classificado":
        validar_classificacao_unica(
            resultado.linhas, classificacao, nome, turma, linha_id=linha.id
        )

    linha.nome = nome
    linha.nome_norm = nome_norm
    linha.turma = turma
    linha.status = status
    linha.classificacao = classificacao
    linha.metrica_valor = metrica_valor
    linha.set_notas(notas)


@oficiais_bp.post("/linha/<int:linha_id>/editar")
@admin_required
def linha_editar(linha_id):
    linha = db.session.get(ResultadoLinha, linha_id)
    if linha is None:
        abort(404)
    try:
        _aplicar_edicao_linha(linha, request.form)
    except ErroImport as exc:
        flash(str(exc), "error")
    else:
        linha.editado_em = utcnow()
        linha.editado_por = current_user.id
        db.session.commit()
        flash(f"{linha.nome} atualizado.", "success")
    return redirect(url_for("oficiais.detalhe", resultado_id=linha.resultado_id))


@oficiais_bp.post("/<int:resultado_id>/editar")
@admin_required
def editar_cabecalho(resultado_id):
    """Só os metadados (fonte, data, métrica). Matérias/escala com linhas dentro
    mudam o significado de todos os números já gravados — bloqueado de propósito."""
    resultado = db.session.get(ResultadoOficial, resultado_id)
    if resultado is None:
        abort(404)

    campos_bloqueados = {"materias", "materias_csv", "escala"}
    if resultado.linhas and campos_bloqueados & set(request.form.keys()):
        flash(
            "Matérias e escala não dão para editar com linhas já importadas — "
            "exclua o concurso e reimporte em vez disso.",
            "error",
        )
        return redirect(url_for("oficiais.detalhe", resultado_id=resultado.id))

    try:
        fonte = _texto(request.form.get("fonte"), "fonte", 40, obrigatorio=False)
        metrica = _texto(request.form.get("metrica"), "metrica", 20, obrigatorio=False)
        bruto_data = (request.form.get("data") or "").strip()
        data = date.fromisoformat(bruto_data) if bruto_data else None
    except ErroImport as exc:
        flash(str(exc), "error")
        return redirect(url_for("oficiais.detalhe", resultado_id=resultado.id))
    except ValueError:
        flash('"data" precisa estar no formato AAAA-MM-DD.', "error")
        return redirect(url_for("oficiais.detalhe", resultado_id=resultado.id))

    resultado.fonte = fonte
    resultado.metrica = metrica
    resultado.data = data
    db.session.commit()
    flash("Cabeçalho atualizado.", "success")
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
