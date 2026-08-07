"""Fase F: backup, exportação (ida e volta com o importador) e histórico de import."""

import json

from app.exportacao import (
    exportar_dados_usuario,
    exportar_resultado_oficial,
    exportar_simulado_turma,
)
from app.models import HistoricoImport, ResultadoOficial, SimuladoTurma
from app.oficiais_import import aplicar as aplicar_oficial
from app.oficiais_import import parse as parse_oficial
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from tests.conftest import payload_oficial, payload_simulado


def _parse_oficial(dados):
    return parse_oficial(json.dumps(dados))


def _parse_simulado(dados):
    return parse_simulado(json.dumps(dados))


# --------------------------------------------------------------------------
# Exportação — ida e volta sem perda
# --------------------------------------------------------------------------


def test_exportar_resultado_oficial_reimporta_sem_erro(app, db, admin):
    aplicar_oficial(db, _parse_oficial(payload_oficial("novata")), admin.id)
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    exportado = exportar_resultado_oficial(resultado, "novata")

    # O formato exportado tem que ser aceito de volta pelo parser, sem erro.
    reparsed = parse_oficial(json.dumps(exportado))
    assert reparsed["concurso"] == payload_oficial("novata")["concurso"]
    assert len(reparsed["linhas"]) == len(resultado.linhas)


def test_exportar_simulado_turma_reimporta_sem_erro(app, db, admin):
    aplicar_simulado(db, _parse_simulado(payload_simulado("novata")), admin.id)
    db.session.commit()

    turma_obj = db.session.scalar(db.select(SimuladoTurma))
    exportado = exportar_simulado_turma(turma_obj, "novata")

    reparsed = parse_simulado(json.dumps(exportado))
    assert reparsed["banca"] == "ITA"
    assert reparsed["rotulo"] == "S3"
    assert len(reparsed["linhas"]) == len(
        [ln for ln in turma_obj.linhas if ln.turma == "novata"]
    )


def test_exportar_dados_usuario_traz_so_o_que_e_dele(app, db, admin, usuario):
    aplicar_simulado(db, _parse_simulado(payload_simulado("novata")), admin.id)
    db.session.commit()
    linha = db.session.scalar(
        db.select(SimuladoTurma).limit(1)
    ).linhas[0]
    linha.user_id = usuario.id
    db.session.commit()

    dados = exportar_dados_usuario(usuario)
    assert dados["usuario"] == usuario.username
    assert len(dados["rankings_simulado"]) == 1
    assert dados["rankings_simulado"][0]["turma"] == "novata"


# --------------------------------------------------------------------------
# Rotas de exportação
# --------------------------------------------------------------------------


def test_rota_baixar_meus_dados(app, db, usuario, client, logar):
    logar(usuario)
    resposta = client.get("/meus-dados")
    assert resposta.status_code == 200
    assert resposta.mimetype == "application/json"
    corpo = json.loads(resposta.get_data(as_text=True))
    assert corpo["usuario"] == usuario.username


def test_rota_exportar_oficial_recusa_usuario_comum(app, db, admin, usuario, client, logar):
    aplicar_oficial(db, _parse_oficial(payload_oficial("novata")), admin.id)
    db.session.commit()
    resultado = db.session.scalar(db.select(ResultadoOficial))

    logar(usuario)
    resposta = client.get(f"/oficiais/{resultado.id}/exportar?turma=novata")
    assert resposta.status_code == 403


def test_rota_exportar_oficial_funciona_para_admin(app, db, admin, client, logar):
    aplicar_oficial(db, _parse_oficial(payload_oficial("novata")), admin.id)
    db.session.commit()
    resultado = db.session.scalar(db.select(ResultadoOficial))

    logar(admin)
    resposta = client.get(f"/oficiais/{resultado.id}/exportar?turma=novata")
    assert resposta.status_code == 200
    corpo = json.loads(resposta.get_data(as_text=True))
    assert corpo["tipo"] == "oficial"


def test_rota_exportar_simulado_turma_recusa_usuario_comum(app, db, admin, usuario, client, logar):
    aplicar_simulado(db, _parse_simulado(payload_simulado("novata")), admin.id)
    db.session.commit()
    turma_obj = db.session.scalar(db.select(SimuladoTurma))

    logar(usuario)
    resposta = client.get(f"/simulados/turma/{turma_obj.id}/exportar?turma=novata")
    assert resposta.status_code == 403


def test_rota_exportar_simulado_turma_funciona_para_admin(app, db, admin, client, logar):
    aplicar_simulado(db, _parse_simulado(payload_simulado("novata")), admin.id)
    db.session.commit()
    turma_obj = db.session.scalar(db.select(SimuladoTurma))

    logar(admin)
    resposta = client.get(f"/simulados/turma/{turma_obj.id}/exportar?turma=novata")
    assert resposta.status_code == 200
    corpo = json.loads(resposta.get_data(as_text=True))
    assert corpo["tipo"] == "simulado"


# --------------------------------------------------------------------------
# Histórico de import (F.3)
# --------------------------------------------------------------------------


def test_import_oficial_grava_historico_com_json_cru(app, db, admin, client, logar):
    logar(admin)
    payload = payload_oficial("novata")
    texto = json.dumps(payload)
    client.post(
        "/oficiais/importar",
        data={"payload": texto, "acao": "confirmar"},
    )

    historico = db.session.scalars(db.select(HistoricoImport)).all()
    assert len(historico) == 1
    assert historico[0].tipo == "oficial"
    assert historico[0].created_by == admin.id
    assert json.loads(historico[0].payload_json) == payload


def test_import_simulado_grava_historico_com_json_cru(app, db, admin, client, logar):
    logar(admin)
    payload = payload_simulado("novata")
    texto = json.dumps(payload)
    client.post(
        "/simulados/turma/importar",
        data={"payload": texto, "data": "2026-04-11", "acao": "confirmar"},
    )

    historico = db.session.scalars(db.select(HistoricoImport)).all()
    assert len(historico) == 1
    assert historico[0].tipo == "simulado"
    assert historico[0].created_by == admin.id
    assert json.loads(historico[0].payload_json) == payload


def test_historico_nao_e_gravado_quando_import_falha(app, db, admin, client, logar):
    logar(admin)
    client.post(
        "/oficiais/importar",
        data={"payload": "{not valid json", "acao": "confirmar"},
    )
    assert db.session.scalars(db.select(HistoricoImport)).all() == []


# --------------------------------------------------------------------------
# flask backup
# --------------------------------------------------------------------------


def test_comando_backup_cria_arquivo(app, tmp_path):
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'origem.db'}"
    # O comando lê o caminho do banco a partir da URI configurada; para um
    # arquivo real existir, criamos um SQLite vazio nesse caminho.
    import sqlite3

    origem = tmp_path / "origem.db"
    sqlite3.connect(str(origem)).close()

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["backup", "--para", str(tmp_path / "backups")])
    assert resultado.exit_code == 0, resultado.output
    assert "Backup criado" in resultado.output
    arquivos = list((tmp_path / "backups").glob("itaime-*.db"))
    assert len(arquivos) == 1
    assert arquivos[0].stat().st_size > 0
