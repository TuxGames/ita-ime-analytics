"""Códigos de convite: quem entra no app e a que aluno a conta pertence.

O cadastro é aberto (qualquer pessoa cria conta), mas a conta nasce TRANCADA:
sem resgatar um código não se acessa nada além da tela do código e do logout.
O motivo é o dado de 73 alunos — nome completo, série, turma e nota — que antes
ficava a um cadastro de distância de qualquer pessoa na internet.

Como o código é emitido para UM aluno, resgatar já estabelece o vínculo
conta ↔ aluno. Esse vínculo é AUTORITATIVO: `vinculo.revincular()`, que refaz
os vínculos por nome depois de cada import, não pode desfazê-lo.

Nada aqui dá commit: quem comita é a rota, como no resto do projeto.
"""

import secrets

from .extensions import db
from .models import Aluno, ConviteAluno, User, utcnow


def gerar_codigo() -> str:
    """Código novo, curto e sem caractere ambíguo, garantidamente inédito.

    Usa `secrets` (não `random`): o código é credencial de acesso, ainda que de
    uso único — um gerador previsível deixaria adivinhar o convite dos outros.
    """
    while True:
        codigo = "".join(
            secrets.choice(ConviteAluno.ALFABETO) for _ in range(ConviteAluno.TAMANHO)
        )
        existe = db.session.scalar(
            db.select(ConviteAluno.id).filter_by(codigo=codigo)
        )
        if existe is None:
            return codigo


def normalizar_codigo(bruto) -> str:
    """Aceita o que a pessoa digita: minúsculas, espaços e o hífen do formato.

    "abcd-2345", "ABCD 2345" e "abcd2345" são o mesmo código. Sem isto, metade
    dos resgates falharia por causa da formatação que nós mesmos mostramos.
    """
    return "".join((bruto or "").upper().split()).replace("-", "")


def convite_ativo(aluno_id: int) -> "ConviteAluno | None":
    """Convite emitido e ainda não usado deste aluno, se houver."""
    return db.session.scalar(
        db.select(ConviteAluno)
        .filter_by(aluno_id=aluno_id, usado_por_user_id=None)
        .order_by(ConviteAluno.created_at.desc())
    )


def emitir(aluno: "Aluno", criado_por_id: int) -> "ConviteAluno":
    """Convite novo para o aluno. Reaproveita o que já existir sem uso.

    Reaproveitar evita uma pilha de códigos válidos para a mesma pessoa: cada
    um deles seria uma porta aberta a mais, e revogar viraria trabalho manual.
    """
    existente = convite_ativo(aluno.id)
    if existente is not None:
        return existente

    convite = ConviteAluno(
        aluno_id=aluno.id, codigo=gerar_codigo(), created_by=criado_por_id
    )
    db.session.add(convite)
    return convite


def revogar(convite: "ConviteAluno") -> bool:
    """Apaga um convite ainda NÃO usado. Devolve False se já foi resgatado.

    Convite usado não some: é o registro de como aquela conta entrou.
    """
    if convite.usado:
        return False
    db.session.delete(convite)
    return True


class ErroConvite(Exception):
    """Código inválido, já usado, ou conta que já resgatou outro."""


def resgatar(codigo_bruto: str, user: "User") -> "Aluno":
    """Resgata o código para `user` e devolve o aluno vinculado. Não comita.

    Levanta `ErroConvite` com mensagem pronta para a tela. Faz tudo de uma vez
    — marca o convite, liga o aluno à conta e libera o acesso — porque um
    estado intermediário aqui é conta trancada com convite queimado.
    """
    if user.convite_ok:
        raise ErroConvite("Sua conta já está liberada.")

    codigo = normalizar_codigo(codigo_bruto)
    if not codigo:
        raise ErroConvite("Digite o código que o admin te enviou.")

    convite = db.session.scalar(db.select(ConviteAluno).filter_by(codigo=codigo))
    if convite is None:
        raise ErroConvite("Código não encontrado. Confira as letras e tente de novo.")
    if convite.usado:
        raise ErroConvite("Esse código já foi usado. Peça um novo ao admin.")

    aluno = db.session.get(Aluno, convite.aluno_id)
    if aluno is None:
        raise ErroConvite("O aluno desse convite não existe mais. Peça um novo ao admin.")
    if aluno.user_id is not None and aluno.user_id != user.id:
        raise ErroConvite("Esse aluno já está vinculado a outra conta. Fale com o admin.")

    convite.usado_por_user_id = user.id
    convite.usado_em = utcnow()

    aluno.user_id = user.id
    # A marca que faz o `revincular()` respeitar este vínculo.
    aluno.vinculo_por_codigo = True
    # Sem nome_oficial declarado, herda o do aluno: é ele que aparece nos
    # listões, e o resgate acabou de afirmar que essa pessoa é essa conta.
    if not user.nome_oficial:
        user.nome_oficial = aluno.nome
    user.convite_ok = True
    return aluno


def desvincular(aluno: "Aluno") -> None:
    """Desfaz o vínculo conta ↔ aluno (correção de erro do admin). Não comita.

    Some também a marca de autoridade: a partir daqui o casamento por nome
    volta a poder agir sobre este aluno. A conta em si continua liberada — ela
    resgatou um código de verdade, e trancá-la de novo puniria a pessoa por um
    erro de cadastro do admin.
    """
    aluno.user_id = None
    aluno.vinculo_por_codigo = False


def alunos_sem_conta() -> list["Aluno"]:
    """Quem ainda falta convidar — a lista de trabalho do admin."""
    return db.session.scalars(
        db.select(Aluno).filter(Aluno.user_id.is_(None)).order_by(Aluno.nome)
    ).all()


def contas_sem_aluno() -> list["User"]:
    """Contas que não estão ligadas a aluno nenhum.

    Logo depois do deploy são as 7 contas que já existiam, liberadas pela
    migration mas nunca casadas com um aluno — é o que o admin vai querer
    acertar na mão.
    """
    vinculados = db.session.scalars(
        db.select(Aluno.user_id).filter(Aluno.user_id.isnot(None))
    ).all()
    query = db.select(User).order_by(User.username)
    if vinculados:
        query = query.filter(User.id.notin_(vinculados))
    return db.session.scalars(query).all()
