"""Migration de fusão: dois cabeçalhos viram um SEM perder o vínculo das pessoas.

Sobe o schema ANTIGO num SQLite temporário, popula duas turmas com linhas
vinculadas, roda `flask db upgrade` de verdade e confere o resultado. É o teste
mais importante da mudança: `user_id` é o "sou eu" de cada um, e perdê-lo é
silencioso — ninguém reclama até abrir o app e não se achar.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVISAO_ANTIGA = "c3e8a71b4f92"  # antes das duas migrations de turma


def _rodar_flask(args, banco, esperar_sucesso=True):
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = "sqlite:///" + banco.replace("\\", "/")
    ambiente["FLASK_APP"] = "wsgi.py"
    ambiente["SECRET_KEY"] = "chave-de-teste"
    ambiente["PYTHONIOENCODING"] = "utf-8"
    processo = subprocess.run(
        [sys.executable, "-m", "flask", "db", *args],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    saida = (processo.stdout or "") + (processo.stderr or "")
    if esperar_sucesso and processo.returncode != 0:
        raise AssertionError(f"flask db {args} falhou:\n{saida}")
    return processo.returncode, saida


@pytest.fixture
def banco_antigo():
    """SQLite no schema anterior às migrations de turma."""
    pasta = tempfile.mkdtemp(prefix="itaime-teste-")
    caminho = os.path.join(pasta, "antigo.db")
    _rodar_flask(["upgrade", REVISAO_ANTIGA], caminho)
    yield caminho
    shutil.rmtree(pasta, ignore_errors=True)


def _semear_duas_turmas(caminho):
    """Dois cabeçalhos do MESMO concurso, cada um com uma pessoa vinculada."""
    con = sqlite3.connect(caminho)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, is_admin, "
        "must_change_password, created_at) VALUES ('admin', 'x', 1, 0, datetime('now'))"
    )
    admin_id = cur.lastrowid
    cur.execute(
        "INSERT INTO users (username, password_hash, is_admin, "
        "must_change_password, created_at) VALUES ('vet', 'x', 0, 0, datetime('now'))"
    )
    vet_id = cur.lastrowid

    ids = {}
    for turma in ("novata", "veterana"):
        cur.execute(
            "INSERT INTO resultados_oficiais (concurso_nome, turma, fonte, data, "
            "escala, materias_csv, metrica, created_by, created_at) "
            "VALUES ('AFA 2027', ?, 'GGE', NULL, 10.0, 'MATEMATICA,FISICA', 'MP', ?, "
            "datetime('now'))",
            (turma, admin_id),
        )
        ids[turma] = cur.lastrowid

    def linha(header_id, nome, posicao, user_id=None):
        cur.execute(
            "INSERT INTO resultado_linhas (resultado_id, nome, nome_norm, status, "
            "classificacao, metrica_valor, notas_json, user_id) "
            "VALUES (?, ?, ?, 'classificado', ?, 7.0, ?, ?)",
            (header_id, nome, nome, posicao,
             json.dumps({"MATEMATICA": 7.0, "FISICA": 7.0}), user_id),
        )

    linha(ids["novata"], "PESSOA NOVATA UM", 100, admin_id)
    linha(ids["novata"], "PESSOA NOVATA DOIS", 101)
    linha(ids["veterana"], "PESSOA VETERANA UM", 200, vet_id)
    con.commit()
    con.close()
    return admin_id, vet_id


def test_fusao_junta_headers_e_preserva_vinculos(banco_antigo):
    admin_id, vet_id = _semear_duas_turmas(banco_antigo)

    _rodar_flask(["upgrade"], banco_antigo)

    con = sqlite3.connect(banco_antigo)
    headers = con.execute(
        "SELECT id, concurso_nome FROM resultados_oficiais"
    ).fetchall()
    assert len(headers) == 1, "os dois cabeçalhos do concurso viram um"

    por_turma = dict(
        con.execute(
            "SELECT turma, COUNT(*) FROM resultado_linhas GROUP BY turma"
        ).fetchall()
    )
    assert por_turma == {"novata": 2, "veterana": 1}, "nenhuma linha se perdeu"

    vinculos = dict(
        con.execute(
            "SELECT nome, user_id FROM resultado_linhas WHERE user_id IS NOT NULL"
        ).fetchall()
    )
    assert vinculos == {
        "PESSOA NOVATA UM": admin_id,
        "PESSOA VETERANA UM": vet_id,
    }, "o vínculo 'sou eu' sobrevive à fusão"

    colunas = {r[1] for r in con.execute("PRAGMA table_info(resultados_oficiais)")}
    assert "turma" not in colunas, "turma sai do cabeçalho"
    con.close()


def test_fusao_aborta_quando_cabecalhos_divergem(banco_antigo):
    _semear_duas_turmas(banco_antigo)
    con = sqlite3.connect(banco_antigo)
    con.execute("UPDATE resultados_oficiais SET escala = 5.0 WHERE turma = 'veterana'")
    con.commit()
    con.close()

    codigo, saida = _rodar_flask(["upgrade"], banco_antigo, esperar_sucesso=False)

    assert codigo != 0, "não dá para fundir com escalas diferentes"
    assert "escala" in saida
    assert "AFA 2027" in saida


def test_fusao_aborta_com_classificacao_repetida_entre_turmas(banco_antigo):
    _semear_duas_turmas(banco_antigo)
    con = sqlite3.connect(banco_antigo)
    # O veterano recebe a mesma posição nacional de um novato.
    con.execute(
        "UPDATE resultado_linhas SET classificacao = 100 "
        "WHERE nome = 'PESSOA VETERANA UM'"
    )
    con.commit()
    con.close()

    codigo, saida = _rodar_flask(["upgrade"], banco_antigo, esperar_sucesso=False)

    assert codigo != 0
    assert "classifica" in saida.lower()


def test_downgrade_devolve_o_schema_antigo(banco_antigo):
    _semear_duas_turmas(banco_antigo)
    _rodar_flask(["upgrade"], banco_antigo)
    _rodar_flask(["downgrade", REVISAO_ANTIGA], banco_antigo)

    con = sqlite3.connect(banco_antigo)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(resultados_oficiais)")}
    assert "turma" in colunas, "a coluna volta ao cabeçalho"
    # A fusão NÃO é desfeita — o docstring da migration diz isso explicitamente.
    assert con.execute("SELECT COUNT(*) FROM resultados_oficiais").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM resultado_linhas").fetchone()[0] == 3
    con.close()
