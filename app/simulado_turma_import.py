"""Validação do JSON de importação do ranking de um simulado da turma.

Prompt de extração em docs/PROMPT-EXTRACAO-SIMULADO.md. Aqui os números são
QUANTIDADES DE ACERTOS (inteiros), não notas — e o total de questões vem do
padrão da banca (models.QUESTOES_PADRAO), não do JSON.
"""

import json
from datetime import date

from .alunos import resolver_aluno
from .models import (
    QUESTOES_PADRAO,
    Materia,
    SimuladoTurma,
    SimuladoTurmaLinha,
    normalizar_nome,
)
from .oficiais_import import ErroImport, materia_por_codigo
from .validacao import (
    _ALIAS_TURMA,
    _texto,
    validar_acertos,
    validar_geral_oficial,
    validar_status,
)


def _inteiro(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroImport(f'"{campo}" precisa ser inteiro (veio {valor!r}).')
    return valor


def _questoes_da_banca(banca: str, materias, do_json) -> dict:
    """Total de questões por matéria: o que veio no JSON, senão o padrão da banca."""
    if do_json:
        if not isinstance(do_json, dict):
            raise ErroImport('"questoes" precisa ser um objeto código→total (ou null).')
        questoes = {}
        for codigo, valor in do_json.items():
            materia = materia_por_codigo(codigo)
            if materia is None:
                raise ErroImport(f"Matéria desconhecida em 'questoes': {codigo!r}.")
            total = _inteiro(valor, f"questoes.{codigo}")
            if total < 1:
                raise ErroImport(f"Total de questões de {materia.value} precisa ser >= 1.")
            questoes[materia.name] = total
    else:
        padrao = QUESTOES_PADRAO.get(banca.upper())
        if padrao is None:
            raise ErroImport(
                f'Não conheço o número de questões da banca "{banca}". '
                "Informe o campo \"questoes\" no JSON (ex.: {\"MAT\": 12, \"FIS\": 12})."
            )
        questoes = dict(padrao)

    faltando = [m.value for m in materias if m.name not in questoes]
    if faltando:
        raise ErroImport(
            "Falta o total de questões de: " + ", ".join(faltando) + "."
        )
    return {m.name: questoes[m.name] for m in materias}


def _linha(bruta, indice, materias, questoes, turma):
    onde = f"resultado #{indice}"
    if not isinstance(bruta, dict):
        raise ErroImport(f"{onde}: cada item de 'resultados' precisa ser um objeto.")

    nome = _texto(bruta.get("nome"), f"nome ({onde})", 120)
    status = validar_status(
        bruta.get("status", "presente"), SimuladoTurmaLinha.STATUS, onde, nome
    )

    serie = _texto(bruta.get("serie"), f"serie ({onde})", 20, obrigatorio=False)

    if status == "ausente":
        return {
            "nome": nome, "nome_norm": normalizar_nome(nome), "serie": serie,
            "turma": turma, "status": status, "acertos": {},
            "media_oficial": None, "geral_oficial": None,
        }

    brutos = bruta.get("acertos") or {}
    if not isinstance(brutos, dict) or not brutos:
        raise ErroImport(f"{onde} ({nome}): faltam os acertos por matéria.")

    permitidas = {m.name for m in materias}
    acertos = {}
    for codigo, valor in brutos.items():
        materia = materia_por_codigo(codigo)
        if materia is None:
            raise ErroImport(f"{onde} ({nome}): matéria desconhecida {codigo!r}.")
        if materia.name not in permitidas:
            raise ErroImport(
                f"{onde} ({nome}): {materia.value} não está na lista 'materias' do "
                "cabeçalho. Cuidado com as colunas calculadas (soma, MÉDIA, GERAL)."
            )
        total = questoes[materia.name]
        certas = _inteiro(valor, f"acertos de {materia.value} ({onde}, {nome})")
        validar_acertos(certas, total, materia, onde, nome)
        acertos[materia.name] = certas

    faltando = [m.value for m in materias if m.name not in acertos]
    if faltando:
        raise ErroImport(f"{onde} ({nome}): faltam os acertos de " + ", ".join(faltando) + ".")

    if not any(acertos.values()):
        raise ErroImport(
            f"{onde} ({nome}): zerou em todas as matérias — se a pessoa faltou, "
            'marque status "ausente".'
        )

    def numero(chave):
        valor = bruta.get(chave)
        if valor is None:
            return None
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErroImport(f'{onde} ({nome}): "{chave}" precisa ser número.')
        return float(valor)

    geral = numero("geral_oficial")
    soma = sum(acertos.values())
    validar_geral_oficial(geral, soma, onde, nome)

    return {
        "nome": nome, "nome_norm": normalizar_nome(nome), "serie": serie,
        # Turma vem do cabeçalho e vale para todas as pessoas desta lista.
        "turma": turma, "status": status, "acertos": acertos,
        "media_oficial": numero("media_oficial"), "geral_oficial": geral,
    }


def parse(texto: str, data_padrao=None) -> dict:
    """Valida o JSON do ranking. `data_padrao` cobre o caso de "data": null.

    Muitas planilhas do colégio não trazem data no título ("Simulado S5 ITA -
    1ª e 2ª fase"), e o extrator é instruído a devolver null em vez de inventar.
    A data continua obrigatória (faz parte da chave da prova), mas pode chegar
    pelo formulário de import em vez de vir no JSON."""
    if not (texto or "").strip():
        raise ErroImport("Cole o JSON do ranking.")
    try:
        dados = json.loads(texto)
    except ValueError as exc:
        raise ErroImport(f"JSON inválido: {exc}")
    if not isinstance(dados, dict):
        raise ErroImport("O JSON precisa ser um objeto (começar com '{').")

    tipo = normalizar_nome(dados.get("tipo", "simulado")).lower()
    if tipo != "simulado":
        raise ErroImport(
            f'Este import é para ranking de simulado; veio tipo {tipo!r}. '
            "Listão de concurso vai na aba Oficiais."
        )

    banca = _texto(dados.get("banca"), "banca", 40)
    rotulo = _texto(dados.get("rotulo"), "rotulo", 20)
    fonte = _texto(dados.get("fonte"), "fonte", 40, obrigatorio=False)

    fase = normalizar_nome(dados.get("fase", "objetiva")).lower()
    if fase not in SimuladoTurma.FASES:
        raise ErroImport(
            f'Fase {dados.get("fase")!r} não existe. Use '
            f'{" ou ".join(repr(f) for f in SimuladoTurma.FASES)}.'
        )

    turma = _ALIAS_TURMA.get(normalizar_nome(dados.get("turma", "novata")))
    if turma is None:
        raise ErroImport('O campo "turma" precisa ser "novata" ou "veterana".')

    bruta_data = dados.get("data")
    if bruta_data in (None, ""):
        # O extrator devolve null quando o título não tem data; nesse caso ela
        # vem do formulário de import.
        data_prova = data_padrao
        if data_prova is None:
            raise ErroImport(
                'O JSON veio com "data": null (o título da planilha não tinha '
                "data). Informe a data da prova no campo acima do formulário."
            )
    else:
        try:
            data_prova = date.fromisoformat(str(bruta_data).strip())
        except ValueError:
            raise ErroImport(
                '"data" precisa estar no formato AAAA-MM-DD. Cuidado: o título do '
                "ranking costuma vir em DD-MM-AAAA."
            )

    codigos = dados.get("materias")
    if not isinstance(codigos, list) or not codigos:
        raise ErroImport('"materias" precisa ser uma lista com pelo menos uma matéria.')
    materias, vistas = [], set()
    for codigo in codigos:
        materia = materia_por_codigo(codigo)
        if materia is None:
            raise ErroImport(f"Matéria desconhecida em 'materias': {codigo!r}.")
        if materia.name in vistas:
            raise ErroImport(f"Matéria repetida em 'materias': {materia.value}.")
        vistas.add(materia.name)
        materias.append(materia)

    questoes = _questoes_da_banca(banca, materias, dados.get("questoes"))

    materias_media = []
    for codigo in dados.get("materias_media") or []:
        materia = materia_por_codigo(codigo)
        if materia is None:
            raise ErroImport(f"Matéria desconhecida em 'materias_media': {codigo!r}.")
        if materia.name not in vistas:
            raise ErroImport(
                f"{materia.value} está em 'materias_media' mas não em 'materias'."
            )
        materias_media.append(materia)

    brutos = dados.get("resultados")
    if not isinstance(brutos, list) or not brutos:
        raise ErroImport('"resultados" precisa ser uma lista com pelo menos uma pessoa.')

    linhas = [
        _linha(b, i, materias, questoes, turma) for i, b in enumerate(brutos, start=1)
    ]

    vistos = set()
    for linha in linhas:
        if linha["nome_norm"] in vistos:
            raise ErroImport(f"Nome repetido na lista: {linha['nome']}.")
        vistos.add(linha["nome_norm"])

    resumo = {s: sum(1 for ln in linhas if ln["status"] == s) for s in SimuladoTurmaLinha.STATUS}
    return {
        "banca": banca, "rotulo": rotulo, "data": data_prova, "turma": turma,
        "fase": fase, "fonte": fonte, "materias": materias,
        "materias_media": materias_media, "questoes": questoes,
        "linhas": linhas, "resumo": resumo,
    }


def _conferir_cabecalho(existente: SimuladoTurma, dados: dict) -> None:
    """A prova é a mesma para as duas turmas: o cabeçalho tem que bater."""
    if {m.name for m in existente.materias} != {m.name for m in dados["materias"]}:
        atual = ", ".join(m.value for m in existente.materias)
        novo = ", ".join(m.value for m in dados["materias"])
        raise ErroImport(
            f"A outra turma de {existente.nome} foi importada com as matérias "
            f"[{atual}], e este JSON traz [{novo}]. As duas turmas fazem a mesma "
            "prova: acerte o cabeçalho ou exclua a prova e reimporte as duas."
        )
    if {m.name for m in existente.materias_media} != {
        m.name for m in dados["materias_media"]
    }:
        raise ErroImport(
            f"A MÉDIA oficial de {existente.nome} foi importada com um conjunto de "
            "matérias diferente do que veio neste JSON. Confira o cabeçalho."
        )
    if existente.questoes != dados["questoes"]:
        raise ErroImport(
            f"O total de questões de {existente.nome} não bate com o da outra "
            f"turma ({existente.questoes} vs {dados['questoes']})."
        )
    if existente.fase != dados["fase"]:
        raise ErroImport(
            f"{existente.nome} já foi importado como fase '{existente.fase}' e "
            f"este JSON diz '{dados['fase']}'."
        )


def _conferir_conflitos_entre_turmas(existente: SimuladoTurma, dados: dict) -> None:
    """Mesma pessoa nas duas turmas é erro de turma informada, não dado real."""
    outras = {
        ln.nome_norm: ln for ln in existente.linhas if ln.turma != dados["turma"]
    }
    for nova in dados["linhas"]:
        antiga = outras.get(nova["nome_norm"])
        if antiga is not None:
            raise ErroImport(
                f'{nova["nome"]} aparece na turma {dados["turma"]} deste JSON e '
                f"também na turma {antiga.turma} já importada desta prova. Ou a "
                "pessoa foi listada duas vezes, ou a turma de um dos imports está "
                "errada."
            )


def aplicar(db, dados: dict, user_id: int) -> SimuladoTurma:
    """Grava o ranking validado, substituindo APENAS a turma que veio no JSON.

    A prova é uma só (chave banca+rótulo+data): reimportar a novata não pode
    encostar na veterana, então o delete é filtrado por turma."""
    simulado = db.session.scalar(
        db.select(SimuladoTurma).filter_by(
            banca=dados["banca"], rotulo=dados["rotulo"], data=dados["data"]
        )
    )

    if simulado is None:
        simulado = SimuladoTurma(
            banca=dados["banca"],
            rotulo=dados["rotulo"],
            data=dados["data"],
            fase=dados["fase"],
            fonte=dados["fonte"],
            created_by=user_id,
        )
        simulado.set_materias(dados["materias"])
        simulado.set_materias(dados["materias_media"], campo="materias_media_csv")
        simulado.set_questoes(dados["questoes"])
        db.session.add(simulado)
    else:
        _conferir_cabecalho(simulado, dados)
        _conferir_conflitos_entre_turmas(simulado, dados)
        simulado.fonte = simulado.fonte or dados["fonte"]
        for antiga in [ln for ln in simulado.linhas if ln.turma == dados["turma"]]:
            simulado.linhas.remove(antiga)
        db.session.flush()

    for bruta in dados["linhas"]:
        linha = SimuladoTurmaLinha(
            nome=bruta["nome"],
            nome_norm=bruta["nome_norm"],
            serie=bruta["serie"],
            turma=bruta["turma"],
            aluno_id=resolver_aluno(bruta["nome"]).id,
            status=bruta["status"],
            media_oficial=bruta["media_oficial"],
            geral_oficial=bruta["geral_oficial"],
        )
        linha.set_acertos(bruta["acertos"])
        simulado.linhas.append(linha)
    return simulado
