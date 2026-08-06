"""sincronização: turma_linha_id em simulados

Fase C (sincronizar simulados da turma para o perfil). Hoje `Simulado` guarda só
`origem="import"`, sem vínculo de volta para a linha do ranking que o gerou —
clicar em "Sincronizar" duas vezes duplicaria tudo. Esta coluna aponta para a
`SimuladoTurmaLinha` de origem, e o unique em (user_id, turma_linha_id) é a
trava que faz a segunda sincronização pular o que já foi trazido.

ADD COLUMN simples funciona sem batch mode no SQLite; o UNIQUE composto,
porém, precisa de batch_alter_table (é criação de índice/constraint).

Revision ID: b1e4a6f0d234
Revises: a4c7d2e91b03
Create Date: 2026-08-06 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1e4a6f0d234'
down_revision = 'a4c7d2e91b03'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.add_column(sa.Column('turma_linha_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_simulados_turma_linha_id'), ['turma_linha_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_simulados_turma_linha_id', 'simulado_turma_linhas', ['turma_linha_id'], ['id']
        )
        batch_op.create_unique_constraint(
            'uq_simulados_user_turma_linha', ['user_id', 'turma_linha_id']
        )


def downgrade():
    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.drop_constraint('uq_simulados_user_turma_linha', type_='unique')
        batch_op.drop_constraint('fk_simulados_turma_linha_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_simulados_turma_linha_id'))
        batch_op.drop_column('turma_linha_id')
