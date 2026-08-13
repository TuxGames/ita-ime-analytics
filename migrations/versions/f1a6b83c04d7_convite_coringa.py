"""codigo coringa: libera a conta sem vincular a aluno

Faltava o caso de quem NAO e aluno -- coordenador, professor, conta de teste.
Essas pessoas precisam entrar mas nao podem ser amarradas a um aluno.

O tipo e EXPLICITO (`aluno`/`coringa`) em vez de deduzido de `aluno_id IS NULL`:
a diferenca e de intencao, nao de preenchimento. Um convite de aluno cujo aluno
foi apagado tambem ficaria com aluno_id nulo, e os dois casos nao sao a mesma
coisa.

Os convites que ja existem sao todos de aluno: `tipo` entra com server_default
'aluno' e so depois o default sai.

Revision ID: f1a6b83c04d7
Revises: e7c2a95d13f8
Create Date: 2026-08-14 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f1a6b83c04d7'
down_revision = 'e7c2a95d13f8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    with op.batch_alter_table("convites_aluno", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tipo", sa.String(length=20), nullable=False, server_default="aluno"
            )
        )
        batch_op.add_column(sa.Column("rotulo", sa.String(length=60), nullable=True))
        # Coringa nao tem aluno.
        batch_op.alter_column(
            "aluno_id", existing_type=sa.Integer(), nullable=True
        )

    existentes = conn.execute(
        sa.text("SELECT COUNT(*) FROM convites_aluno WHERE tipo = 'aluno'")
    ).scalar()
    print(f"  [coringa] {existentes} convite(s) existente(s) marcado(s) como tipo 'aluno'.")

    # Daqui em diante quem define o tipo e o codigo, nao o banco.
    with op.batch_alter_table("convites_aluno", schema=None) as batch_op:
        batch_op.alter_column(
            "tipo", existing_type=sa.String(length=20), server_default=None
        )


def downgrade():
    # Coringa nao cabe no schema antigo (aluno_id NOT NULL): some antes.
    conn = op.get_bind()
    apagados = conn.execute(
        sa.text("DELETE FROM convites_aluno WHERE tipo = 'coringa'")
    ).rowcount
    if apagados:
        print(f"  [coringa] {apagados} coringa(s) apagado(s): nao cabem no schema antigo.")

    with op.batch_alter_table("convites_aluno", schema=None) as batch_op:
        batch_op.alter_column(
            "aluno_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.drop_column("rotulo")
        batch_op.drop_column("tipo")
