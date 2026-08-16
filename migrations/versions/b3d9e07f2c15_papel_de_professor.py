"""papel de professor: ve ficha do aluno, nao ve estudo nem treino

Professor/coordenacao ganha uma ficha por aluno -- simulados e oficiais
reunidos. Nota de simulado e dado que o colegio ja distribui para a turma; a
ficha e conveniencia sobre dado que ja circula.

O que NAO entra na ficha: estudo, treino e registro de questoes. A pessoa
digitou isso aqui achando que era dela, e so compartilha dentro de um grupo,
por escolha. Se vazasse, ela pararia de registrar.

Coluna nova com default FALSE: ninguem vira professor por acidente. Quem marca
e o admin, em /admin/convites.

Revision ID: b3d9e07f2c15
Revises: f1a6b83c04d7
Create Date: 2026-08-15 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'b3d9e07f2c15'
down_revision = 'f1a6b83c04d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_professor", sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("is_professor", existing_type=sa.Boolean(),
                              server_default=None)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_professor")
