"""grupos (Bloco 2)

Grupo pequeno de usuários que compartilham quanto estudaram: questões feitas
(RegistroEstudo) e simulados feitos (Simulado). Tempo de estudo NUNCA entra
aqui — é por isso que não existe FK nenhuma para sessoes_treino.

grupo_membros guarda o ciclo convite -> aceite -> (opcionalmente) saída:
"convidado" não aparece em nenhuma agregação até virar "ativo"; "saiu" some
de novo. O UNIQUE (grupo_id, user_id) impede convite duplicado do mesmo par.

Revision ID: f6a2c9d4b715
Revises: e4b7c1f9a082
Create Date: 2026-08-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a2c9d4b715'
down_revision = 'e4b7c1f9a082'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "grupos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("criado_por", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["criado_por"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "grupo_membros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grupo_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("convidado_em", sa.DateTime(), nullable=False),
        sa.Column("respondido_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupos.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grupo_id", "user_id"),
    )
    with op.batch_alter_table("grupo_membros", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_grupo_membros_grupo_id"), ["grupo_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_grupo_membros_user_id"), ["user_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("grupo_membros", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_grupo_membros_user_id"))
        batch_op.drop_index(batch_op.f("ix_grupo_membros_grupo_id"))
    op.drop_table("grupo_membros")
    op.drop_table("grupos")
