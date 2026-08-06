"""Resolução de nome para Aluno — o único lugar que decide "quem é essa pessoa".

Os dados vêm de planilhas lidas por OCR, onde a mesma pessoa aparece com grafias
diferentes ("DANIEL DOURADO OLIVEIRA XIMENES" e "DANIEL DOURADO O. XIMENES").
Normalizar acento e espaço resolve parte; o resto é decisão humana, registrada
como apelido no merge. Por isso a busca tem uma ordem fixa e um lugar só.

Nada aqui dá commit: quem commita é a rota, como no resto do projeto.
"""

from .extensions import db
from .models import (
    Aluno,
    AlunoApelido,
    ResultadoLinha,
    SimuladoTurmaLinha,
    normalizar_nome,
)

# As duas tabelas cujas linhas apontam para Aluno.
TABELAS_DE_LINHA = (ResultadoLinha, SimuladoTurmaLinha)


class ErroMerge(Exception):
    """Merge impossível, com mensagem pronta para o admin."""


def encontrar_aluno(nome) -> Aluno | None:
    """Procura sem criar. Apelido primeiro, depois o nome canônico."""
    chave = normalizar_nome(nome)
    if not chave:
        return None
    apelido = db.session.scalar(
        db.select(AlunoApelido).filter_by(nome_norm=chave)
    )
    if apelido is not None:
        return apelido.aluno
    return db.session.scalar(db.select(Aluno).filter_by(nome_norm=chave))


def resolver_aluno(nome) -> Aluno:
    """Devolve o Aluno desse nome, criando um se ainda não existir.

    O flush é necessário porque um mesmo import pode citar o nome novo mais de
    uma vez: sem ele, a segunda chamada não enxergaria o aluno recém-criado e
    criaria um duplicado."""
    aluno = encontrar_aluno(nome)
    if aluno is not None:
        return aluno
    aluno = Aluno(nome=(nome or "").strip(), nome_norm=normalizar_nome(nome))
    db.session.add(aluno)
    db.session.flush()
    return aluno


def linhas_do_aluno(aluno: Aluno) -> dict:
    """{modelo: [linhas]} — tudo em que a pessoa aparece."""
    return {
        modelo: db.session.scalars(
            db.select(modelo).filter_by(aluno_id=aluno.id)
        ).all()
        for modelo in TABELAS_DE_LINHA
    }


def contar_linhas(aluno: Aluno) -> int:
    return sum(
        db.session.scalar(
            db.select(db.func.count(modelo.id)).filter_by(aluno_id=aluno.id)
        )
        for modelo in TABELAS_DE_LINHA
    )


def mesclar(sobrevivente: Aluno, absorvido: Aluno) -> int:
    """Junta dois alunos que são a mesma pessoa. Devolve quantas linhas migraram.

    Reponta as linhas (nunca apaga nenhuma), registra o nome do absorvido como
    apelido — para que um import futuro com aquela grafia caia no aluno certo —
    e remove o absorvido."""
    if sobrevivente.id == absorvido.id:
        raise ErroMerge("Escolha dois alunos diferentes.")
    if sobrevivente.user_id and absorvido.user_id and (
        sobrevivente.user_id != absorvido.user_id
    ):
        raise ErroMerge(
            f"{sobrevivente.nome} e {absorvido.nome} estão vinculados a contas "
            "diferentes. Desfaça um dos vínculos antes de mesclar."
        )

    migradas = 0
    for modelo in TABELAS_DE_LINHA:
        for linha in db.session.scalars(
            db.select(modelo).filter_by(aluno_id=absorvido.id)
        ):
            linha.aluno_id = sobrevivente.id
            migradas += 1

    # O nome do absorvido vira apelido, junto com os apelidos que ele já tinha.
    grafias = [absorvido.nome_norm] + [a.nome_norm for a in absorvido.apelidos]
    db.session.delete(absorvido)
    db.session.flush()  # libera o unique de aluno_apelidos.nome_norm

    for chave in grafias:
        if chave == sobrevivente.nome_norm:
            continue
        ja_existe = db.session.scalar(
            db.select(AlunoApelido).filter_by(nome_norm=chave)
        )
        if ja_existe is None:
            db.session.add(
                AlunoApelido(
                    aluno_id=sobrevivente.id, nome_norm=chave, origem="merge"
                )
            )

    sobrevivente.user_id = sobrevivente.user_id or absorvido.user_id
    return migradas


def candidatos_a_merge() -> list[dict]:
    """Pares suspeitos de serem a mesma pessoa, para o admin decidir.

    Heurística deliberadamente simples e conservadora: um nome ser prefixo do
    outro (truncamento na largura da célula) ou os dois compartilharem primeiro
    e último sobrenome (abreviação do meio). Não mescla nada sozinho — nome é
    justamente o campo sem trava aritmética, então a decisão é humana."""
    alunos = db.session.scalars(db.select(Aluno).order_by(Aluno.nome)).all()
    pares = []
    for i, um in enumerate(alunos):
        for outro in alunos[i + 1:]:
            motivo = _motivo_de_suspeita(um.nome_norm, outro.nome_norm)
            if motivo:
                pares.append({"a": um, "b": outro, "motivo": motivo})
    return pares


def _motivo_de_suspeita(a: str, b: str) -> str | None:
    if not a or not b:
        return None
    if a.startswith(b) or b.startswith(a):
        return "um nome é o começo do outro (provável corte na célula)"
    partes_a, partes_b = a.split(), b.split()
    if len(partes_a) < 2 or len(partes_b) < 2:
        return None
    if partes_a[0] == partes_b[0] and partes_a[-1] == partes_b[-1]:
        return "mesmo primeiro nome e mesmo último sobrenome (provável abreviação)"
    return None
