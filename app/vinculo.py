"""Ligação entre a pessoa das listas e a conta de cada usuário.

Antes o casamento era nome-da-linha ↔ nome_oficial, linha por linha. Agora passa
pelo Aluno: `User.nome_oficial` decide `Aluno.user_id`, e as linhas herdam do
aluno. A vantagem prática é que apelido criado num merge passa a valer para o
vínculo também — quem se reconheceu numa grafia continua reconhecido na outra.

`linha.user_id` continua preenchido porque é o que as telas já consultam; só
mudou quem decide o valor.
"""

from .alunos import TABELAS_DE_LINHA, encontrar_aluno
from .extensions import db
from .models import Aluno, User, normalizar_nome


def revincular() -> int:
    """Refaz Aluno.user_id e propaga para as linhas. Devolve quantos registros
    mudaram.

    Roda inteiro (e não só o que acabou de entrar) porque as tabelas são pequenas
    e assim import novo, troca de nome no perfil e "sou eu" convergem para o
    mesmo estado, sem caminho especial para cada caso."""
    usuarios = db.session.scalars(
        db.select(User).filter(User.nome_oficial.isnot(None))
    ).all()

    desejado = {}
    for user in usuarios:
        aluno = encontrar_aluno(user.nome_oficial)
        if aluno is not None:
            desejado[aluno.id] = user.id

    alterados = 0
    por_aluno = {}
    for aluno in db.session.scalars(db.select(Aluno)):
        novo = desejado.get(aluno.id)
        if aluno.user_id != novo:
            aluno.user_id = novo
            alterados += 1
        por_aluno[aluno.id] = novo

    for modelo in TABELAS_DE_LINHA:
        for linha in db.session.scalars(db.select(modelo)):
            novo = por_aluno.get(linha.aluno_id) if linha.aluno_id else None
            if linha.user_id != novo:
                linha.user_id = novo
                alterados += 1
    return alterados


def nome_ja_usado(nome_norm: str, exceto_user_id: int) -> bool:
    """True se outra conta já reivindicou esse nome."""
    outros = db.session.scalars(
        db.select(User).filter(
            User.id != exceto_user_id, User.nome_oficial.isnot(None)
        )
    ).all()
    return any(normalizar_nome(u.nome_oficial) == nome_norm for u in outros)
