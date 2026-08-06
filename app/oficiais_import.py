"""Validação do JSON de importação de resultado oficial.

O admin cola o JSON gerado a partir do listão (o prompt de extração está em
docs/PROMPT-EXTRACAO.md). Nada aqui toca o banco: a função `parse` devolve uma
estrutura pronta, ou levanta ErroImport com uma mensagem em português dizendo
exatamente qual campo está errado — o objetivo é pegar erro de extração (um 8
que virou 3, uma matéria a mais) antes de gravar.
"""

import json
from datetime import date

from .alunos import resolver_aluno
from .models import Materia, ResultadoLinha, ResultadoOficial, normalizar_nome

TIPOS_SUPORTADOS = ("oficial",)

# Aceita tanto o código curto do listão quanto o nome por extenso.
_ALIAS_MATERIA = {
    "MAT": Materia.MATEMATICA, "MATEMATICA": Materia.MATEMATICA,
    "FIS": Materia.FISICA, "FISICA": Materia.FISICA,
    "QUI": Materia.QUIMICA, "QUIM": Materia.QUIMICA, "QUIMICA": Materia.QUIMICA,
    "PORT": Materia.PORTUGUES, "PORTUGUES": Materia.PORTUGUES,
    "ING": Materia.INGLES, "INGLES": Materia.INGLES,
    "RED": Materia.REDACAO, "REDACAO": Materia.REDACAO,
    "GEO": Materia.GEOGRAFIA, "GEOGRAFIA": Materia.GEOGRAFIA,
    "HIST": Materia.HISTORIA, "HISTORIA": Materia.HISTORIA,
}

_ALIAS_TURMA = {
    "NOVATA": "novata", "NOVATAS": "novata", "NOVATO": "novata", "NOVATOS": "novata",
    "VETERANA": "veterana", "VETERANAS": "veterana",
    "VETERANO": "veterana", "VETERANOS": "veterana",
}


class ErroImport(Exception):
    """Erro de validação, com mensagem já pronta para mostrar ao admin."""


def materia_por_codigo(codigo):
    """Materia a partir de 'MAT', 'Matemática', 'QUÍM'... ou None."""
    return _ALIAS_MATERIA.get(normalizar_nome(codigo).replace(" ", ""))


def _texto(valor, campo, maximo, obrigatorio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ErroImport(f'O campo "{campo}" é obrigatório.')
        return None
    texto = str(valor).strip()
    if len(texto) > maximo:
        raise ErroImport(f'O campo "{campo}" passa de {maximo} caracteres.')
    return texto


def _numero(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroImport(f'"{campo}" precisa ser número (veio {valor!r}).')
    return float(valor)


def _data(valor):
    if valor in (None, ""):
        return None
    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError:
        raise ErroImport(f'"data" precisa estar no formato AAAA-MM-DD (veio {valor!r}).')


def _linha(bruta, indice, materias, escala, turma):
    """Valida uma entrada de `resultados`. `indice` é 1-based, para a mensagem."""
    onde = f"resultado #{indice}"
    if not isinstance(bruta, dict):
        raise ErroImport(f"{onde}: cada item de 'resultados' precisa ser um objeto.")

    nome = _texto(bruta.get("nome"), f"nome ({onde})", 120)
    status = normalizar_nome(bruta.get("status")).lower().replace(" ", "_")
    if status not in ResultadoLinha.STATUS:
        raise ErroImport(
            f"{onde} ({nome}): status inválido {bruta.get('status')!r}. "
            f"Use um de: {', '.join(ResultadoLinha.STATUS)}."
        )

    classificacao = bruta.get("classificacao")
    if status == "classificado":
        if classificacao is None:
            raise ErroImport(f"{onde} ({nome}): classificado precisa de 'classificacao'.")
        if isinstance(classificacao, bool) or not isinstance(classificacao, int):
            raise ErroImport(f"{onde} ({nome}): 'classificacao' precisa ser inteiro.")
        if classificacao < 1:
            raise ErroImport(f"{onde} ({nome}): 'classificacao' precisa ser >= 1.")
    else:
        classificacao = None

    metrica_valor = bruta.get("metrica")
    if metrica_valor is not None:
        metrica_valor = _numero(metrica_valor, f"metrica ({onde}, {nome})")

    notas = {}
    brutas = bruta.get("notas") or {}
    if not isinstance(brutas, dict):
        raise ErroImport(f"{onde} ({nome}): 'notas' precisa ser um objeto código→nota.")
    permitidas = {m.name for m in materias}
    for codigo, valor in brutas.items():
        materia = materia_por_codigo(codigo)
        if materia is None:
            raise ErroImport(f"{onde} ({nome}): matéria desconhecida {codigo!r}.")
        if materia.name not in permitidas:
            raise ErroImport(
                f"{onde} ({nome}): {materia.value} não está na lista 'materias' do cabeçalho."
            )
        nota = _numero(valor, f"nota de {materia.value} ({onde}, {nome})")
        if nota < 0 or nota > escala:
            raise ErroImport(
                f"{onde} ({nome}): nota de {materia.value} = {nota} fora da escala 0–{escala:g}. "
                "Confira a extração."
            )
        notas[materia.name] = nota

    if status != "nao_encontrado" and not notas:
        raise ErroImport(f"{onde} ({nome}): faltam as notas por matéria.")

    return {
        "nome": nome,
        "nome_norm": normalizar_nome(nome),
        # Turma vem do cabeçalho (o JSON é sempre de uma turma só) e fica
        # carimbada em cada pessoa: é ela que sobrevive no banco.
        "turma": turma,
        "status": status,
        "classificacao": classificacao,
        "metrica_valor": metrica_valor,
        "notas": notas,
    }


def parse(texto: str) -> dict:
    """Valida o JSON colado e devolve a estrutura pronta para virar registros."""
    if not (texto or "").strip():
        raise ErroImport("Cole o JSON do resultado.")
    try:
        dados = json.loads(texto)
    except ValueError as exc:
        raise ErroImport(f"JSON inválido: {exc}")
    if not isinstance(dados, dict):
        raise ErroImport("O JSON precisa ser um objeto (começar com '{').")

    tipo = normalizar_nome(dados.get("tipo", "oficial")).lower()
    if tipo not in TIPOS_SUPORTADOS:
        raise ErroImport(
            f'Tipo {tipo!r} ainda não é suportado — por enquanto só "oficial".'
        )

    concurso = _texto(dados.get("concurso"), "concurso", 80)
    turma = _ALIAS_TURMA.get(normalizar_nome(dados.get("turma")))
    if turma is None:
        raise ErroImport('O campo "turma" precisa ser "novata" ou "veterana".')

    fonte = _texto(dados.get("fonte"), "fonte", 40, obrigatorio=False)
    metrica = _texto(dados.get("metrica"), "metrica", 20, obrigatorio=False)
    data_prova = _data(dados.get("data"))

    escala = dados.get("escala", 10)
    escala = _numero(escala, "escala")
    if escala <= 0:
        raise ErroImport('"escala" precisa ser maior que zero.')

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

    brutos = dados.get("resultados")
    if not isinstance(brutos, list) or not brutos:
        raise ErroImport('"resultados" precisa ser uma lista com pelo menos uma pessoa.')

    linhas = [
        _linha(b, i, materias, escala, turma) for i, b in enumerate(brutos, start=1)
    ]

    nomes_vistos = set()
    for linha in linhas:
        if linha["nome_norm"] in nomes_vistos:
            raise ErroImport(f"Nome repetido no listão: {linha['nome']}.")
        nomes_vistos.add(linha["nome_norm"])

    posicoes = [ln["classificacao"] for ln in linhas if ln["classificacao"]]
    if len(posicoes) != len(set(posicoes)):
        raise ErroImport("Há duas pessoas com a mesma classificação. Confira a extração.")

    resumo = {s: sum(1 for ln in linhas if ln["status"] == s) for s in ResultadoLinha.STATUS}
    return {
        "concurso": concurso,
        "turma": turma,
        "fonte": fonte,
        "data": data_prova,
        "escala": escala,
        "materias": materias,
        "metrica": metrica,
        "linhas": linhas,
        "resumo": resumo,
    }


def _conferir_cabecalho(existente: ResultadoOficial, dados: dict) -> None:
    """A outra turma já definiu a régua do concurso; a nova tem que usar a mesma.

    Matérias e escala mudam o significado dos números, então divergência é erro.
    Métrica, fonte e data são metadados: preenchem se faltavam, senão prevalece o
    que já estava (o admin corrige editando, não reimportando)."""
    if {m.name for m in existente.materias} != {m.name for m in dados["materias"]}:
        atual = ", ".join(m.value for m in existente.materias)
        novo = ", ".join(m.value for m in dados["materias"])
        raise ErroImport(
            f'A outra turma de "{existente.concurso_nome}" foi importada com as '
            f"matérias [{atual}], e este JSON traz [{novo}]. As duas turmas fazem a "
            "mesma prova: acerte o cabeçalho ou exclua o concurso e reimporte as duas."
        )
    if abs((existente.escala or 0) - dados["escala"]) > 1e-9:
        raise ErroImport(
            f'A outra turma de "{existente.concurso_nome}" foi importada na escala '
            f"0–{existente.escala:g}, e este JSON usa 0–{dados['escala']:g}."
        )


def _conferir_conflitos_entre_turmas(existente, dados) -> None:
    """Colisões contra as linhas da OUTRA turma, que o parse sozinho não enxerga."""
    outras = [ln for ln in existente.linhas if ln.turma != dados["turma"]]

    por_nome = {ln.nome_norm: ln for ln in outras}
    for nova in dados["linhas"]:
        antiga = por_nome.get(nova["nome_norm"])
        if antiga is not None:
            raise ErroImport(
                f'{nova["nome"]} aparece na turma {dados["turma"]} deste JSON e '
                f"também na turma {antiga.turma} já importada deste concurso. "
                "Ou a pessoa foi listada duas vezes, ou a turma de um dos imports "
                "está errada."
            )

    # A classificação é NACIONAL: vale para o concurso inteiro, não por turma.
    por_posicao = {
        ln.classificacao: ln
        for ln in outras
        if ln.status == "classificado" and ln.classificacao
    }
    for nova in dados["linhas"]:
        if nova["status"] != "classificado" or not nova["classificacao"]:
            continue
        antiga = por_posicao.get(nova["classificacao"])
        if antiga is not None:
            raise ErroImport(
                f'Classificação {nova["classificacao"]} está com {nova["nome"]} '
                f"({dados['turma']}) e com {antiga.nome} ({antiga.turma}) ao mesmo "
                "tempo. A classificação é nacional: confira a extração."
            )


def aplicar(db, dados: dict, user_id: int) -> ResultadoOficial:
    """Grava o resultado validado, substituindo APENAS a turma que veio no JSON.

    Um concurso tem um registro só (a classificação é nacional). Reimportar a
    novata não pode encostar na veterana — por isso o delete é filtrado por turma
    e as linhas da outra turma ficam onde estão, com seus vínculos."""
    resultado = db.session.scalar(
        db.select(ResultadoOficial).filter_by(concurso_nome=dados["concurso"])
    )

    if resultado is None:
        resultado = ResultadoOficial(
            concurso_nome=dados["concurso"],
            fonte=dados["fonte"],
            data=dados["data"],
            escala=dados["escala"],
            metrica=dados["metrica"],
            created_by=user_id,
        )
        resultado.set_materias(dados["materias"])
        db.session.add(resultado)
    else:
        _conferir_cabecalho(resultado, dados)
        _conferir_conflitos_entre_turmas(resultado, dados)
        # Metadados: completam o que faltava, sem sobrescrever o que já existe.
        resultado.metrica = resultado.metrica or dados["metrica"]
        resultado.fonte = resultado.fonte or dados["fonte"]
        resultado.data = resultado.data or dados["data"]
        # Só as linhas desta turma saem; as da outra permanecem intactas.
        for antiga in [ln for ln in resultado.linhas if ln.turma == dados["turma"]]:
            resultado.linhas.remove(antiga)
        db.session.flush()

    for bruta in dados["linhas"]:
        linha = ResultadoLinha(
            nome=bruta["nome"],
            nome_norm=bruta["nome_norm"],
            turma=bruta["turma"],
            # Resolve a identidade da pessoa (apelido de merge inclusive), para a
            # mesma grafia alternativa não virar um aluno novo a cada import.
            aluno_id=resolver_aluno(bruta["nome"]).id,
            status=bruta["status"],
            classificacao=bruta["classificacao"],
            metrica_valor=bruta["metrica_valor"],
        )
        linha.set_notas(bruta["notas"])
        resultado.linhas.append(linha)
    return resultado
