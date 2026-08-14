"""Área do admin: turmas, alunos e a curadoria de identidade (merge).

Existe porque a Fase A criou o Aluno a partir dos nomes das planilhas — e nome
lido por OCR varia. A data migration cria um aluno por grafia distinta, então
duplicatas nascem junto; sem uma tela para juntá-las, a lista de turma nasce
errada. Por isso merge faz parte da mesma entrega, e não de um "depois".
"""

import json

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

from ..alunos import (
    ErroMerge,
    candidatos_a_merge,
    contar_linhas,
    linhas_do_aluno,
    mesclar,
)
from flask_login import current_user

from ..convites import (
    ErroConvite,
    alunos_sem_conta,
    coringas,
    contas_sem_aluno,
    convite_ativo,
    desvincular,
    emitir,
    emitir_coringa,
    revogar,
)
from ..decorators import admin_required
from ..diagnostico import retrato, sha_remoto, testar_github
from ..evolucao import evolucao_do_aluno
from ..extensions import db, limiter
from ..forms import AlunoForm, CoringaForm
from ..models import (
    MATERIAS_SIMULADO,
    TURMA_CURTO,
    TURMAS,
    Aluno,
    AlunoApelido,
    ConviteAluno,
    HistoricoImport,
    ResultadoLinha,
    SimuladoTurmaLinha,
    normalizar_nome,
    turma_valida,
)
from ..oficiais_import import materias_da_query
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


@admin_bp.route("/alunos/<int:aluno_id>/evolucao")
@admin_required
def aluno_evolucao(aluno_id):
    """Mesma visão de evolução do usuário (Fase E), sobre um aluno qualquer."""
    aluno = _get_aluno(aluno_id)
    recorte = materias_da_query(request.args.get("materias"), MATERIAS_SIMULADO)
    dados = evolucao_do_aluno(aluno.id, recorte)
    return render_template(
        "evolucao.html",
        titulo=f"Evolução — {aluno.nome}",
        dados_js=dados,
        voltar_url=url_for("admin.aluno_detalhe", aluno_id=aluno.id),
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


# --------------------------------------------------------------------------
# Histórico de import — só leitura.
# --------------------------------------------------------------------------
#
# A tabela era só de escrita: gravava todo import aplicado e ninguém nunca via.
# Aqui ela vira tela, para comparar o que foi enviado com o que ficou gravado
# e, se preciso, reaplicar À MÃO. Não existe rollback e não é o objetivo:
# desfazer import é caso a caso e mexeria em dado de todo mundo.

# JSON acima disto não vai inteiro para a tela: só o começo, mais o botão de
# baixar. Sem o corte, um listão grande trava o navegador do celular.
LIMITE_JSON_NA_TELA = 100_000


@admin_bp.route("/historico")
@admin_required
def historico():
    """Lista dos imports aplicados, mais recente primeiro.

    Sem o JSON: só o tamanho dele. Despejar o payload aqui deixaria a listagem
    com megabytes.
    """
    registros = db.session.scalars(
        db.select(HistoricoImport).order_by(HistoricoImport.created_at.desc())
    ).all()
    itens = [
        {"registro": r, "tamanho": len(r.payload_json or "")} for r in registros
    ]
    return render_template("admin/historico.html", itens=itens)


def _get_historico(historico_id: int) -> "HistoricoImport":
    registro = db.session.get(HistoricoImport, historico_id)
    if registro is None:
        abort(404)
    return registro


@admin_bp.route("/historico/<int:historico_id>")
@admin_required
def historico_detalhe(historico_id):
    """O JSON cru, indentado para leitura. Se não for JSON válido, mostra como veio."""
    registro = _get_historico(historico_id)
    bruto = registro.payload_json or ""
    try:
        formatado = json.dumps(json.loads(bruto), indent=2, ensure_ascii=False, sort_keys=False)
    except (ValueError, TypeError):
        formatado = bruto

    cortado = len(formatado) > LIMITE_JSON_NA_TELA
    return render_template(
        "admin/historico_detalhe.html",
        registro=registro,
        conteudo=formatado[:LIMITE_JSON_NA_TELA] if cortado else formatado,
        cortado=cortado,
        tamanho=len(bruto),
    )


@admin_bp.route("/historico/<int:historico_id>/baixar")
@admin_required
def historico_baixar(historico_id):
    """Baixa o payload original, sem reformatar — é o que foi enviado."""
    registro = _get_historico(historico_id)
    nome = f"import-{registro.tipo}-{registro.id}.json"
    return Response(
        registro.payload_json or "",
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# --------------------------------------------------------------------------
# Convites — quem entra no app e a que aluno cada conta pertence.
# --------------------------------------------------------------------------


@admin_bp.route("/convites")
@admin_required
def convites():
    """Quem já tem conta, quem tem código pendente e quem falta convidar."""
    alunos = db.session.scalars(db.select(Aluno).order_by(Aluno.nome)).all()
    itens = [
        {
            "aluno": aluno,
            "convite": convite_ativo(aluno.id),
            "usado": db.session.scalar(
                db.select(ConviteAluno)
                .filter(
                    ConviteAluno.aluno_id == aluno.id,
                    ConviteAluno.usado_por_user_id.isnot(None),
                )
                .order_by(ConviteAluno.usado_em.desc())
            ),
        }
        for aluno in alunos
    ]
    return render_template(
        "admin/convites.html",
        itens=itens,
        faltam=alunos_sem_conta(),
        contas_soltas=contas_sem_aluno(),
        coringas=coringas(),
        coringa_form=CoringaForm(),
    )


def _get_aluno(aluno_id: int) -> "Aluno":
    aluno = db.session.get(Aluno, aluno_id)
    if aluno is None:
        abort(404)
    return aluno


@admin_bp.post("/convites/<int:aluno_id>/gerar")
@admin_required
def convite_gerar(aluno_id):
    aluno = _get_aluno(aluno_id)
    if aluno.user_id is not None:
        flash(f"{aluno.nome} já tem conta vinculada.", "info")
        return redirect(url_for("admin.convites"))
    convite = emitir(aluno, current_user.id)
    db.session.commit()
    flash(f"Código de {aluno.nome}: {convite.formatado}", "success")
    return redirect(url_for("admin.convites"))


@admin_bp.post("/convites/<int:convite_id>/revogar")
@admin_required
def convite_revogar(convite_id):
    convite = db.session.get(ConviteAluno, convite_id)
    if convite is None:
        abort(404)
    nome = convite.aluno.nome if convite.aluno else "aluno"
    if revogar(convite):
        db.session.commit()
        flash(f"Código de {nome} revogado.", "success")
    else:
        flash("Esse código já foi usado — não dá para revogar.", "error")
    return redirect(url_for("admin.convites"))


@admin_bp.post("/convites/<int:aluno_id>/desvincular")
@admin_required
def convite_desvincular(aluno_id):
    """Desfaz o vínculo conta ↔ aluno, para corrigir erro.

    A conta continua liberada: ela resgatou um código de verdade, e trancá-la
    puniria a pessoa por um engano de cadastro.
    """
    aluno = _get_aluno(aluno_id)
    desvincular(aluno)
    db.session.commit()
    flash(f"{aluno.nome} não está mais vinculado a nenhuma conta.", "success")
    return redirect(url_for("admin.convites"))


@admin_bp.post("/convites/coringa")
@admin_required
def convite_coringa():
    """Código que libera a conta sem vincular a aluno nenhum."""
    form = CoringaForm()
    if not form.validate_on_submit():
        flash("Diga para que serve o coringa (ex.: coordenador).", "error")
        return redirect(url_for("admin.convites"))
    try:
        convite = emitir_coringa(form.rotulo.data, current_user.id)
    except ErroConvite as erro:
        flash(str(erro), "error")
        return redirect(url_for("admin.convites"))
    db.session.commit()
    flash(f"Coringa para {convite.rotulo}: {convite.formatado}", "success")
    return redirect(url_for("admin.convites"))


# --------------------------------------------------------------------------
# Diagnóstico de deploy — SÓ LEITURA.
# --------------------------------------------------------------------------
#
# Nasceu de um deploy real: o disco tinha 2.5.03, o site servia 2.5.02, e o
# primeiro `touch` no WSGI não reiniciou o worker. A comparação
# "memória × disco" vira mostrador aqui — é ela que responde sozinha
# "o deploy não pegou, reinicie".
#
# Nenhuma rota daqui escreve, move ou executa comando de mudança. O teste de
# rede é POST (nunca GET) porque sai da máquina, e tem timeout curto: sem
# proxy a conexão TRAVA em vez de falhar rápido.


@admin_bp.route("/deploy")
@admin_required
def deploy():
    """Estado do worker. Nada de rede: só o que dá para ler da própria máquina."""
    return render_template("admin/deploy.html", estado=retrato(), rede=None, remoto=None)


@admin_bp.post("/deploy/testar-rede")
@admin_required
@limiter.limit("10 per hour", error_message="Muitos testes de rede. Espere um pouco.")
def deploy_testar_rede():
    """Pergunta ao GitHub se o WORKER alcança ele. Leitura HTTP, nada mais.

    O alvo é fixo no código: nada da requisição vira argumento. O formulário
    não manda parâmetro nenhum além do CSRF.
    """
    current_app.logger.info(
        "Diagnóstico de rede: usuario=%s ip=%s",
        current_user.username,
        request.remote_addr,
    )
    return render_template(
        "admin/deploy.html",
        estado=retrato(),
        rede=testar_github(),
        remoto=sha_remoto(),
    )
