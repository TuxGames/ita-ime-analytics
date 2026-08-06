"""materias do perfil (D.1)

Campo para o usuário dizer quais matérias ele quer acompanhar de perto — vira
o default do filtro "mostrar apenas" no ranking da turma (D.2). Mesma
convenção de Concurso.materias_csv (nomes do enum Materia separados por
vírgula). NULL = sem preferência cadastrada ainda.

ADD COLUMN simples: SQLite aceita direto, sem batch mode.

Revision ID: c7a5e2f18b9d
Revises: b1e4a6f0d234
Create Date: 2026-08-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7a5e2f18b9d'
down_revision = 'b1e4a6f0d234'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('materias_csv', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('materias_csv')
