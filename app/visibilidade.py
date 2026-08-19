"""Quem pode ver qual fase de simulado. UM ponto de decisão, não quinze `if`.

Estado atual: a **2ª fase (discursiva) é só do admin.** Ele importa, olha,
confere e corrige; para todo o resto do mundo — aluno, professor, coordenação,
conta coringa — a prova discursiva **não existe**. Não é link escondido: a rota
devolve 404, a listagem não a traz, a evolução a ignora e nenhum número
derivado dela sai em lugar nenhum.

POR QUE
    As fórmulas do IME não fecham. Cinco famílias de hipótese morreram contra
    as 12 linhas do S6 em que temos as duas fases. Enquanto a coordenação não
    confirmar como o colégio calcula nota e média com 2ª fase, nenhum aluno vê
    um número que ninguém consegue auditar — e número que ninguém audita é pior
    que número nenhum.

POR QUE CONSTANTE NO CÓDIGO, E NÃO COLUNA NO BANCO
    Não é configuração por prova: é um estado do RECURSO INTEIRO. Uma flag por
    linha convidaria a liberar uma prova e esquecer a outra, e ainda daria a
    impressão de que isto é uma escolha editorial. É um bloqueio temporário com
    uma condição de saída clara — e apagar quatro linhas de código é mais
    honesto (e mais fácil de revisar) do que caçar uma flag no banco.

COMO REMOVER, QUANDO A COORDENAÇÃO CONFIRMAR
    Esvazie `FASES_RESERVADAS`. Os testes de
    `tests/test_2fase_so_admin.py` vão falhar em bloco — é o esperado, e é a
    lista exata do que volta a ficar visível. Confira um por um e apague o
    arquivo.

COMO USAR
    - Em consulta: `so_provas_visiveis(db.select(...))` acrescenta o filtro.
    - Em rota: `abort_se_reservada(prova)` devolve 404 para quem não é admin.
    - Ao percorrer relacionamento (`aluno.linhas`, `turma.linhas`), onde não há
      query para filtrar: `linhas_visiveis(linhas)`.
"""

from flask import has_request_context
from flask_login import current_user

from .models import SimuladoTurma, SimuladoTurmaLinha

# Fases que só o admin enxerga. Vazio = tudo visível para todo mundo.
FASES_RESERVADAS = frozenset({"discursiva"})


def _e_admin(user=None) -> bool:
    """Admin de verdade. Fora de requisição (CLI, script), o padrão é NÃO.

    O default fechado é de propósito: um caminho novo que esqueça de passar o
    usuário esconde a mais, não de menos. Quem precisa ver tudo fora da web
    (a conferência do admin, por exemplo) diz isso explicitamente.
    """
    if user is None:
        if not has_request_context():
            return False
        user = current_user
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_admin", False))


def pode_ver_fase(fase: str | None, user=None) -> bool:
    """Esta fase existe para este usuário?"""
    if fase not in FASES_RESERVADAS:
        return True
    return _e_admin(user)


def pode_ver_prova(prova: "SimuladoTurma | None", user=None) -> bool:
    return prova is not None and pode_ver_fase(prova.fase, user)


def so_provas_visiveis(query, user=None, tudo=False):
    """Acrescenta o filtro de fase a uma query sobre SimuladoTurma.

    `tudo=True` é o escape explícito para uso fora da web (CLI de conferência),
    onde não há usuário logado mas quem roda é o dono do banco.
    """
    if tudo or _e_admin(user) or not FASES_RESERVADAS:
        return query
    return query.filter(SimuladoTurma.fase.notin_(FASES_RESERVADAS))


def so_linhas_visiveis(query, user=None, tudo=False):
    """Idem, para query sobre SimuladoTurmaLinha. Faz o JOIN se preciso.

    Usa subquery em vez de join para não interferir com joins que quem chamou
    já tenha montado — e para não duplicar linha por engano.
    """
    if tudo or _e_admin(user) or not FASES_RESERVADAS:
        return query
    reservadas = (
        SimuladoTurma.__table__.select()
        .with_only_columns(SimuladoTurma.id)
        .where(SimuladoTurma.fase.in_(FASES_RESERVADAS))
    )
    return query.filter(SimuladoTurmaLinha.turma_id.notin_(reservadas))


def linhas_visiveis(linhas, user=None) -> list:
    """Filtra uma lista já carregada (relacionamento), onde não há query.

    `aluno.linhas` e `turma.linhas` são relacionamentos do ORM: o filtro tem
    que acontecer em Python, senão a prova reservada atravessa por dentro.
    """
    if _e_admin(user) or not FASES_RESERVADAS:
        return list(linhas)
    return [ln for ln in linhas if ln.turma_obj.fase not in FASES_RESERVADAS]
