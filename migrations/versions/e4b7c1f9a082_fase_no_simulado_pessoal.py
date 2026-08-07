"""fase no simulado pessoal (Bloco 1)

SimuladoTurma já tinha `fase` ("objetiva"/"discursiva"); Simulado não tinha, e
a sincronização em lote nunca a lia — a informação se perdia ao trazer o
ranking da turma para o perfil. Esta coluna fecha essa lacuna. Opcional: quem
digita o simulado à mão pode não informar.

ADD COLUMN simples: SQLite aceita direto, sem batch mode.

Revision ID: e4b7c1f9a082
Revises: d8f3c6a1e457
Create Date: 2026-08-07 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4b7c1f9a082'
down_revision = 'd8f3c6a1e457'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('simulados', sa.Column('fase', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.drop_column('fase')
