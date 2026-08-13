"""recalcula a nota do simulado pessoal com a formula proporcional

A `nota_geral` do simulado PESSOAL era a media simples dos percentuais por
materia; o ranking da turma usa proporcional (soma dos acertos / soma das
questoes). Com pesos iguais (ITA, 12 questoes em tudo) as duas coincidem; com
pesos diferentes (IME 15/15/10) divergem, e a mesma prova aparecia como 48,9
numa tela e 5,00 na outra.

Aqui a nota e RECALCULADA a partir de `simulado_materias`, na escala 0-100
(a tela mostra como porcentagem).

SO MEXE EM `nota_automatica = 1`. Nota digitada a mao fica intacta: nao da para
saber em que escala ela foi digitada, e converter no chute corromperia dado do
usuario. Em producao sao 3 registros assim (2.0, 16.0, 16.0), de dois usuarios.

Sem detalhe por materia, o registro tambem fica como esta: nao ha de onde
recalcular.

Revision ID: d4b8c1f70e23
Revises: c9f3b28e71a4
Create Date: 2026-08-13 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd4b8c1f70e23'
down_revision = 'c9f3b28e71a4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Uma consulta so: soma dos acertos e das questoes por simulado, restrita
    # aos automaticos que tem detalhe por materia.
    linhas = conn.execute(
        sa.text(
            "SELECT s.id, s.nota_geral, "
            "       SUM(m.acertos) AS acertos, SUM(m.total_questoes) AS questoes "
            "FROM simulados s "
            "JOIN simulado_materias m ON m.simulado_id = s.id "
            "WHERE s.nota_automatica = 1 "
            "GROUP BY s.id, s.nota_geral "
            "HAVING SUM(m.total_questoes) > 0"
        )
    ).mappings().all()

    mudados = 0
    for linha in linhas:
        nova = round(100.0 * linha["acertos"] / linha["questoes"], 2)
        if abs((linha["nota_geral"] or 0) - nova) < 0.005:
            continue  # ja estava proporcional (ITA: as duas formulas coincidem)
        conn.execute(
            sa.text("UPDATE simulados SET nota_geral = :nova WHERE id = :id"),
            {"nova": nova, "id": linha["id"]},
        )
        mudados += 1

    intocados = conn.execute(
        sa.text("SELECT COUNT(*) FROM simulados WHERE nota_automatica = 0")
    ).scalar()
    print(
        f"  [nota] {len(linhas)} automatico(s) conferido(s), {mudados} recalculado(s); "
        f"{intocados} manual(is) preservado(s)."
    )


def downgrade():
    """Volta a media simples dos percentuais, so nos automaticos.

    Nao e um no-op: quem rodar o downgrade quer o numero antigo de volta.
    """
    conn = op.get_bind()

    ids = conn.execute(
        sa.text("SELECT id FROM simulados WHERE nota_automatica = 1")
    ).scalars().all()

    for simulado_id in ids:
        materias = conn.execute(
            sa.text(
                "SELECT acertos, total_questoes FROM simulado_materias "
                "WHERE simulado_id = :id AND total_questoes > 0"
            ),
            {"id": simulado_id},
        ).mappings().all()
        if not materias:
            continue
        media = sum(100.0 * m["acertos"] / m["total_questoes"] for m in materias)
        media = round(media / len(materias), 2)
        conn.execute(
            sa.text("UPDATE simulados SET nota_geral = :v WHERE id = :id"),
            {"v": media, "id": simulado_id},
        )
