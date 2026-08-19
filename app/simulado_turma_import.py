"""Validação do JSON de importação do ranking de um simulado da turma.

Duas fases, dois formatos de número, dois prompts de extração:

- 1ª fase (objetiva), docs/PROMPT-EXTRACAO-SIMULADO.md — os valores são
  QUANTIDADES DE ACERTOS (inteiros) sobre um total de questões que vem do
  padrão da banca (models.QUESTOES_PADRAO), não do JSON.
- 2ª fase (discursiva), docs/PROMPT-EXTRACAO-2FASE.md — os valores são NOTAS
  DECIMAIS de 0 a 10. Não existe total de questões, e por isso não existe
  `questoes` nem `geral_oficial` aqui.

Os conjuntos de matérias DIFEREM entre as fases do mesmo simulado: no ITA S5 o
discursivo tem POR e RED e não tem ING; a objetiva tem ING e não tem POR nem
RED. Cada fase é uma prova própria (a `fase` está na chave única), então cada
uma carrega o próprio cabeçalho sem conflito.
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
    validar_nota,
    validar_status,
)

# Escala da nota na 2ª fase. A mesma régua do mural do colégio.
ESCALA_DISCURSIVA = 10.0


def _inteiro(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroImport(f'"{campo}" precisa ser inteiro (veio {valor!r}).')
    return valor


def _questoes_da_banca(banca: str, materias, do_json, fase="objetiva") -> dict:
    """Total de questões por matéria: o que veio no JSON, senão o padrão da banca.

    Vazio na 2ª fase: lá a nota já nasce em 0–10 e não há questões para contar.
    Sem esta saída, o import da discursiva morria no cabeçalho reclamando que
    falta o total de questões de Português, Inglês e Redação — e "resolver"
    inventando totais faria a validação de acertos rejeitar 5,70 por não ser
    inteiro. A estrutura não deve fingir que existe um total."""
    if fase == "discursiva":
        return {}
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


def _linha_discursiva(bruta, onde, nome, serie, turma, status, materias):
    """Uma pessoa na 2ª fase: notas decimais 0–10, sem total de questões.

    Duas diferenças que NÃO são detalhe em relação à objetiva:

    1. Zerar tudo é legítimo aqui. Na objetiva, quem zera todas as matérias
       quase certamente faltou (chute acerta alguma), e o import recusa pedindo
       status "ausente". Na discursiva zerar é comum — a planilha do ITA S5 tem
       uma linha 0,00 0,00 0,20 0,00 0,00, e há quem zere tudo e ainda tenha
       média. Aplicar aqui a regra da objetiva recusaria dado real.
    2. Célula vazia não é zero. Ausência de matéria é erro de extração e para o
       import; 0,00 é nota. Por isso toda matéria do cabeçalho é obrigatória.
    """
    brutas = bruta.get("notas") or {}
    if not isinstance(brutas, dict) or not brutas:
        raise ErroImport(
            f"{onde} ({nome}): faltam as notas por matéria. Se a pessoa não fez "
            'a discursiva, marque status "ausente" — zero não é ausência.'
        )

    permitidas = {m.name for m in materias}
    notas = {}
    for codigo, valor in brutas.items():
        materia = materia_por_codigo(codigo)
        if materia is None:
            raise ErroImport(f"{onde} ({nome}): matéria desconhecida {codigo!r}.")
        if materia.name not in permitidas:
            raise ErroImport(
                f"{onde} ({nome}): {materia.value} não está na lista 'materias' do "
                "cabeçalho. Cuidado com as colunas calculadas (MÉDIA, MÉDIA FINAL)."
            )
        nota = _numero_decimal(valor, f"nota de {materia.value} ({onde}, {nome})")
        # Mesma validação de escala que os listões oficiais usam.
        validar_nota(nota, ESCALA_DISCURSIVA, materia, onde, nome)
        notas[materia.name] = nota

    faltando = [m.value for m in materias if m.name not in notas]
    if faltando:
        raise ErroImport(
            f"{onde} ({nome}): faltam as notas de " + ", ".join(faltando) + ". "
            "Célula vazia não é zero — confira a extração."
        )

    # NÃO há checagem de "zerou em tudo": ver o docstring.

    def numero(chave):
        valor = bruta.get(chave)
        return None if valor is None else _numero_decimal(valor, f"{onde}: {chave}")

    return {
        "nome": nome, "nome_norm": normalizar_nome(nome), "serie": serie,
        "turma": turma, "status": status, "acertos": {}, "notas": notas,
        # `media_oficial` e `geral_oficial` são da objetiva e têm contrato
        # exato; o número da discursiva vive em campo próprio, sem carimbo.
        "media_oficial": None, "geral_oficial": None,
        "media_informada": numero("media_oficial"),
        # `media_final_oficial` é o nome que o prompt emite. Ler um nome
        # diferente aqui perderia a MÉDIA FINAL em silêncio — que é o pior
        # jeito de errar: o import passa, a tela fica vazia e ninguém sabe.
        # `_avisos_de_campo_desconhecido` existe para pegar essa classe inteira.
        "media_final_informada": numero("media_final_oficial"),
    }


def _numero_decimal(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroImport(f'"{campo}" precisa ser número (veio {valor!r}).')
    return float(valor)


def _linha(bruta, indice, materias, questoes, turma, fase="objetiva"):
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
            "turma": turma, "status": status, "acertos": {}, "notas": {},
            "media_oficial": None, "geral_oficial": None,
            "media_informada": None, "media_final_informada": None,
        }

    if fase == "discursiva":
        return _linha_discursiva(bruta, onde, nome, serie, turma, status, materias)

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
        "turma": turma, "status": status, "acertos": acertos, "notas": {},
        "media_oficial": numero("media_oficial"), "geral_oficial": geral,
        # Campos da 2ª fase: sempre nulos aqui. A objetiva tem `media_oficial`,
        # que é outra coisa — conferida contra a soma dos acertos.
        "media_informada": None, "media_final_informada": None,
    }


# Pesos da MÉDIA do bloco discursivo do ITA, observados na planilha do S5 e
# conferidos linha a linha, inclusive nos extremos (0,00 0,00 0,20 0,00 0,00 ->
# 0,40/8 = 0,05). Exatas pesam o dobro de Português e Redação.
#
# Isto NÃO é fonte de nada: nenhum número do app sai daqui. Serve só para
# AVISAR quando a média copiada da planilha discorda da conta — sinal de que a
# leitura errou uma célula. Se o colégio mudar o peso, o copiado continua certo
# e este aviso vira ruído, e aí a resposta é apagar estes pesos, não recalcular.
PESOS_MEDIA_ITA_DISCURSIVA = {
    "MATEMATICA": 2, "QUIMICA": 2, "FISICA": 2, "PORTUGUES": 1, "REDACAO": 1,
}

# Divergência tolerada antes de avisar: a planilha mostra 2 casas.
TOLERANCIA_MEDIA = 0.01


# Tudo que `_linha` e `_linha_discursiva` sabem ler de uma pessoa. Chave fora
# desta lista é campo que o extrator produziu e o import descarta.
CAMPOS_DA_PESSOA = {
    "nome", "serie", "status", "acertos", "notas",
    "media_oficial", "geral_oficial", "media_final_oficial",
}


def _avisos_de_campo_desconhecido(brutos) -> list:
    """Avisa quando o JSON traz campo que o import não lê.

    Esta guarda nasceu de um erro real: o prompt passou a emitir
    `media_final_oficial` e o parser continuou lendo `media_final`. O import
    passava, a coluna MÉDIA FINAL sumia e nada reclamava — dado perdido em
    silêncio, que é o pior modo de falha possível.

    Avisa em vez de bloquear, pelo mesmo motivo dos outros avisos: um extrator
    que acrescenta um campo inofensivo não deve travar a importação da turma.
    Mas o admin vê, na tela, antes de confirmar.
    """
    desconhecidos = set()
    for bruta in brutos:
        if isinstance(bruta, dict):
            desconhecidos |= set(bruta) - CAMPOS_DA_PESSOA
    if not desconhecidos:
        return []
    return [
        "O JSON traz campo(s) que o import não lê e vai DESCARTAR: "
        + ", ".join(sorted(desconhecidos))
        + ". Confira se o prompt de extração e o import estão falando a mesma "
        "língua antes de confirmar."
    ]


def _avisos_de_media(banca, fase, materias, linhas) -> list:
    """Avisos de leitura sobre a coluna de média. NUNCA bloqueia, nunca corrige.

    Só para o ITA na 2ª fase, e só quando o cabeçalho traz exatamente as cinco
    matérias que a fórmula conhecida cobre. Fora disso o app se cala.

    Por que não para o IME: com as duas fases do S6 em mãos, CINCO famílias de
    hipótese foram testadas contra 12 linhas e todas morreram — a fórmula do
    ITA previa 6,50 e 4,50 na objetiva e errou a segunda por mais de 2 pontos;
    ponderação em dois grupos dá peso negativo para exatas; e há linha cuja
    média (5,10) é maior que o discursivo calculado (4,84) E que a objetiva
    (4,50), então não é nem combinação convexa das duas. Um aviso que dispara
    em toda linha treina o usuário a ignorar aviso — que é pior que não avisar.
    """
    if fase != "discursiva" or banca.strip().upper() != "ITA":
        return []
    if {m.name for m in materias} != set(PESOS_MEDIA_ITA_DISCURSIVA):
        return []

    avisos = []
    for linha in linhas:
        informada = linha.get("media_informada")
        if linha["status"] != "presente" or informada is None:
            continue
        soma = sum(
            PESOS_MEDIA_ITA_DISCURSIVA[nome] * nota
            for nome, nota in linha["notas"].items()
        )
        calculada = soma / sum(PESOS_MEDIA_ITA_DISCURSIVA.values())
        if abs(calculada - informada) > TOLERANCIA_MEDIA:
            avisos.append(
                f"{linha['nome']}: a planilha diz média {informada:.2f}, mas a "
                f"fórmula do ITA dá {calculada:.2f}. Confira a leitura das notas "
                "dessa linha. O import segue com o número da planilha."
            )
    return avisos


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

    # Segunda data do título, quando existe. GUARDADA E IGNORADA: a 1ª fase do
    # IME S6 é de 04/07 e a 2ª traz "11/07 - 14/04" — a segunda data não aponta
    # para a outra fase, parece resto de template. Não serve para casar fases
    # nem para deduzir data nenhuma; quem casa fases é (banca, rotulo).
    bruta_secundaria = dados.get("data_secundaria")
    data_secundaria = None
    if bruta_secundaria not in (None, ""):
        try:
            data_secundaria = date.fromisoformat(str(bruta_secundaria).strip())
        except ValueError:
            raise ErroImport(
                '"data_secundaria" precisa estar no formato AAAA-MM-DD (ou null).'
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

    questoes = _questoes_da_banca(banca, materias, dados.get("questoes"), fase)

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
        _linha(b, i, materias, questoes, turma, fase)
        for i, b in enumerate(brutos, start=1)
    ]

    vistos = set()
    for linha in linhas:
        if linha["nome_norm"] in vistos:
            raise ErroImport(f"Nome repetido na lista: {linha['nome']}.")
        vistos.add(linha["nome_norm"])

    resumo = {s: sum(1 for ln in linhas if ln["status"] == s) for s in SimuladoTurmaLinha.STATUS}
    return {
        "banca": banca, "rotulo": rotulo, "data": data_prova, "turma": turma,
        "data_secundaria": data_secundaria,
        "fase": fase, "fonte": fonte, "materias": materias,
        "materias_media": materias_media, "questoes": questoes,
        "linhas": linhas, "resumo": resumo,
        "avisos": (
            _avisos_de_campo_desconhecido(brutos)
            + _avisos_de_media(banca, fase, materias, linhas)
        ),
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
    # Não há mais checagem de fase aqui: desde que `fase` entrou na chave única
    # (d7b2e94a1c60), duas fases são duas provas distintas, e `aplicar()` só
    # chega neste ponto com a prova da MESMA fase. A checagem antiga nunca mais
    # dispararia — e guarda que não dispara vira comentário que mente.


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

    A prova é uma só (chave banca+rótulo+data+FASE): reimportar a novata não
    pode encostar na veterana, então o delete é filtrado por turma.

    A `fase` na busca não é detalhe: sem ela, importar a 2ª fase encontraria a
    linha da 1ª e cairia no ramo de reimport logo abaixo, que apaga as linhas
    daquela turma antes de gravar as novas. A objetiva sumiria em silêncio."""
    simulado = db.session.scalar(
        db.select(SimuladoTurma).filter_by(
            banca=dados["banca"], rotulo=dados["rotulo"], data=dados["data"],
            fase=dados["fase"],
        )
    )

    if simulado is None:
        simulado = SimuladoTurma(
            banca=dados["banca"],
            rotulo=dados["rotulo"],
            data=dados["data"],
            data_secundaria=dados["data_secundaria"],
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
            media_informada=bruta["media_informada"],
            media_final_informada=bruta["media_final_informada"],
        )
        linha.set_acertos(bruta["acertos"])
        linha.set_notas(bruta["notas"])
        simulado.linhas.append(linha)
    return simulado
