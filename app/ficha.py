"""Ficha do aluno para professor e coordenação. SÓ LEITURA, e só nota.

A linha que define este módulo: nota de simulado é dado que o COLÉGIO já
distribui para a turma inteira — a ficha só poupa o professor de garimpar prova
por prova. Estudo, treino e registro de questões NÃO entram: a pessoa digitou
isso aqui achando que era dela, e só compartilha dentro de um grupo, por
escolha. Se vazasse para a ficha, ela pararia de registrar, e o dado morreria
para ela também.

O jeito de errar isto é vazamento por reaproveitamento: pegar um payload pronto
que já carrega estudo junto. Por isso `ficha_do_aluno` monta um dicionário
EXPLÍCITO, campo a campo, em vez de repassar objetos do ORM — de onde qualquer
template poderia navegar para `aluno.user.simulados` e daí para o resto.

O cálculo de evolução é REUSADO de `evolucao.py` (o mesmo que o aluno vê de si
e o admin vê do aluno). Escrever um segundo faria os dois divergirem sem
ninguém saber qual está certo.
"""

from .evolucao import evolucao_do_aluno, linhas_do_aluno_em_ordem
from .extensions import db
from .grouping import compor_titulo
from .models import Aluno, Materia, ResultadoLinha

# Chaves que a ficha PODE conter. Qualquer coisa fora desta lista é vazamento —
# o teste `test_ficha_nao_carrega_dado_privado` reprova o que não estiver aqui.
CAMPOS_PERMITIDOS = {
    "aluno_id", "nome", "turma", "serie", "ativo",
    "simulados", "oficiais", "evolucao", "resumo",
}


# Chaves da LISTA de alunos. Mesma regra da ficha, pelo mesmo motivo.
CAMPOS_DA_LISTA = {"id", "nome", "turma", "serie", "ativo"}


def alunos_para_ficha() -> list[dict]:
    """Todos os alunos, para o professor escolher. Só identificação e turma.

    Dicionário, não `Aluno`: entregar o objeto do ORM daria ao template um
    caminho para `a.user` e de lá para estudo e treino. A lista é o lugar mais
    fácil de esquecer disso, porque ela "só mostra nome".
    """
    return [
        {
            "id": a.id,
            "nome": a.nome,
            "turma": a.turma_curto if a.turma else None,
            "serie": a.serie,
            "ativo": a.ativo,
        }
        for a in db.session.scalars(db.select(Aluno).order_by(Aluno.nome))
    ]


def ficha_do_aluno(aluno: "Aluno", materias=None, user=None) -> dict:
    """Histórico de NOTAS do aluno. Não toca em estudo, treino nem grupo.

    Monta tudo à mão de propósito: nada de devolver o `Aluno` cru, que daria
    ao template um caminho para `aluno.user` e de lá para o resto do app.

    `user` decide quais fases aparecem. O professor NÃO vê a 2ª fase: ele não
    é admin, e o número não está confirmado com a coordenação — ver
    app/visibilidade.py. Como a ficha reusa `linhas_do_aluno_em_ordem` e
    `evolucao_do_aluno`, basta repassar para os três lugares fecharem juntos.
    """
    linhas = linhas_do_aluno_em_ordem(aluno.id, user)

    simulados = []
    for linha in linhas:
        turma = linha.turma_obj
        materias_da_prova = turma.materias_media or turma.materias
        nota = turma.nota_de(linha, materias_da_prova)
        posicao = next(
            (pos for pos, ln, _ in turma.ranking(materias_da_prova) if ln.id == linha.id),
            None,
        )
        simulados.append({
            # Com a fase: as duas fases da mesma prova são duas linhas aqui, e
            # sem ela as duas apareceriam escritas "ITA S5".
            "prova": compor_titulo(turma.banca, turma.rotulo, turma.fase),
            "data": turma.data,
            "fase": turma.fase,
            "turma": linha.turma,
            "serie": linha.serie,
            "nota": nota,
            "posicao": posicao,
            "total": len(turma.presentes()),
            # Acertos por matéria: é o desempenho da PROVA, não hábito de estudo.
            "acertos": {
                Materia[nome].value: {"certas": certas, "total": turma.questoes.get(nome)}
                for nome, certas in (linha.acertos or {}).items()
                if nome in Materia.__members__
            },
        })

    oficiais = [
        {
            "concurso": ln.resultado.concurso_nome,
            "data": ln.resultado.data,
            "status": ln.status_label,
            "classificacao": ln.classificacao,
            "turma": ln.turma_curto,
        }
        for ln in db.session.scalars(
            db.select(ResultadoLinha)
            .filter(ResultadoLinha.aluno_id == aluno.id)
            .order_by(ResultadoLinha.id)
        )
    ]

    notas = [s["nota"] for s in simulados if s["nota"] is not None]
    return {
        "aluno_id": aluno.id,
        "nome": aluno.nome,
        "turma": aluno.turma_curto if aluno.turma else None,
        "serie": aluno.serie,
        "ativo": aluno.ativo,
        "simulados": simulados,
        "oficiais": oficiais,
        # Reuso, não cópia: a mesma conta que o aluno vê de si mesmo.
        "evolucao": evolucao_do_aluno(aluno.id, materias, user),
        "resumo": {
            "provas": len(simulados),
            "media": round(sum(notas) / len(notas), 2) if notas else None,
            "melhor": max(notas) if notas else None,
            "ultima": notas[-1] if notas else None,
            "classificacoes": sum(1 for o in oficiais if o["classificacao"]),
        },
    }
