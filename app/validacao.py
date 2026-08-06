"""Validação compartilhada entre import e edição manual (B.2 do plano de fase B).

Até aqui, cada importador (`oficiais_import.py`, `simulado_turma_import.py`)
reimplementava sozinho as mesmas checagens de valor (nota fora da escala,
acertos acima do total, status desconhecido...). A edição manual do admin
(rotas em `app/oficiais/routes.py` e `app/simulados/routes.py`) precisa das
MESMAS regras — é o requisito de aceite B.5: recusar com a mesma mensagem que
o import daria para o mesmo erro. Daqui pra frente as duas pontas chamam as
funções daqui, em vez de cada uma ter sua cópia da regra.

Nada aqui toca o banco.
"""

from .models import normalizar_nome

_ALIAS_TURMA = {
    "NOVATA": "novata", "NOVATAS": "novata", "NOVATO": "novata", "NOVATOS": "novata",
    "VETERANA": "veterana", "VETERANAS": "veterana",
    "VETERANO": "veterana", "VETERANOS": "veterana",
}


class ErroImport(Exception):
    """Erro de validação, com mensagem já pronta para mostrar ao admin.

    O nome ficou de import (histórico), mas hoje também é levantada pelas
    rotas de edição manual — é o mesmo tipo de erro: "um valor não bate com a
    régua esperada", só que descoberto num formulário em vez de um JSON."""


def _texto(valor, campo, maximo, obrigatorio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ErroImport(f'O campo "{campo}" é obrigatório.')
        return None
    texto = str(valor).strip()
    if len(texto) > maximo:
        raise ErroImport(f'O campo "{campo}" passa de {maximo} caracteres.')
    return texto


def validar_status(bruto, permitidos, onde, nome, com_underscore=False):
    """Normaliza e confere o status contra o conjunto válido (STATUS do modelo).

    `com_underscore` cobre o caso de ResultadoLinha, cujo STATUS usa "_"
    ("sem_aproveitamento") — o JSON/formulário pode vir com espaço."""
    status = normalizar_nome(bruto).lower()
    if com_underscore:
        status = status.replace(" ", "_")
    if status not in permitidos:
        raise ErroImport(
            f"{onde} ({nome}): status inválido {bruto!r}. "
            f"Use um de: {', '.join(permitidos)}."
        )
    return status


def validar_classificacao(classificacao, onde, nome):
    """Regra de ResultadoLinha: status "classificado" exige posição >= 1."""
    if classificacao is None:
        raise ErroImport(f"{onde} ({nome}): classificado precisa de 'classificacao'.")
    if isinstance(classificacao, bool) or not isinstance(classificacao, int):
        raise ErroImport(f"{onde} ({nome}): 'classificacao' precisa ser inteiro.")
    if classificacao < 1:
        raise ErroImport(f"{onde} ({nome}): 'classificacao' precisa ser >= 1.")


def validar_nota(nota, escala, materia, onde, nome):
    """Nota de uma matéria dentro de 0..escala (ResultadoLinha)."""
    if nota < 0 or nota > escala:
        raise ErroImport(
            f"{onde} ({nome}): nota de {materia.value} = {nota} fora da escala 0–{escala:g}. "
            "Confira a extração."
        )


def validar_acertos(certas, total, materia, onde, nome):
    """Acertos de uma matéria dentro de 0..total de questões (SimuladoTurmaLinha)."""
    if certas < 0 or certas > total:
        raise ErroImport(
            f"{onde} ({nome}): {certas} acertos em {materia.value}, mas a prova "
            f"tem {total} questões. Confira a extração."
        )


def validar_geral_oficial(geral, soma, onde, nome):
    """Coerência entre a coluna GERAL e a soma dos acertos, tolerância 0.01."""
    if geral is not None and abs(geral - soma) > 0.01:
        raise ErroImport(
            f"{onde} ({nome}): a coluna GERAL diz {geral:g}, mas a soma dos acertos "
            f"dá {soma}. Alguma célula foi lida errado."
        )


def validar_classificacao_unica(linhas, classificacao, nome, turma, linha_id=None):
    """A classificação é NACIONAL (vale para todas as turmas do mesmo concurso).

    `linhas` é o conjunto inteiro do ResultadoOficial; `linha_id` exclui a
    própria linha (edição manual não pode colidir consigo mesma)."""
    conflito = next(
        (
            ln
            for ln in linhas
            if ln.status == "classificado"
            and ln.classificacao == classificacao
            and ln.id != linha_id
        ),
        None,
    )
    if conflito is not None:
        raise ErroImport(
            f"Classificação {classificacao} está com {nome} ({turma}) e com "
            f"{conflito.nome} ({conflito.turma}) ao mesmo tempo. A classificação "
            "é nacional: confira a extração."
        )


def validar_nome_unico(linhas, nome, nome_norm, turma, linha_id=None):
    """Duas pessoas com o mesmo nome na mesma prova (mesmo concurso/turma da prova)."""
    conflito = next(
        (ln for ln in linhas if ln.nome_norm == nome_norm and ln.id != linha_id),
        None,
    )
    if conflito is not None:
        raise ErroImport(
            f'{nome} aparece na turma {turma} e também na turma {conflito.turma} '
            "já cadastrada nesta prova. Ou a pessoa está duplicada, ou a turma de "
            "uma das linhas está errada."
        )
