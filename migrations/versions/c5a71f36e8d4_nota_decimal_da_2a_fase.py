"""notas decimais da 2a fase, medias copiadas e a segunda data do titulo

Tres colunas, nenhuma preenchida por esta migration -- todas anulaveis, todas
NULL nas linhas existentes, que sao todas de 1a fase.

notas_json em simulado_turma_linhas
    Notas decimais 0-10 por materia da 2a fase, AO LADO de acertos_json e nao
    dentro dele. Em acertos_json os valores sao questoes CERTAS, inteiras,
    sobre um total; na discursiva a nota ja nasce em 0-10 e nao existe total de
    questoes. Uma coluna com os dois significados obrigaria cada um dos ~14
    leitores a saber a fase para interpretar o numero, e quem errasse nao
    quebraria: mostraria "5.7/12" como se fosse acerto de questao. Separadas,
    um leitor que nao conhece a 2a fase ve acertos vazio e nao desenha nada.

    Mesmo nome e mesmo formato de resultado_linhas.notas_json, que ja guarda
    nota decimal dos listoes oficiais desde a b7d4f9a02c11.

media_informada em simulado_turma_linhas
    A coluna de media da planilha, COPIADA, sem carimbo de significado. No ITA
    S5 sabemos que e a media do bloco discursivo; na planilha do IME S6 ha uma
    coluna "Media" sozinha que nao se reproduz a partir das seis materias dela,
    e pode ja ser a media final. Ate o colegio responder, guardar sem afirmar.

    Separada de media_oficial, que ja existe e tem contrato exato (a MEDIA da
    objetiva, conferida contra a soma dos acertos por validar_geral_oficial).
    Reusar aquela contaminaria um campo de significado conhecido.

media_final_informada em simulado_turma_linhas
    A coluna MEDIA FINAL, so quando a planilha traz as duas fases lado a lado e
    a nomeia. NULL quando nao existe -- nunca calculada. A formula observada
    (0,8 x discursivo + 0,2 x objetiva) confere linha a linha no ITA S5, mas e
    observada, nao publicada: serve para CONFERIR a leitura, nunca como fonte.

data_secundaria em simulados_turma
    Alguns titulos trazem duas datas ("Simulado IME S6 - 11/07/2026 -
    14/04/2026"). Nao sabemos qual e qual, e essa e justamente a pista para
    descobrir o que a coluna "Media" do IME significa. Descartar seria perder a
    evidencia.

Revision ID: c5a71f36e8d4
Revises: b3d9e07f2c15
Create Date: 2026-08-19 14:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'c5a71f36e8d4'
down_revision = 'b3d9e07f2c15'
branch_labels = None
depends_on = None


def upgrade():
    # Colunas anulaveis: ADD COLUMN simples basta no SQLite, sem recriar tabela.
    # A recriacao com copy_from fica para a migration da chave unica.
    with op.batch_alter_table("simulado_turma_linhas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notas_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("media_informada", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("media_final_informada", sa.Float(), nullable=True)
        )

    with op.batch_alter_table("simulados_turma", schema=None) as batch_op:
        batch_op.add_column(sa.Column("data_secundaria", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("simulados_turma", schema=None) as batch_op:
        batch_op.drop_column("data_secundaria")

    with op.batch_alter_table("simulado_turma_linhas", schema=None) as batch_op:
        batch_op.drop_column("media_final_informada")
        batch_op.drop_column("media_informada")
        batch_op.drop_column("notas_json")
