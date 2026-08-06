"""aluno como entidade

Até aqui uma pessoa não existia no sistema: quem aparecia em 8 provas eram 8
linhas soltas com o mesmo nome. Esta migration cria a identidade (`alunos`),
as grafias alternativas (`aluno_apelidos`) e reponta todas as linhas.

A semeadura cria UM aluno por `nome_norm` distinto. Isso significa que as
variações conhecidas ("... DE OLIVEIRA M" vs "... MELO COELHO") nascem como
alunos duplicados — de propósito: juntá-las é decisão humana, feita na tela de
merge, e é por isso que a tela faz parte da mesma entrega.

Como nas anteriores, tudo em SQL puro: uma migration precisa continuar rodando
igual daqui a um ano, mesmo depois de o modelo ter mudado.

Revision ID: f2a91c48d370
Revises: e91b47dc2a05
Create Date: 2026-08-06 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a91c48d370'
down_revision = 'e91b47dc2a05'
branch_labels = None
depends_on = None


# (tabela, coluna de data que serve para achar a ocorrência mais recente)
_FONTES = (
    ("resultado_linhas", "resultados_oficiais", "resultado_id"),
    ("simulado_turma_linhas", "simulados_turma", "turma_id"),
)


def _semear_alunos(conn):
    """Um Aluno por nome_norm; nome/turma/série vêm da ocorrência mais recente."""
    # Junta as duas origens numa lista só, com a data da prova para desempate.
    # Listão oficial pode não ter data — cai para o começo dos tempos.
    linhas = conn.execute(
        sa.text(
            """
            SELECT l.nome_norm, l.nome, l.turma, NULL AS serie, l.user_id,
                   COALESCE(r.data, '0001-01-01') AS quando
              FROM resultado_linhas l
              JOIN resultados_oficiais r ON r.id = l.resultado_id
            UNION ALL
            SELECT l.nome_norm, l.nome, l.turma, l.serie, l.user_id,
                   s.data AS quando
              FROM simulado_turma_linhas l
              JOIN simulados_turma s ON s.id = l.turma_id
            """
        )
    ).mappings().all()

    consolidado = {}
    for linha in linhas:
        atual = consolidado.get(linha["nome_norm"])
        if atual is None or str(linha["quando"]) >= str(atual["quando"]):
            # A série só existe no ranking de simulado; não deixe um listão
            # oficial (serie NULL) apagar a série já conhecida.
            serie = linha["serie"] or (atual or {}).get("serie")
            consolidado[linha["nome_norm"]] = {
                "nome": linha["nome"],
                "turma": linha["turma"],
                "serie": serie,
                "quando": linha["quando"],
                "user_id": linha["user_id"] or (atual or {}).get("user_id"),
            }
        elif linha["user_id"] and not atual.get("user_id"):
            atual["user_id"] = linha["user_id"]

    for nome_norm, dados in consolidado.items():
        conn.execute(
            sa.text(
                "INSERT INTO alunos (nome, nome_norm, turma, serie, user_id, "
                "ativo, created_at) VALUES (:nome, :nome_norm, :turma, :serie, "
                ":user_id, 1, datetime('now'))"
            ),
            {"nome": dados["nome"], "nome_norm": nome_norm,
             "turma": dados["turma"], "serie": dados["serie"],
             "user_id": dados["user_id"]},
        )
    print(f"  [alunos] {len(consolidado)} aluno(s) criado(s) a partir das linhas")


def _repontar(conn):
    for tabela, _cabecalho, _fk in _FONTES:
        conn.execute(
            sa.text(
                f"UPDATE {tabela} SET aluno_id = ("
                "  SELECT a.id FROM alunos a WHERE a.nome_norm = "
                f"  {tabela}.nome_norm)"
            )
        )


def _conferir(conn):
    for tabela, _cabecalho, _fk in _FONTES:
        orfas = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {tabela} WHERE aluno_id IS NULL")
        ).scalar()
        if orfas:
            raise RuntimeError(
                f"{orfas} linha(s) de {tabela} ficaram sem aluno_id. Isso não "
                "deveria acontecer: toda linha tem nome_norm e todo nome_norm "
                "virou aluno. Investigue antes de seguir."
            )


def upgrade():
    op.create_table(
        "alunos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("nome_norm", sa.String(length=120), nullable=False),
        sa.Column("turma", sa.String(length=20), nullable=True),
        sa.Column("serie", sa.String(length=20), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("alunos", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_alunos_nome_norm"), ["nome_norm"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_alunos_user_id"), ["user_id"], unique=False)

    op.create_table(
        "aluno_apelidos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aluno_id", sa.Integer(), nullable=False),
        sa.Column("nome_norm", sa.String(length=120), nullable=False),
        sa.Column("origem", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["aluno_id"], ["alunos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("aluno_apelidos", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_aluno_apelidos_nome_norm"), ["nome_norm"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_aluno_apelidos_aluno_id"), ["aluno_id"], unique=False
        )

    for tabela, _cabecalho, _fk in _FONTES:
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.add_column(sa.Column("aluno_id", sa.Integer(), nullable=True))
            batch_op.create_index(
                batch_op.f(f"ix_{tabela}_aluno_id"), ["aluno_id"], unique=False
            )
            batch_op.create_foreign_key(
                f"fk_{tabela}_aluno_id", "alunos", ["aluno_id"], ["id"]
            )

    conn = op.get_bind()
    _semear_alunos(conn)
    _repontar(conn)
    _conferir(conn)


def downgrade():
    """Remove a entidade. Os apelidos criados em merges são perdidos.

    As linhas não são tocadas — nome, turma e série sempre estiveram nelas — mas
    o trabalho de curadoria (quem é a mesma pessoa que quem) não tem onde morar
    no schema antigo e some junto."""
    for tabela, _cabecalho, _fk in _FONTES:
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{tabela}_aluno_id", type_="foreignkey")
            batch_op.drop_index(batch_op.f(f"ix_{tabela}_aluno_id"))
            batch_op.drop_column("aluno_id")

    with op.batch_alter_table("aluno_apelidos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_aluno_apelidos_aluno_id"))
        batch_op.drop_index(batch_op.f("ix_aluno_apelidos_nome_norm"))
    op.drop_table("aluno_apelidos")

    with op.batch_alter_table("alunos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alunos_user_id"))
        batch_op.drop_index(batch_op.f("ix_alunos_nome_norm"))
    op.drop_table("alunos")
