"""edição manual das linhas

Reimportar uma turma apaga e reinsere todas as linhas dela — uma correção
manual do admin direto no banco desapareceria silenciosamente no próximo
import. Estas colunas marcam "isso foi editado à mão" para o preview de
import avisar antes de sobrescrever (a decisão de confirmar mesmo assim
continua sendo do admin).

SQLite aceita ADD COLUMN simples sem batch mode; batch_alter_table só entra
no downgrade, porque DROP COLUMN esse SQLite não faz direto.

Revision ID: a4c7d2e91b03
Revises: f2a91c48d370
Create Date: 2026-08-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4c7d2e91b03'
down_revision = 'f2a91c48d370'
branch_labels = None
depends_on = None


_TABELAS = ("resultado_linhas", "simulado_turma_linhas")


def upgrade():
    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column("editado_em", sa.DateTime(), nullable=True))
        op.add_column(tabela, sa.Column("editado_por", sa.Integer(), nullable=True))


def downgrade():
    for tabela in _TABELAS:
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_column("editado_por")
            batch_op.drop_column("editado_em")
