"""ranking de simulado da turma e origem do simulado

Revision ID: c3e8a71b4f92
Revises: b7d4f9a02c11
Create Date: 2026-08-05 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e8a71b4f92'
down_revision = 'b7d4f9a02c11'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('simulados_turma',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('banca', sa.String(length=40), nullable=False),
    sa.Column('rotulo', sa.String(length=20), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('turma', sa.String(length=20), nullable=False),
    sa.Column('fonte', sa.String(length=40), nullable=True),
    sa.Column('materias_csv', sa.String(length=200), nullable=False),
    sa.Column('materias_media_csv', sa.String(length=200), nullable=True),
    sa.Column('questoes_json', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('banca', 'rotulo', 'turma')
    )

    op.create_table('simulado_turma_linhas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('turma_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('nome_norm', sa.String(length=120), nullable=False),
    sa.Column('serie', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('acertos_json', sa.Text(), nullable=True),
    sa.Column('media_oficial', sa.Float(), nullable=True),
    sa.Column('geral_oficial', sa.Float(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['turma_id'], ['simulados_turma.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('simulado_turma_linhas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_simulado_turma_linhas_turma_id'), ['turma_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulado_turma_linhas_nome_norm'), ['nome_norm'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulado_turma_linhas_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origem', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.drop_column('origem')

    with op.batch_alter_table('simulado_turma_linhas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_simulado_turma_linhas_user_id'))
        batch_op.drop_index(batch_op.f('ix_simulado_turma_linhas_nome_norm'))
        batch_op.drop_index(batch_op.f('ix_simulado_turma_linhas_turma_id'))

    op.drop_table('simulado_turma_linhas')
    op.drop_table('simulados_turma')
