"""turma por pessoa no ranking de simulado, e campo fase

Mesma ideia da migration anterior (d5f1a83c62e7), agora para o ranking do
colégio: a prova é uma só, então novatos e veteranos passam a conviver no mesmo
registro e a turma desce para cada linha.

A chave passa a incluir a DATA porque "S5" repete todo ano: sem ela, dois
simulados de anos diferentes com o mesmo rótulo colidiriam.

Também entra `fase`, com "objetiva" para tudo que já existe (todo o dado atual é
1ª fase). O campo existe para a discursiva entrar depois sem outra migration.

Como na Fase 1, o objetivo é preservar `simulado_turma_linhas.user_id`: as linhas
são REPONTADAS, nunca recriadas.

Revision ID: e91b47dc2a05
Revises: d5f1a83c62e7
Create Date: 2026-08-05 16:00:00.000000

"""
from collections import defaultdict
from datetime import date

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e91b47dc2a05'
down_revision = 'd5f1a83c62e7'
branch_labels = None
depends_on = None


def _tabela_simulados_antiga():
    """Schema atual, para o batch recriar a tabela sem a unique antiga."""
    return sa.Table(
        "simulados_turma",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("banca", sa.String(length=40), nullable=False),
        sa.Column("rotulo", sa.String(length=20), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("turma", sa.String(length=20), nullable=False),
        sa.Column("fase", sa.String(length=20), nullable=False),
        sa.Column("fonte", sa.String(length=40), nullable=True),
        sa.Column("materias_csv", sa.String(length=200), nullable=False),
        sa.Column("materias_media_csv", sa.String(length=200), nullable=True),
        sa.Column("questoes_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # A unique antiga (banca, rotulo, turma) é omitida de propósito.
    )


def _fundir_headers(conn):
    headers = conn.execute(
        sa.text(
            "SELECT id, banca, rotulo, data, materias_csv, materias_media_csv, "
            "questoes_json FROM simulados_turma ORDER BY id"
        )
    ).mappings().all()

    por_prova = defaultdict(list)
    for header in headers:
        por_prova[(header["banca"], header["rotulo"], header["data"])].append(header)

    for (banca, rotulo, data), grupo in por_prova.items():
        if len(grupo) < 2:
            continue
        sobrevivente = grupo[0]

        for campo in ("materias_csv", "materias_media_csv", "questoes_json"):
            valores = {h[campo] for h in grupo}
            if len(valores) > 1:
                raise RuntimeError(
                    f'Não dá para fundir "{banca} {rotulo}" ({data}): o campo '
                    f'"{campo}" diverge entre as turmas ({sorted(map(str, valores))}). '
                    "Reimporte as duas turmas com o mesmo cabeçalho antes de rodar "
                    "esta migration."
                )

        absorvidos = [h["id"] for h in grupo[1:]]
        conn.execute(
            sa.text(
                "UPDATE simulado_turma_linhas SET turma_id = :vivo "
                "WHERE turma_id IN :absorvidos"
            ).bindparams(sa.bindparam("absorvidos", expanding=True)),
            {"vivo": sobrevivente["id"], "absorvidos": absorvidos},
        )
        conn.execute(
            sa.text(
                "DELETE FROM simulados_turma WHERE id IN :absorvidos"
            ).bindparams(sa.bindparam("absorvidos", expanding=True)),
            {"absorvidos": absorvidos},
        )
        print(
            f"  [ranking] {banca} {rotulo} ({data}): {len(grupo)} registros fundidos "
            f"em #{sobrevivente['id']}"
        )


def _avisar_datas_proximas(conn):
    """Mesma (banca, rotulo) com datas diferentes NÃO se funde — e está certo.

    Mas se as datas estão a poucos dias e as matérias batem, provavelmente é a
    mesma prova com a data digitada errada numa das turmas. Quem decide é o
    usuário: aqui só avisamos."""
    linhas = conn.execute(
        sa.text(
            "SELECT id, banca, rotulo, data, materias_csv FROM simulados_turma "
            "ORDER BY banca, rotulo, data"
        )
    ).mappings().all()

    por_prova = defaultdict(list)
    for linha in linhas:
        por_prova[(linha["banca"], linha["rotulo"])].append(linha)

    for (banca, rotulo), grupo in por_prova.items():
        if len(grupo) < 2:
            continue
        for anterior, atual in zip(grupo, grupo[1:]):
            if anterior["materias_csv"] != atual["materias_csv"]:
                continue
            try:
                dias = abs(
                    (date.fromisoformat(str(atual["data"])[:10])
                     - date.fromisoformat(str(anterior["data"])[:10])).days
                )
            except (ValueError, TypeError):
                continue
            if 0 < dias <= 7:
                print(
                    f"  [AVISO] {banca} {rotulo} aparece em {anterior['data']} e "
                    f"{atual['data']} ({dias} dia(s) de diferença) com as mesmas "
                    "matérias. Podem ser a MESMA prova com a data errada em uma das "
                    "turmas — confira e, se for o caso, reimporte com a data certa."
                )


def upgrade():
    conn = op.get_bind()

    # 1. fase no header (tudo que existe hoje é 1ª fase).
    with op.batch_alter_table("simulados_turma", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "fase",
                sa.String(length=20),
                nullable=False,
                server_default="objetiva",
            )
        )

    # 2. turma nas linhas, nullable primeiro.
    with op.batch_alter_table("simulado_turma_linhas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("turma", sa.String(length=20), nullable=True))

    conn.execute(
        sa.text(
            "UPDATE simulado_turma_linhas SET turma = ("
            "  SELECT s.turma FROM simulados_turma s WHERE s.id = turma_id"
            ")"
        )
    )

    _avisar_datas_proximas(conn)
    _fundir_headers(conn)

    orfas = conn.execute(
        sa.text("SELECT COUNT(*) FROM simulado_turma_linhas WHERE turma IS NULL")
    ).scalar()
    if orfas:
        raise RuntimeError(
            f"{orfas} linha(s) de ranking sem turma (órfãs de um header apagado). "
            "Limpe-as antes de rodar esta migration."
        )

    with op.batch_alter_table("simulado_turma_linhas", schema=None) as batch_op:
        batch_op.alter_column("turma", existing_type=sa.String(length=20), nullable=False)
        batch_op.create_index(
            batch_op.f("ix_simulado_turma_linhas_turma"), ["turma"], unique=False
        )

    # 3. Header perde a turma; a chave vira (banca, rotulo, data). O server_default
    #    de `fase` sai aqui: ele serviu só para preencher as linhas existentes.
    with op.batch_alter_table(
        "simulados_turma", copy_from=_tabela_simulados_antiga(), schema=None
    ) as batch_op:
        batch_op.drop_column("turma")
        batch_op.alter_column(
            "fase", existing_type=sa.String(length=20), server_default=None
        )
        batch_op.create_unique_constraint(
            "uq_simulados_turma_prova", ["banca", "rotulo", "data"]
        )


def downgrade():
    """ATENÇÃO: não desfaz a fusão (ver d5f1a83c62e7).

    Devolve o schema antigo — turma no header, preenchida com a turma majoritária
    das linhas — mas a prova continua com um registro só. Separar de novo exige
    reimportar os JSONs."""
    conn = op.get_bind()

    with op.batch_alter_table("simulados_turma", schema=None) as batch_op:
        batch_op.add_column(sa.Column("turma", sa.String(length=20), nullable=True))

    conn.execute(
        sa.text(
            "UPDATE simulados_turma SET turma = COALESCE(("
            "  SELECT l.turma FROM simulado_turma_linhas l WHERE l.turma_id = id "
            "  GROUP BY l.turma ORDER BY COUNT(*) DESC LIMIT 1"
            "), 'novata')"
        )
    )

    with op.batch_alter_table("simulados_turma", schema=None) as batch_op:
        batch_op.alter_column("turma", existing_type=sa.String(length=20), nullable=False)
        batch_op.drop_constraint("uq_simulados_turma_prova", type_="unique")
        batch_op.create_unique_constraint(
            "uq_simulados_turma_banca_rotulo_turma", ["banca", "rotulo", "turma"]
        )
        batch_op.drop_column("fase")

    with op.batch_alter_table("simulado_turma_linhas", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_simulado_turma_linhas_turma"))
        batch_op.drop_column("turma")
