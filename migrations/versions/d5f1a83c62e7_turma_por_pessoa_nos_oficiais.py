"""turma por pessoa nos resultados oficiais

A classificação de um concurso é nacional: existe UMA lista, e turma é só um
recorte do colégio. Esta migration desfaz a modelagem antiga (um header por
turma) fundindo os headers do mesmo concurso e carimbando a turma em cada linha.

A fusão é feita em SQL puro, sem importar os modelos ORM: uma migration precisa
continuar rodando igual daqui a um ano, mesmo depois de o modelo ter mudado.

O ponto crítico é preservar `resultado_linhas.user_id` — é o vínculo "sou eu" de
cada pessoa. Por isso as linhas são REPONTADAS para o header sobrevivente
(UPDATE do resultado_id), nunca recriadas.

Revision ID: d5f1a83c62e7
Revises: c3e8a71b4f92
Create Date: 2026-08-05 15:00:00.000000

"""
from collections import defaultdict

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5f1a83c62e7'
down_revision = 'c3e8a71b4f92'
branch_labels = None
depends_on = None


# Colunas atuais de resultados_oficiais (usadas no copy_from do batch mode: o
# SQLite recria a tabela, e é assim que trocamos a unique sem DROP CONSTRAINT).
def _tabela_oficiais_antiga():
    return sa.Table(
        "resultados_oficiais",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("concurso_nome", sa.String(length=80), nullable=False),
        sa.Column("turma", sa.String(length=20), nullable=False),
        sa.Column("fonte", sa.String(length=40), nullable=True),
        sa.Column("data", sa.Date(), nullable=True),
        sa.Column("escala", sa.Float(), nullable=False),
        sa.Column("materias_csv", sa.String(length=200), nullable=False),
        sa.Column("metrica", sa.String(length=20), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # A unique antiga (concurso_nome, turma) é omitida de propósito: o batch
        # recria a tabela a partir daqui, então não declará-la já a remove.
    )


def _fundir_headers(conn):
    """Junta os headers do mesmo concurso, elegendo o de menor id."""
    headers = conn.execute(
        sa.text(
            "SELECT id, concurso_nome, escala, materias_csv, metrica, fonte, data "
            "FROM resultados_oficiais ORDER BY id"
        )
    ).mappings().all()

    por_concurso = defaultdict(list)
    for header in headers:
        por_concurso[header["concurso_nome"]].append(header)

    for concurso, grupo in por_concurso.items():
        if len(grupo) < 2:
            continue
        sobrevivente = grupo[0]  # menor id (a query já vem ordenada)

        # Campos que mudam o significado dos números não podem divergir: se
        # divergirem, é decisão do usuário qual está certo, não da migration.
        for campo in ("materias_csv", "escala", "metrica"):
            valores = {h[campo] for h in grupo}
            if len(valores) > 1:
                raise RuntimeError(
                    f'Não dá para fundir "{concurso}": o campo "{campo}" diverge '
                    f"entre as turmas ({sorted(map(str, valores))}). Reimporte as "
                    "duas turmas com o mesmo cabeçalho antes de rodar esta migration."
                )

        absorvidos = [h["id"] for h in grupo[1:]]
        # Repontar (e não recriar) preserva user_id, que é o objetivo da fusão.
        conn.execute(
            sa.text(
                "UPDATE resultado_linhas SET resultado_id = :vivo "
                "WHERE resultado_id IN :absorvidos"
            ).bindparams(sa.bindparam("absorvidos", expanding=True)),
            {"vivo": sobrevivente["id"], "absorvidos": absorvidos},
        )
        conn.execute(
            sa.text(
                "DELETE FROM resultados_oficiais WHERE id IN :absorvidos"
            ).bindparams(sa.bindparam("absorvidos", expanding=True)),
            {"absorvidos": absorvidos},
        )
        print(
            f"  [oficiais] {concurso}: {len(grupo)} registros fundidos em "
            f"#{sobrevivente['id']} ({len(absorvidos)} absorvido(s))"
        )


def _conferir_classificacao_unica(conn):
    """Duas pessoas na mesma posição nacional é erro de extração — pare agora."""
    duplicadas = conn.execute(
        sa.text(
            "SELECT r.concurso_nome, l.classificacao, COUNT(*) AS n "
            "FROM resultado_linhas l "
            "JOIN resultados_oficiais r ON r.id = l.resultado_id "
            "WHERE l.status = 'classificado' AND l.classificacao IS NOT NULL "
            "GROUP BY l.resultado_id, l.classificacao HAVING n > 1"
        )
    ).mappings().all()
    if duplicadas:
        detalhes = "; ".join(
            f'{d["concurso_nome"]}: classificação {d["classificacao"]} aparece {d["n"]}x'
            for d in duplicadas
        )
        raise RuntimeError(
            "Depois de juntar as turmas sobraram classificações repetidas dentro "
            f"do mesmo concurso ({detalhes}). A classificação é nacional, então "
            "isso é erro de extração: corrija o listão e reimporte."
        )


def upgrade():
    conn = op.get_bind()

    # 1. turma nas linhas, nullable primeiro (as linhas existentes ainda não têm).
    with op.batch_alter_table("resultado_linhas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("turma", sa.String(length=20), nullable=True))

    # 2. Migração de dados: turma desce do header para as linhas, e os headers do
    #    mesmo concurso viram um só.
    conn.execute(
        sa.text(
            "UPDATE resultado_linhas SET turma = ("
            "  SELECT r.turma FROM resultados_oficiais r WHERE r.id = resultado_id"
            ")"
        )
    )
    _fundir_headers(conn)
    _conferir_classificacao_unica(conn)

    # Linha órfã (header já apagado) não deveria existir, mas se existir o
    # NOT NULL abaixo quebraria sem explicação. Melhor falhar com nome.
    orfas = conn.execute(
        sa.text("SELECT COUNT(*) FROM resultado_linhas WHERE turma IS NULL")
    ).scalar()
    if orfas:
        raise RuntimeError(
            f"{orfas} linha(s) de resultado oficial sem turma (provavelmente órfãs "
            "de um header apagado). Limpe-as antes de rodar esta migration."
        )

    # 3. Agora sim, turma obrigatória.
    with op.batch_alter_table("resultado_linhas", schema=None) as batch_op:
        batch_op.alter_column("turma", existing_type=sa.String(length=20), nullable=False)
        batch_op.create_index(
            batch_op.f("ix_resultado_linhas_turma"), ["turma"], unique=False
        )

    # 4. Header perde a turma e passa a ser único por concurso.
    with op.batch_alter_table(
        "resultados_oficiais", copy_from=_tabela_oficiais_antiga(), schema=None
    ) as batch_op:
        batch_op.drop_column("turma")
        batch_op.create_unique_constraint(
            "uq_resultados_oficiais_concurso_nome", ["concurso_nome"]
        )


def downgrade():
    """ATENÇÃO: não desfaz a fusão.

    Dois headers viraram um e não há como saber onde recortar de volta sem
    inventar dado. O downgrade devolve o SCHEMA antigo (coluna turma no header,
    preenchida com a turma majoritária das linhas), mas o concurso continua com
    um registro só. Recuperar a separação exige reimportar os JSONs."""
    conn = op.get_bind()

    with op.batch_alter_table("resultados_oficiais", schema=None) as batch_op:
        batch_op.add_column(sa.Column("turma", sa.String(length=20), nullable=True))

    conn.execute(
        sa.text(
            "UPDATE resultados_oficiais SET turma = COALESCE(("
            "  SELECT l.turma FROM resultado_linhas l WHERE l.resultado_id = id "
            "  GROUP BY l.turma ORDER BY COUNT(*) DESC LIMIT 1"
            "), 'novata')"
        )
    )

    with op.batch_alter_table("resultados_oficiais", schema=None) as batch_op:
        batch_op.alter_column("turma", existing_type=sa.String(length=20), nullable=False)
        batch_op.drop_constraint("uq_resultados_oficiais_concurso_nome", type_="unique")
        batch_op.create_unique_constraint(
            "uq_resultados_oficiais_concurso_nome_turma", ["concurso_nome", "turma"]
        )

    with op.batch_alter_table("resultado_linhas", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_resultado_linhas_turma"))
        batch_op.drop_column("turma")
