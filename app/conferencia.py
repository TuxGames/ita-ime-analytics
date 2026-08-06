"""Relatório de qualidade dos dados importados.

Os campos numéricos têm trava aritmética (limite por matéria, GERAL vs soma,
escala) e por isso são confiáveis. `nome`, `serie` e `turma` NÃO têm trava
nenhuma — é exatamente onde os erros de OCR aparecem, e já foi observado na
prática a mesma planilha extraída duas vezes produzir séries diferentes para a
mesma pessoa.

Nada aqui bloqueia: as validações que barram estão em oficiais_import e
simulado_turma_import. Isto é para o admin bater o olho depois de importar.
"""

from collections import defaultdict

from .extensions import db
from .models import (
    TURMA_CURTO,
    ResultadoLinha,
    ResultadoOficial,
    SimuladoTurma,
    SimuladoTurmaLinha,
)

# Ordem de progressão das séries. Quem está em "3º ANO" não volta para "2º ANO";
# pode repetir, avançar, ou sair do EM (CURSO). O que não pode é regredir.
_ORDEM_SERIE = {"1º ANO": 1, "2º ANO": 2, "3º ANO": 3, "CURSO": 4}


def _nivel(serie):
    return _ORDEM_SERIE.get((serie or "").strip().upper())


def _linhas_de_simulado():
    """[(data, prova, linha)] de todos os rankings, em ordem cronológica."""
    provas = db.session.scalars(
        db.select(SimuladoTurma).order_by(SimuladoTurma.data)
    ).all()
    return [(p.data, p, ln) for p in provas for ln in p.linhas]


def serie_que_regride() -> list[dict]:
    """Pessoa que aparece numa série mais baixa num simulado POSTERIOR."""
    por_pessoa = defaultdict(list)
    for data, prova, linha in _linhas_de_simulado():
        if _nivel(linha.serie) is not None:
            por_pessoa[linha.nome_norm].append((data, prova, linha))

    avisos = []
    for nome_norm, ocorrencias in por_pessoa.items():
        ocorrencias.sort(key=lambda item: item[0])
        for (data_a, prova_a, linha_a), (data_b, prova_b, linha_b) in zip(
            ocorrencias, ocorrencias[1:]
        ):
            if _nivel(linha_b.serie) < _nivel(linha_a.serie):
                avisos.append(
                    {
                        "nome": linha_b.nome,
                        "de": f"{linha_a.serie} em {prova_a.nome} ({data_a})",
                        "para": f"{linha_b.serie} em {prova_b.nome} ({data_b})",
                    }
                )
    return avisos


def nomes_que_aparecem_uma_vez() -> list[dict]:
    """Candidatos a truncamento ou abreviação de nome.

    Casos reais: "MARCUS VINICIUS BERNARDINO DE OLIVEIRA M" (cortado na largura
    da célula) e "DANIEL DOURADO O. XIMENES" vs "...OLIVEIRA XIMENES". Não há
    correção automática segura — só dá para reportar para decisão humana."""
    ocorrencias = defaultdict(list)
    for _data, prova, linha in _linhas_de_simulado():
        ocorrencias[linha.nome_norm].append(prova.nome)
    for resultado in db.session.scalars(db.select(ResultadoOficial)):
        for linha in resultado.linhas:
            ocorrencias[linha.nome_norm].append(resultado.concurso_nome)

    nomes = {}
    for _data, _prova, linha in _linhas_de_simulado():
        nomes.setdefault(linha.nome_norm, linha.nome)
    for resultado in db.session.scalars(db.select(ResultadoOficial)):
        for linha in resultado.linhas:
            nomes.setdefault(linha.nome_norm, linha.nome)

    return sorted(
        (
            {"nome": nomes[chave], "onde": onde[0]}
            for chave, onde in ocorrencias.items()
            if len(onde) == 1
        ),
        key=lambda item: item["nome"],
    )


def pessoa_em_duas_turmas() -> list[dict]:
    """Mesma pessoa com turmas diferentes ENTRE provas.

    Dentro da mesma prova isso já é bloqueado no import; aqui o caso é a turma
    ter sido informada errada em algum dos arquivos."""
    turmas_por_pessoa = defaultdict(set)
    nomes = {}
    for _data, prova, linha in _linhas_de_simulado():
        turmas_por_pessoa[linha.nome_norm].add(linha.turma)
        nomes[linha.nome_norm] = linha.nome
    for resultado in db.session.scalars(db.select(ResultadoOficial)):
        for linha in resultado.linhas:
            turmas_por_pessoa[linha.nome_norm].add(linha.turma)
            nomes[linha.nome_norm] = linha.nome

    return [
        {
            "nome": nomes[chave],
            "turmas": [TURMA_CURTO.get(t, t) for t in sorted(turmas)],
        }
        for chave, turmas in sorted(turmas_por_pessoa.items())
        if len(turmas) > 1
    ]


def contagem_por_turma() -> dict:
    """Quantas pessoas por turma em cada prova/listão, para o admin conferir."""
    provas = []
    for prova in db.session.scalars(
        db.select(SimuladoTurma).order_by(SimuladoTurma.data.desc())
    ):
        provas.append(
            {
                "nome": f"{prova.nome} ({prova.data})",
                "por_turma": {
                    TURMA_CURTO.get(t, t): prova.total_de(t)
                    for t in prova.turmas_presentes
                },
            }
        )
    listoes = []
    for resultado in db.session.scalars(
        db.select(ResultadoOficial).order_by(ResultadoOficial.concurso_nome)
    ):
        listoes.append(
            {
                "nome": resultado.concurso_nome,
                "por_turma": {
                    TURMA_CURTO.get(t, t): resultado.total_de(t)
                    for t in resultado.turmas_presentes
                },
            }
        )
    return {"simulados": provas, "oficiais": listoes}


def relatorio() -> dict:
    """Tudo de uma vez. Só leitura — não altera nada."""
    return {
        "serie_regride": serie_que_regride(),
        "nomes_solitarios": nomes_que_aparecem_uma_vez(),
        "duas_turmas": pessoa_em_duas_turmas(),
        "contagem": contagem_por_turma(),
    }


def tem_alerta(dados: dict) -> bool:
    return bool(
        dados["serie_regride"] or dados["nomes_solitarios"] or dados["duas_turmas"]
    )


def _resumo_texto(dados: dict) -> list[str]:
    """Mesmo conteúdo do relatório, em linhas de texto (para o CLI)."""
    linhas = []
    if dados["serie_regride"]:
        linhas.append("SÉRIE QUE REGRIDE (provável erro de leitura):")
        for aviso in dados["serie_regride"]:
            linhas.append(f"  - {aviso['nome']}: {aviso['de']} -> {aviso['para']}")
    if dados["duas_turmas"]:
        linhas.append("PESSOA EM DUAS TURMAS (turma informada errada em algum import):")
        for aviso in dados["duas_turmas"]:
            linhas.append(f"  - {aviso['nome']}: {', '.join(aviso['turmas'])}")
    if dados["nomes_solitarios"]:
        linhas.append("NOMES QUE APARECEM UMA VEZ SÓ (truncamento ou abreviação?):")
        for aviso in dados["nomes_solitarios"]:
            linhas.append(f"  - {aviso['nome']} (só em {aviso['onde']})")
    linhas.append("CONTAGEM POR TURMA:")
    for grupo, titulo in (("simulados", "Simulados"), ("oficiais", "Listões")):
        for item in dados["contagem"][grupo]:
            partes = ", ".join(f"{n} {t.lower()}" for t, n in item["por_turma"].items())
            linhas.append(f"  [{titulo}] {item['nome']}: {partes}")
    return linhas


def registrar_cli(app):
    import click

    @app.cli.command("conferir-import")
    def conferir_import():
        """Relatório de qualidade dos dados importados (só leitura)."""
        dados = relatorio()
        for linha in _resumo_texto(dados):
            click.echo(linha)
        if not tem_alerta(dados):
            click.echo("Nenhum alerta de nome, série ou turma.")
