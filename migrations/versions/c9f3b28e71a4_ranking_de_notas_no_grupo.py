"""placar de notas opcional no grupo

Uma coluna booleana em `grupos`. O default é FALSE de propósito: comparar nota
é mais exposto do que comparar volume de questões, e grupo que já existe não
pode passar a mostrar placar sem o dono ligar.

O server_default entra junto porque a tabela pode ter linhas: sem ele, o NOT
NULL falharia nos grupos já criados. Ele sai no fim — a partir daí quem define
o valor é o default do modelo, do lado do Python.

Revision ID: c9f3b28e71a4
Revises: f6a2c9d4b715
Create Date: 2026-08-11 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c9f3b28e71a4'
down_revision = 'f6a2c9d4b715'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("grupos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mostrar_ranking",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("grupos", schema=None) as batch_op:
        batch_op.alter_column(
            "mostrar_ranking", existing_type=sa.Boolean(), server_default=None
        )


def downgrade():
    with op.batch_alter_table("grupos", schema=None) as batch_op:
        batch_op.drop_column("mostrar_ranking")
