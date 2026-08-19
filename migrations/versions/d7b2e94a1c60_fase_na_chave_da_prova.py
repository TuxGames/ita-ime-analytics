"""fase entra na chave unica da prova: as duas fases sao provas distintas

Hoje a chave e (banca, rotulo, data). As duas fases do MESMO simulado
compartilham as tres -- "ITA S5 09/05/2026" objetiva e discursiva colidem. Sem
isto nao da nem para representar a planilha de dois blocos do ITA S5.

Por que e seguro rodar em qualquer base:

    A chave nova e ESTRITAMENTE MAIS FRACA. Todo conjunto de linhas que
    satisfaz a unicidade de tres colunas satisfaz a de quatro. Entao esta
    migration nao pode falhar por dado existente, seja qual for a contagem. E
    nao ha backfill: `fase` ja e NOT NULL com default 'objetiva' desde a
    e91b47dc2a05.

O que ela evitava, e que passa a ser responsabilidade do codigo:

    Sem fase na chave, `aplicar()` do simulado_turma_import encontrava a linha
    da OUTRA fase e caia no ramo de reimport, que apaga as linhas daquela turma
    antes de gravar as novas. Importar a discursiva apagaria a objetiva, em
    silencio. A guarda que segurava isso (_conferir_cabecalho comparando
    `existente.fase != dados["fase"]`) sai junto nesta versao: com fase na
    chave ela nunca mais dispara, e guarda que nao dispara vira comentario que
    mente.

SQLite nao altera constraint no lugar, entao e batch_alter_table com copy_from:
a tabela e recriada com a definicao abaixo e os dados copiados.

Revision ID: d7b2e94a1c60
Revises: c5a71f36e8d4
Create Date: 2026-08-19 15:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'd7b2e94a1c60'
down_revision = 'c5a71f36e8d4'
branch_labels = None
depends_on = None

# Definicao explicita da tabela como ela e NESTE ponto da historia. Escrita a
# mao de proposito: importar o modelo faria a migration seguir o models.py e
# quebrar silenciosamente quando ele mudar no futuro.
TABELA = sa.Table(
    "simulados_turma",
    sa.MetaData(),
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("banca", sa.String(length=40), nullable=False),
    sa.Column("rotulo", sa.String(length=20), nullable=False),
    sa.Column("data", sa.Date(), nullable=False),
    sa.Column("fase", sa.String(length=20), nullable=False),
    sa.Column("data_secundaria", sa.Date(), nullable=True),
    sa.Column("fonte", sa.String(length=40), nullable=True),
    sa.Column("materias_csv", sa.String(length=200), nullable=False),
    sa.Column("materias_media_csv", sa.String(length=200), nullable=True),
    sa.Column("questoes_json", sa.Text(), nullable=False),
    sa.Column("created_by", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
        "banca", "rotulo", "data", name="uq_simulados_turma_prova"
    ),
)


def upgrade():
    with op.batch_alter_table(
        "simulados_turma", schema=None, copy_from=TABELA
    ) as batch_op:
        batch_op.drop_constraint("uq_simulados_turma_prova", type_="unique")
        batch_op.create_unique_constraint(
            "uq_simulados_turma_prova", ["banca", "rotulo", "data", "fase"]
        )


def downgrade():
    # Volta para a chave de tres colunas. ATENCAO: se ja existirem as duas
    # fases da mesma prova, o downgrade FALHA na hora de recriar a constraint
    # -- e falhar e o certo, porque a alternativa seria escolher uma das duas
    # provas para descartar.
    with op.batch_alter_table("simulados_turma", schema=None) as batch_op:
        batch_op.drop_constraint("uq_simulados_turma_prova", type_="unique")
        batch_op.create_unique_constraint(
            "uq_simulados_turma_prova", ["banca", "rotulo", "data"]
        )
