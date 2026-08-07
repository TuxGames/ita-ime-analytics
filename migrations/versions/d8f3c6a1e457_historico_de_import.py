"""histórico de import (F.3)

Uma linha por import APLICADO (oficial ou de simulado), com o JSON cru
submetido — para auditoria/depuração manual. Sem rollback automático a partir
daqui: é só o registro do que aconteceu.

Revision ID: d8f3c6a1e457
Revises: c7a5e2f18b9d
Create Date: 2026-08-06 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8f3c6a1e457'
down_revision = 'c7a5e2f18b9d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "historico_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("alvo", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("historico_imports")
