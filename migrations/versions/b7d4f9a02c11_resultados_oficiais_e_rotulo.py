"""resultados oficiais, vinculo por nome e rotulo do simulado

Revision ID: b7d4f9a02c11
Revises: a1c2e3f4b5d6
Create Date: 2026-08-05 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d4f9a02c11'
down_revision = 'a1c2e3f4b5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('resultados_oficiais',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('concurso_nome', sa.String(length=80), nullable=False),
    sa.Column('turma', sa.String(length=20), nullable=False),
    sa.Column('fonte', sa.String(length=40), nullable=True),
    sa.Column('data', sa.Date(), nullable=True),
    sa.Column('escala', sa.Float(), nullable=False),
    sa.Column('materias_csv', sa.String(length=200), nullable=False),
    sa.Column('metrica', sa.String(length=20), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('concurso_nome', 'turma')
    )

    op.create_table('resultado_linhas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resultado_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('nome_norm', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('classificacao', sa.Integer(), nullable=True),
    sa.Column('metrica_valor', sa.Float(), nullable=True),
    sa.Column('notas_json', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['resultado_id'], ['resultados_oficiais.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('resultado_linhas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_resultado_linhas_resultado_id'), ['resultado_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_resultado_linhas_nome_norm'), ['nome_norm'], unique=False)
        batch_op.create_index(batch_op.f('ix_resultado_linhas_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nome_oficial', sa.String(length=120), nullable=True))

    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rotulo', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('simulados', schema=None) as batch_op:
        batch_op.drop_column('rotulo')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('nome_oficial')

    with op.batch_alter_table('resultado_linhas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_resultado_linhas_user_id'))
        batch_op.drop_index(batch_op.f('ix_resultado_linhas_nome_norm'))
        batch_op.drop_index(batch_op.f('ix_resultado_linhas_resultado_id'))

    op.drop_table('resultado_linhas')
    op.drop_table('resultados_oficiais')
