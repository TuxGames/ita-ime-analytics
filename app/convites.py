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


class ErroConvite(Exception):
    """Código inválido, já usado, ou conta que já resgatou outro."""


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


def emitir_coringa(rotulo: str, criado_por_id: int) -> "ConviteAluno":
    """Convite que LIBERA a conta sem vincular a aluno nenhum.

    Para quem não é aluno: coordenador, professor, conta de teste. Uso único
    como os demais — para convidar duas pessoas, geram-se dois. Não reaproveita
    coringa pendente (ao contrário do convite de aluno): cada coringa é para uma
    pessoa diferente, e o rótulo é justamente o que os distingue.
    """
    rotulo = (rotulo or "").strip()
    if not rotulo:
        raise ErroConvite("Diga para que serve o coringa (ex.: coordenador).")

    convite = ConviteAluno(
        tipo="coringa",
        aluno_id=None,
        rotulo=rotulo[:60],
        codigo=gerar_codigo(),
        created_by=criado_por_id,
    )
    db.session.add(convite)
    return convite


def coringas() -> list["ConviteAluno"]:
    """Todos os coringas, pendentes e usados, do mais novo para o mais velho."""
    return db.session.scalars(
        db.select(ConviteAluno)
        .filter(ConviteAluno.tipo == "coringa")
        .order_by(ConviteAluno.created_at.desc())
    ).all()


def convite_coringa_do_usuario(user_id: int) -> "ConviteAluno | None":
    """O coringa que esta conta resgatou, se foi por aí que ela entrou."""
    return db.session.scalar(
        db.select(ConviteAluno).filter(
            ConviteAluno.tipo == "coringa",
            ConviteAluno.usado_por_user_id == user_id,
        )
    )


def convite_ativo(aluno_id: int) -> "ConviteAluno | None":
    """Convite emitido e ainda não usado deste aluno, se houver."""
    return db.session.scalar(
        db.select(ConviteAluno)
        .filter_by(aluno_id=aluno_id, usado_por_user_id=None, tipo="aluno")
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
        tipo="aluno",
        aluno_id=aluno.id,
        codigo=gerar_codigo(),
        created_by=criado_por_id,
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


def resgatar(codigo_bruto: str, user: "User") -> "Aluno | None":
    """Resgata o código para `user`. Não comita.

    Devolve o aluno vinculado, ou None quando o código é coringa — coringa
    libera a conta sem amarrá-la a aluno nenhum.

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

    convite.usado_por_user_id = user.id
    convite.usado_em = utcnow()

    if convite.eh_coringa:
        # Libera e pronto: coringa é justamente para quem NÃO é aluno. Sem
        # vínculo, sem nome_oficial herdado — a pessoa não aparece em listão.
        user.convite_ok = True
        return None

    aluno = db.session.get(Aluno, convite.aluno_id)
    if aluno is None:
        raise ErroConvite("O aluno desse convite não existe mais. Peça um novo ao admin.")
    if aluno.user_id is not None and aluno.user_id != user.id:
        raise ErroConvite("Esse aluno já está vinculado a outra conta. Fale com o admin.")

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


def contas_sem_aluno() -> list[dict]:
    """Contas não ligadas a aluno nenhum, dizendo QUAIS são coringa.

    A lista serve para o admin ver o que falta acertar — mas conta que entrou
    por coringa não é pendência, é o estado final correto. Por isso cada item
    vem com o convite coringa (ou None), e a tela separa as duas coisas.

    Logo depois do deploy, as contas que já existiam aparecem aqui sem coringa:
    são elas que o admin vai querer casar com um aluno.
    """
    vinculados = db.session.scalars(
        db.select(Aluno.user_id).filter(Aluno.user_id.isnot(None))
    ).all()
    query = db.select(User).order_by(User.username)
    if vinculados:
        query = query.filter(User.id.notin_(vinculados))

    return [
        {"user": u, "coringa": convite_coringa_do_usuario(u.id)}
        for u in db.session.scalars(query)
    ]
