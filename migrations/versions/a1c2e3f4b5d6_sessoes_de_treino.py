"""sessoes de treino

Revision ID: a1c2e3f4b5d6
Revises: 752e66781be8
Create Date: 2026-07-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c2e3f4b5d6'
down_revision = '752e66781be8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sessoes_treino',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('materia', sa.Enum('MATEMATICA', 'FISICA', 'QUIMICA', 'PORTUGUES', 'INGLES', 'REDACAO', 'GEOGRAFIA', 'HISTORIA', 'OUTROS', name='materia', native_enum=False, length=20), nullable=True),
    sa.Column('questoes', sa.Integer(), nullable=False),
    sa.Column('tempo_total_seg', sa.Integer(), nullable=False),
    sa.Column('tempo_padrao_seg', sa.Integer(), nullable=True),
    sa.Column('observacao', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sessoes_treino', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessoes_treino_data'), ['data'], unique=False)
        batch_op.create_index(batch_op.f('ix_sessoes_treino_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('sessoes_treino', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessoes_treino_user_id'))
        batch_op.drop_index(batch_op.f('ix_sessoes_treino_data'))

    op.drop_table('sessoes_treino')
