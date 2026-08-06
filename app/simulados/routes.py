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

from ..conferencia import relatorio, tem_alerta
from ..decorators import admin_required
from ..extensions import db
from ..forms import ImportSimuladoTurmaForm, SimuladoForm
from ..grouping import agrupar, rotulo_curto
from ..models import (
    TURMA_CURTO,
    Concurso,
    Materia,
    Simulado,
    SimuladoMateria,
    SimuladoTurma,
    SimuladoTurmaLinha,
    normalizar_nome,
    turma_valida,
    utcnow,
)
from ..oficiais_import import ErroImport
from ..simulado_sync import concursos_por_banca, linhas_pendentes, sincronizar_linha, sugerir_concurso
from ..simulado_turma_import import aplicar as aplicar_turma
from ..simulado_turma_import import parse as parse_turma
from ..validacao import (
    _texto,
    validar_acertos,
    validar_geral_oficial,
    validar_nome_unico,
    validar_status,
)
from ..vinculo import nome_ja_usado, revincular

simulados_bp = Blueprint("simulados", __name__)


def _get_simulado_do_usuario(simulado_id: int) -> Simulado:
    """Carrega o simulado SOMENTE se pertencer ao usuário logado (ou admin).

    404 (e não 403) quando o dono é outro: não confirma a existência do recurso,
    então não dá sinal útil para varredura de IDs.
    """
    simulado = db.session.get(Simulado, simulado_id)
    if simulado is None:
        abort(404)
    if simulado.user_id != current_user.id and not current_user.is_admin:
        abort(404)
    return simulado


def _concursos_ordenados():
    return db.session.scalars(db.select(Concurso).order_by(Concurso.data_prova)).all()


def _bancas_e_etapas(concursos):
    """Estruturas para os dois selects dependentes do form de simulado.

    bancas: lista de bancas na ordem cronológica.
    etapas: [{id, banca, label}] — label = fase/dia + data (ou "Prova única")."""
    bancas, etapas = [], []
    for banca, itens in agrupar(concursos):
        bancas.append(banca)
        for c in itens:
            fase = rotulo_curto(c.nome)
            if fase == c.nome:  # concurso sem " - " (dia único)
                fase = "Prova única"
            # Só o nome da fase, sem a data (a data fica no dashboard/countdown).
            etapas.append({"id": c.id, "banca": banca, "label": fase})
    return bancas, etapas


def _ids_das_choices(choices) -> set:
    return {cid for cid, _ in choices}


def _materias_map() -> dict:
    """{concurso_id: [nome_enum, ...]} — matérias que caem em cada concurso.

    Usado no front para mostrar só as matérias do concurso selecionado."""
    concursos = db.session.scalars(db.select(Concurso)).all()
    return {c.id: [m.name for m in c.materias] for c in concursos}


def _rotulos_usados() -> list:
    """Rótulos que o usuário já usou (S1, S3...), para o datalist do formulário."""
    linhas = db.session.scalars(
        db.select(Simulado.rotulo)
        .filter(Simulado.user_id == current_user.id, Simulado.rotulo.isnot(None))
        .distinct()
    ).all()
    return sorted({r.strip() for r in linhas if r and r.strip()})


def _aplicar_form(form: SimuladoForm, simulado: Simulado) -> None:
    simulado.concurso_id = form.concurso_id.data
    simulado.rotulo = (form.rotulo.data or "").strip() or None
    simulado.data_simulado = form.data_simulado.data
    simulado.posicao_estimada = form.posicao_estimada.data
    simulado.observacao = form.observacao.data or None

    # Só aceita matérias que realmente caem no concurso escolhido (guarda de
    # servidor: não confia no que o front mandou/escondeu).
    concurso = db.session.get(Concurso, form.concurso_id.data)
    permitidas = {m.name for m in concurso.materias} if concurso else set()

    # Nota geral: automática (média dos % das matérias que contam) ou manual.
    if form.modo_nota.data == "auto":
        media = form.media_automatica(permitidas)
        simulado.nota_geral = media if media is not None else 0.0
        simulado.nota_automatica = True
    else:
        simulado.nota_geral = float(form.nota_geral.data)
        simulado.nota_automatica = False

    # Remove as matérias antigas E força o DELETE agora (flush): senão, ao regravar
    # as mesmas matérias, o SQLAlchemy pode inserir antes de deletar e violar o
    # UNIQUE (simulado_id, materia).
    simulado.materias.clear()
    db.session.flush()
    for enum_name, subform in form.materia_fields():
        if subform.preenchido and enum_name in permitidas:
            simulado.materias.append(
                SimuladoMateria(
                    materia=Materia[enum_name],
                    acertos=subform.acertos.data,
                    total_questoes=subform.total_questoes.data,
                )
            )


@simulados_bp.route("/")
@login_required
def listar():
    simulados = db.session.scalars(
        db.select(Simulado)
        .filter_by(user_id=current_user.id)
        .order_by(Simulado.data_simulado.desc(), Simulado.id.desc())
    ).all()
    return render_template("simulados/list.html", simulados=simulados)


def _render_form(form, titulo, concursos, **extra):
    bancas, etapas = _bancas_e_etapas(concursos)
    return render_template(
        "simulados/form.html",
        form=form,
        titulo=titulo,
        bancas=bancas,
        etapas=etapas,
        materias_map=_materias_map(),
        rotulos=_rotulos_usados(),
        **extra,
    )


@simulados_bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    concursos = _concursos_ordenados()
    form = SimuladoForm()
    form.concurso_id.choices = [(c.id, c.nome) for c in concursos]
    if not form.concurso_id.choices:
        flash("Nenhum concurso cadastrado ainda. Peça ao admin para criar um.", "info")
        return redirect(url_for("concursos.listar"))

    if form.validate_on_submit():
        simulado = Simulado(user_id=current_user.id)
        db.session.add(simulado)  # na sessão antes de mexer nas matérias (ver _aplicar_form)
        _aplicar_form(form, simulado)
        db.session.commit()
        flash("Simulado registrado!", "success")
        return redirect(url_for("simulados.detalhe", simulado_id=simulado.id))

    if request.method == "GET":
        preselect = request.args.get("concurso", type=int)
        if preselect and preselect in _ids_das_choices(form.concurso_id.choices):
            form.concurso_id.data = preselect

    return _render_form(form, "Novo simulado", concursos)


@simulados_bp.route("/<int:simulado_id>")
@login_required
def detalhe(simulado_id):
    simulado = _get_simulado_do_usuario(simulado_id)
    return render_template("simulados/detail.html", simulado=simulado)


@simulados_bp.route("/<int:simulado_id>/editar", methods=["GET", "POST"])
@login_required
def editar(simulado_id):
    simulado = _get_simulado_do_usuario(simulado_id)
    concursos = _concursos_ordenados()
    form = SimuladoForm(obj=simulado)
    form.concurso_id.choices = [(c.id, c.nome) for c in concursos]

    if form.validate_on_submit():
        _aplicar_form(form, simulado)
        db.session.commit()
        flash("Simulado atualizado.", "success")
        return redirect(url_for("simulados.detalhe", simulado_id=simulado.id))

    if request.method == "GET":
        form.concurso_id.data = simulado.concurso_id
        form.modo_nota.data = "auto" if simulado.nota_automatica else "manual"
        existentes = {sm.materia.name: sm for sm in simulado.materias}
        for enum_name, subform in form.materia_fields():
            if enum_name in existentes:
                subform.acertos.data = existentes[enum_name].acertos
                subform.total_questoes.data = existentes[enum_name].total_questoes

    return _render_form(form, "Editar simulado", concursos, simulado=simulado)


@simulados_bp.post("/<int:simulado_id>/deletar")
@login_required
def deletar(simulado_id):
    simulado = _get_simulado_do_usuario(simulado_id)
    db.session.delete(simulado)
    db.session.commit()
    flash("Simulado excluído.", "success")
    return redirect(url_for("simulados.listar"))


# --------------------------------------------------------------------------
# Sincronização em lote (Fase C): traz TODAS as linhas pendentes do usuário.
# --------------------------------------------------------------------------


@simulados_bp.route("/sincronizar", methods=["GET", "POST"])
@login_required
def sincronizar():
    """Versão em lote do `turma_trazer`: só adiciona, nunca apaga/sobrescreve.

    GET mostra o preview (linhas pendentes + concurso sugerido, editável por
    linha). POST grava o que foi confirmado; linha sem concurso escolhido ou
    já sincronizada fica de fora, sem travar as demais."""
    mapa_bancas = concursos_por_banca()
    pendentes = linhas_pendentes(current_user.id)

    if request.method == "POST":
        sincronizados, pulados = 0, 0
        for linha in pendentes:
            concurso_id = request.form.get(f"concurso_{linha.id}", type=int)
            concurso = db.session.get(Concurso, concurso_id) if concurso_id else None
            if concurso is None:
                pulados += 1
                continue
            resultado = sincronizar_linha(linha, concurso, current_user.id)
            if resultado is None:
                pulados += 1
            else:
                sincronizados += 1
        db.session.commit()
        if sincronizados:
            flash(
                f"{sincronizados} simulado(s) sincronizado(s)"
                + (f", {pulados} pulado(s)." if pulados else "."),
                "success",
            )
        else:
            flash("Nada para sincronizar — nenhuma linha com concurso escolhido.", "info")
        return redirect(url_for("simulados.listar"))

    itens = [
        {"linha": linha, "sugestao": sugerir_concurso(linha, mapa_bancas)}
        for linha in pendentes
    ]
    return render_template(
        "simulados/sincronizar.html",
        itens=itens,
        concursos=_concursos_ordenados(),
    )


# --------------------------------------------------------------------------
# Ranking da turma: o mesmo simulado, com todo mundo que fez.
# --------------------------------------------------------------------------

_PROMPT_CACHE = {}


def _prompt_simulado() -> str:
    if "texto" not in _PROMPT_CACHE:
        caminho = os.path.join(
            os.path.dirname(current_app.root_path),
            "docs",
            "PROMPT-EXTRACAO-SIMULADO.md",
        )
        try:
            with open(caminho, encoding="utf-8") as arquivo:
                _PROMPT_CACHE["texto"] = arquivo.read()
        except OSError:
            _PROMPT_CACHE["texto"] = (
                "Arquivo docs/PROMPT-EXTRACAO-SIMULADO.md não encontrado."
            )
    return _PROMPT_CACHE["texto"]


def _avisar_qualidade() -> None:
    """Alerta pós-import sobre nome/série/turma, que não têm trava aritmética.

    Informativo: nada aqui bloqueia o import (o que bloqueia está nos parsers)."""
    dados = relatorio()
    if not tem_alerta(dados):
        return
    partes = []
    if dados["serie_regride"]:
        partes.append(f"{len(dados['serie_regride'])} série(s) regredindo")
    if dados["duas_turmas"]:
        partes.append(f"{len(dados['duas_turmas'])} pessoa(s) em duas turmas")
    if dados["nomes_solitarios"]:
        partes.append(f"{len(dados['nomes_solitarios'])} nome(s) que aparecem uma vez só")
    flash(
        "Confira a extração: " + ", ".join(partes) + ". "
        "Rode `flask conferir-import` para ver os detalhes.",
        "info",
    )


def _get_turma(turma_id: int) -> SimuladoTurma:
    turma = db.session.get(SimuladoTurma, turma_id)
    if turma is None:
        abort(404)
    return turma


@simulados_bp.route("/turma/")
@login_required
def turma_listar():
    turmas = db.session.scalars(
        db.select(SimuladoTurma).order_by(
            SimuladoTurma.data.desc(), SimuladoTurma.banca, SimuladoTurma.rotulo
        )
    ).all()
    minhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(user_id=current_user.id)
    ).all()
    return render_template(
        "simulados/turma_list.html",
        turmas=turmas,
        tem_vinculo=bool(minhas),
        sem_nome=not (current_user.nome_oficial or "").strip(),
        TURMA_CURTO=TURMA_CURTO,
    )


@simulados_bp.route("/turma/importar", methods=["GET", "POST"])
@admin_required
def turma_importar():
    form = ImportSimuladoTurmaForm()
    preview = None

    if form.validate_on_submit():
        # Planilha sem data no título faz o extrator devolver "data": null; nesse
        # caso a data vem daqui.
        try:
            dados = parse_turma(form.payload.data, data_padrao=form.data.data)
        except ErroImport as exc:
            form.payload.errors.append(str(exc))
        else:
            existente = db.session.scalar(
                db.select(SimuladoTurma).filter_by(
                    banca=dados["banca"], rotulo=dados["rotulo"], data=dados["data"]
                )
            )
            if request.form.get("acao") == "confirmar":
                try:
                    simulado = aplicar_turma(db, dados, current_user.id)
                except ErroImport as exc:
                    db.session.rollback()
                    form.payload.errors.append(str(exc))
                else:
                    db.session.flush()
                    vinculadas = revincular()
                    db.session.commit()
                    flash(
                        f"Turma {dados['turma']} de {simulado.nome} importada — "
                        f"{len(dados['linhas'])} pessoas, "
                        f"{vinculadas} vinculada(s) a perfis.",
                        "success",
                    )
                    _avisar_qualidade()
                    return redirect(
                        url_for("simulados.turma_detalhe", turma_id=simulado.id)
                    )
            else:
                linhas_editadas = []
                if existente is not None:
                    linhas_editadas = [
                        ln.nome
                        for ln in existente.linhas
                        if ln.turma == dados["turma"] and ln.editado_em is not None
                    ]
                preview = {
                    "dados": dados,
                    "prova": existente,
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
        "simulados/turma_importar.html",
        form=form,
        preview=preview,
        prompt_extracao=_prompt_simulado(),
    )


@simulados_bp.route("/turma/<int:turma_id>")
@login_required
def turma_detalhe(turma_id):
    turma = _get_turma(turma_id)
    materias = turma.materias
    # Filtro por query string: link compartilhável e servidor como fonte da
    # verdade. Valor inválido cai em "Todos" silenciosamente.
    filtro = turma_valida(request.args.get("turma"))

    # Padrão do recorte: as matérias da MÉDIA oficial; se o listão não disser,
    # todas as matérias da prova.
    padrao = turma.materias_media or materias

    # Matérias do concurso alvo do usuário, para o atalho "Meu concurso":
    # a interseção entre o que o concurso cobra e o que esta prova mediu.
    do_concurso = {}
    for concurso in db.session.scalars(db.select(Concurso).order_by(Concurso.data_prova)):
        nomes = [m.name for m in concurso.materias if m in materias]
        if nomes:
            do_concurso[concurso.nome] = nomes

    minha_linha = next(
        (ln for ln in turma.linhas if ln.user_id == current_user.id), None
    )
    meu_simulado = None
    if minha_linha is not None:
        meu_simulado = db.session.scalar(
            db.select(Simulado).filter_by(
                user_id=current_user.id, rotulo=turma.rotulo
            )
        )

    # O JS recalcula o ranking no recorte de matérias; só as linhas do filtro de
    # turma ativo vão para ele, para as posições renumerarem dentro do recorte.
    dados_js = {
        "questoes": turma.questoes,
        "materias": [{"name": m.name, "label": m.value} for m in materias],
        "padrao": [m.name for m in padrao],
        "porConcurso": do_concurso,
        "chave": f"itaime_recorte_{turma.banca}",
        "linhas": [
            {"id": ln.id, "acertos": ln.acertos, "eu": ln.user_id == current_user.id}
            for ln in turma.presentes(filtro)
        ],
    }

    return render_template(
        "simulados/turma_detalhe.html",
        t=turma,
        materias=materias,
        dados_js=dados_js,
        minha_linha=minha_linha,
        meu_simulado=meu_simulado,
        filtro=filtro,
        turmas=turma.turmas_presentes,
        TURMA_CURTO=TURMA_CURTO,
        concursos=db.session.scalars(
            db.select(Concurso).order_by(Concurso.data_prova)
        ).all(),
    )


@simulados_bp.post("/turma/<int:turma_id>/excluir")
@admin_required
def turma_excluir(turma_id):
    """Exclui UMA turma (?turma=...) ou a prova inteira, como nos Oficiais."""
    turma = _get_turma(turma_id)

    alvo_turma = turma_valida(request.form.get("turma"))
    if alvo_turma is None:
        nome = turma.nome
        db.session.delete(turma)
        db.session.commit()
        flash(f"{nome} excluído por completo.", "success")
        return redirect(url_for("simulados.turma_listar"))

    alvo = [ln for ln in turma.linhas if ln.turma == alvo_turma]
    if not alvo:
        abort(404)
    for linha in alvo:
        turma.linhas.remove(linha)
    db.session.flush()

    if not turma.linhas:
        nome = turma.nome
        db.session.delete(turma)
        db.session.commit()
        flash(
            f"Turma {alvo_turma} excluída — era a última, então {nome} saiu junto.",
            "success",
        )
        return redirect(url_for("simulados.turma_listar"))

    db.session.commit()
    flash(f"Turma {alvo_turma} excluída ({len(alvo)} pessoas).", "success")
    return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))


# --------------------------------------------------------------------------
# Edição manual pelo admin (Fase B do plano) — correção pontual sem reimportar.
# --------------------------------------------------------------------------


def _aplicar_edicao_linha_turma(linha: SimuladoTurmaLinha, form) -> None:
    """Valida e grava os campos editáveis de uma SimuladoTurmaLinha. Não comita.

    Usa as mesmas funções de app/validacao.py que `parse()` usa no import."""
    turma_obj = linha.turma_obj
    onde = "edição"

    nome = _texto(form.get("nome"), "nome", 120)
    nome_norm = normalizar_nome(nome)

    turma = turma_valida(form.get("turma"))
    if turma is None:
        raise ErroImport('O campo "turma" precisa ser "novata" ou "veterana".')

    serie = _texto(form.get("serie"), "serie", 20, obrigatorio=False)

    status = validar_status(form.get("status"), SimuladoTurmaLinha.STATUS, onde, nome)

    acertos = {}
    if status == "presente":
        for materia in turma_obj.materias:
            bruto = (form.get(f"acertos_{materia.name}") or "").strip()
            if not bruto:
                continue
            if not bruto.lstrip("-").isdigit():
                raise ErroImport(
                    f"{onde} ({nome}): acertos de {materia.value} precisa ser inteiro."
                )
            certas = int(bruto)
            total = turma_obj.questoes.get(materia.name, 0)
            validar_acertos(certas, total, materia, onde, nome)
            acertos[materia.name] = certas

    def _opcional_float(campo, rotulo):
        bruto = (form.get(campo) or "").strip()
        if not bruto:
            return None
        try:
            return float(bruto.replace(",", "."))
        except ValueError:
            raise ErroImport(f"{onde} ({nome}): {rotulo} precisa ser número.")

    media_oficial = _opcional_float("media_oficial", "a média oficial")
    geral_oficial = _opcional_float("geral_oficial", "o GERAL")

    if status == "presente":
        validar_geral_oficial(geral_oficial, sum(acertos.values()), onde, nome)

    # Escopo é a PROVA INTEIRA (todas as turmas), não só a turma da linha.
    validar_nome_unico(turma_obj.linhas, nome, nome_norm, turma, linha_id=linha.id)

    linha.nome = nome
    linha.nome_norm = nome_norm
    linha.turma = turma
    linha.serie = serie
    linha.status = status
    linha.set_acertos(acertos)
    linha.media_oficial = media_oficial
    linha.geral_oficial = geral_oficial


@simulados_bp.post("/turma/linha/<int:linha_id>/editar")
@admin_required
def turma_linha_editar(linha_id):
    linha = db.session.get(SimuladoTurmaLinha, linha_id)
    if linha is None:
        abort(404)
    try:
        _aplicar_edicao_linha_turma(linha, request.form)
    except ErroImport as exc:
        flash(str(exc), "error")
    else:
        linha.editado_em = utcnow()
        linha.editado_por = current_user.id
        db.session.commit()
        flash(f"{linha.nome} atualizado.", "success")
    return redirect(url_for("simulados.turma_detalhe", turma_id=linha.turma_id))


@simulados_bp.post("/turma/<int:turma_id>/editar")
@admin_required
def turma_editar_cabecalho(turma_id):
    """Só a fonte. Matérias/questões com linhas dentro mudam o significado dos
    números já gravados (acertos, ranking) — bloqueado de propósito."""
    turma = _get_turma(turma_id)

    campos_bloqueados = {"materias", "materias_csv", "materias_media_csv", "questoes"}
    if turma.linhas and campos_bloqueados & set(request.form.keys()):
        flash(
            "Matérias e questões não dão para editar com linhas já importadas — "
            "exclua a prova e reimporte em vez disso.",
            "error",
        )
        return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))

    try:
        fonte = _texto(request.form.get("fonte"), "fonte", 40, obrigatorio=False)
    except ErroImport as exc:
        flash(str(exc), "error")
        return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))

    turma.fonte = fonte
    db.session.commit()
    flash("Cabeçalho atualizado.", "success")
    return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))


@simulados_bp.post("/turma/linha/<int:linha_id>/reivindicar")
@login_required
def turma_reivindicar(linha_id):
    linha = db.session.get(SimuladoTurmaLinha, linha_id)
    if linha is None:
        abort(404)
    if nome_ja_usado(linha.nome_norm, current_user.id):
        flash("Esse nome já está vinculado a outra conta.", "error")
    else:
        current_user.nome_oficial = linha.nome
        revincular()
        db.session.commit()
        flash(f"Pronto — seus resultados estão ligados a {linha.nome}.", "success")
    return redirect(url_for("simulados.turma_detalhe", turma_id=linha.turma_id))


@simulados_bp.post("/turma/<int:turma_id>/trazer")
@login_required
def turma_trazer(turma_id):
    """Copia a linha do usuário para o Simulado pessoal dele. Sempre opt-in.

    Nunca sobrescreve um registro que a pessoa digitou à mão, e nunca encosta
    na observação — aquilo é dela."""
    turma = _get_turma(turma_id)
    linha = next((ln for ln in turma.linhas if ln.user_id == current_user.id), None)
    if linha is None or linha.status != "presente":
        abort(404)

    concurso = db.session.get(Concurso, request.form.get("concurso_id", type=int) or 0)
    if concurso is None:
        flash("Escolha para qual concurso esse simulado conta.", "error")
        return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))

    existente = db.session.scalar(
        db.select(Simulado).filter_by(user_id=current_user.id, rotulo=turma.rotulo)
    )
    if existente is not None and not existente.veio_de_import:
        flash(
            f"Você já lançou o {turma.rotulo} à mão. Não vou sobrescrever — "
            "exclua o seu registro antes, se quiser usar os números do ranking.",
            "error",
        )
        return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))

    # Calcula tudo ANTES de mexer na sessão: nota_geral é NOT NULL, então o
    # registro só pode ir ao banco já com a nota pronta.
    permitidas = {m.name for m in concurso.materias}
    notas, percentuais = [], []
    for materia in turma.materias:
        certas = linha.acertos.get(materia.name)
        total = turma.questoes.get(materia.name)
        if certas is None or not total or materia.name not in permitidas:
            continue
        notas.append((materia, certas, total))
        percentuais.append(100.0 * certas / total)

    if not percentuais:
        flash(f"Nenhuma matéria do {concurso.nome} caiu nesse simulado.", "error")
        return redirect(url_for("simulados.turma_detalhe", turma_id=turma.id))

    # Posição sob a MESMA régua da nota (as matérias do concurso escolhido), para
    # os dois números do registro contarem a mesma história.
    posicao = next(
        (
            pos
            for pos, ln, _ in turma.ranking([m for m, _, _ in notas])
            if ln.id == linha.id
        ),
        None,
    )

    simulado = existente or Simulado(user_id=current_user.id)
    simulado.concurso_id = concurso.id
    simulado.rotulo = turma.rotulo
    simulado.data_simulado = turma.data
    simulado.origem = "import"
    simulado.nota_geral = round(sum(percentuais) / len(percentuais), 2)
    simulado.nota_automatica = True
    simulado.posicao_estimada = posicao
    if existente is None:
        db.session.add(simulado)

    # Regravar as matérias: DELETE antes do INSERT para não bater no UNIQUE.
    simulado.materias.clear()
    db.session.flush()
    for materia, certas, total in notas:
        simulado.materias.append(
            SimuladoMateria(materia=materia, acertos=certas, total_questoes=total)
        )
    db.session.commit()
    flash(
        f"{turma.rotulo} trazido para os seus simulados.", "success"
    )
    return redirect(url_for("simulados.detalhe", simulado_id=simulado.id))
