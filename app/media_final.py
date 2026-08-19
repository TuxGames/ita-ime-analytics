"""Média final das duas fases: COPIADA quando a planilha traz, calculada só em
último caso — e sempre dizendo qual das duas é.

A ordem importa e não é preferência de estilo:

1. **Veio `MÉDIA FINAL` na planilha?** É esse número. Fim. Este é o caso comum:
   a planilha de dois blocos do ITA S5 já traz a coluna, em azul, na ponta
   direita. Não há nada a combinar.
2. **Não veio, é ITA, e as duas fases estão importadas?** Aí sim
   `0,8 × discursivo + 0,2 × objetiva`, marcado na tela como CALCULADO.
3. **IME? Nunca.** Cinco famílias de hipótese morreram contra as 12 linhas do
   S6 em que temos as duas fases — inclusive uma que exigia peso negativo para
   exatas, e o fato de a média publicada de uma pessoa (5,10) ser maior que o
   discursivo calculado (4,84) E que a objetiva (4,50), o que impede qualquer
   combinação convexa das duas.

Por que copiar ganha de calcular mesmo quando a fórmula fecha: o colégio pode
mudar o peso sem avisar ninguém. No dia em que mudar, o número copiado continua
certo e o calculado passa a mentir — em silêncio, porque continua parecendo um
número plausível.

As fases se emparelham por `(banca, rotulo)`. NÃO por data: as duas fases do
IME S6 são de 04/07 e 11/07, e `data_secundaria` é resto de template (o título
da 2ª fase traz 14/04, que não é a data de fase nenhuma).
"""

from .extensions import db
from .models import SimuladoTurma, SimuladoTurmaLinha
from .visibilidade import pode_ver_prova

# Pesos do bloco discursivo do ITA, observados no S5 e conferidos linha a linha.
# Só usados no caso 2, quando a planilha não trouxe a coluna pronta.
PESOS_DISCURSIVO_ITA = {
    "MATEMATICA": 2, "QUIMICA": 2, "FISICA": 2, "PORTUGUES": 1, "REDACAO": 1,
}
PESO_DISCURSIVO, PESO_OBJETIVA = 0.8, 0.2

# Bancas cuja combinação das fases é conhecida. O IME está fora de propósito.
BANCAS_COM_FORMULA = {"ITA"}


def _media_do_discursivo(prova: "SimuladoTurma", linha) -> float | None:
    """Nota do bloco discursivo: a copiada, se houver; senão a fórmula do ITA.

    Ausente vale ZERO, não "não conta" — é o que a planilha real mostra: quem
    faltou a uma fase ainda recebeu média final (0,00 e 3,61 → 0,72)."""
    if linha.status == "ausente":
        return 0.0
    if linha.media_informada is not None:
        return linha.media_informada
    if {m.name for m in prova.materias} != set(PESOS_DISCURSIVO_ITA):
        return None
    soma = sum(
        PESOS_DISCURSIVO_ITA[nome] * nota for nome, nota in linha.notas.items()
    )
    return soma / sum(PESOS_DISCURSIVO_ITA.values())


def _media_da_objetiva(prova: "SimuladoTurma", linha) -> float | None:
    """Nota da 1ª fase: a copiada, se houver; senão a proporcional de sempre."""
    if linha.status == "ausente":
        return 0.0
    if linha.media_oficial is not None:
        return linha.media_oficial
    return prova.nota_de(linha, prova.materias_media or prova.materias)


def _fase_irma(prova: "SimuladoTurma", fase: str) -> "SimuladoTurma | None":
    return db.session.scalar(
        db.select(SimuladoTurma).filter_by(
            banca=prova.banca, rotulo=prova.rotulo, fase=fase
        )
    )


def media_final_da_linha(linha: "SimuladoTurmaLinha", user=None) -> tuple[float, str] | None:
    """`(valor, origem)` com origem `"copiada"` ou `"calculada"`, ou None.

    A origem não é enfeite: a tela precisa dizer qual é qual, senão um número
    calculado com fórmula observada passa por número oficial do colégio.
    """
    prova = linha.turma_obj
    # A média final vive na linha da 2ª fase. Se essa fase não existe para quem
    # está olhando, o número dela também não — um valor que a pessoa não
    # consegue auditar contra nenhuma tela é pior que valor nenhum.
    if not pode_ver_prova(prova, user):
        return None

    if linha.media_final_informada is not None:
        return (linha.media_final_informada, "copiada")

    if prova.fase != "discursiva" or prova.banca.strip().upper() not in BANCAS_COM_FORMULA:
        return None

    objetiva = _fase_irma(prova, "objetiva")
    if not pode_ver_prova(objetiva, user):
        return None

    # A pessoa precisa existir na outra fase. Não estar na lista é diferente de
    # ter faltado: faltou vale zero, não estar não permite afirmar nada.
    if linha.aluno_id is None:
        return None
    par = next((ln for ln in objetiva.linhas if ln.aluno_id == linha.aluno_id), None)
    if par is None:
        return None

    discursivo = _media_do_discursivo(prova, linha)
    objetivo = _media_da_objetiva(objetiva, par)
    if discursivo is None or objetivo is None:
        return None

    valor = PESO_DISCURSIVO * discursivo + PESO_OBJETIVA * objetivo
    return (round(valor, 2), "calculada")
