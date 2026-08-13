"""codigo de convite por aluno, e trava de acesso na conta

O cadastro e aberto: qualquer pessoa criava conta e via nome completo, serie,
turma e nota de 73 alunos. Agora conta nova nasce trancada e so e liberada
resgatando um codigo emitido pelo admin para UM aluno -- o resgate ja cria o
vinculo conta <-> aluno.

CRITICO: `users.convite_ok` entra com server_default TRUE, e so DEPOIS o
default vira FALSE. As contas que ja existem sao marcadas como liberadas; sem
isso o deploy trancaria todo mundo numa tela pedindo um codigo que ninguem
tem. Conta criada a partir daqui nasce com FALSE (default do modelo, do lado
do Python).

`alunos.vinculo_por_codigo` marca o vinculo autoritativo: `vinculo.revincular()`
refaz vinculos por nome depois de cada import e nao pode desfazer o que o
codigo estabeleceu.

Revision ID: e7c2a95d13f8
Revises: d4b8c1f70e23
Create Date: 2026-08-13 18:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e7c2a95d13f8'
down_revision = 'd4b8c1f70e23'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Trava na conta. Entra como TRUE para nao trancar quem ja existe.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "convite_ok", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )

    liberadas = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE convite_ok = 1")
    ).scalar()
    print(f"  [convites] {liberadas} conta(s) existente(s) marcada(s) como liberada(s).")

    # O server_default sai aqui: dele em diante quem manda e o default do
    # modelo (False), entao conta NOVA nasce trancada.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "convite_ok", existing_type=sa.Boolean(), server_default=None
        )

    # 2. Marca de vinculo autoritativo. Ninguem tem ainda: default FALSE.
    with op.batch_alter_table("alunos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "vinculo_por_codigo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("alunos", schema=None) as batch_op:
        batch_op.alter_column(
            "vinculo_por_codigo", existing_type=sa.Boolean(), server_default=None
        )

    # 3. Tabela dos convites.
    op.create_table(
        "convites_aluno",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aluno_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("usado_por_user_id", sa.Integer(), nullable=True),
        sa.Column("usado_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["aluno_id"], ["alunos.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["usado_por_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("convites_aluno", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_convites_aluno_aluno_id"), ["aluno_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_convites_aluno_codigo"), ["codigo"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_convites_aluno_usado_por_user_id"),
            ["usado_por_user_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("convites_aluno", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_convites_aluno_usado_por_user_id"))
        batch_op.drop_index(batch_op.f("ix_convites_aluno_codigo"))
        batch_op.drop_index(batch_op.f("ix_convites_aluno_aluno_id"))
    op.drop_table("convites_aluno")

    with op.batch_alter_table("alunos", schema=None) as batch_op:
        batch_op.drop_column("vinculo_por_codigo")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("convite_ok")
