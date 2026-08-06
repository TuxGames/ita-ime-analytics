"""Vínculo por nome e as rotas que mudaram de granularidade."""

import json

from app.models import ResultadoOficial, SimuladoTurma, SimuladoTurmaLinha
from app.oficiais_import import aplicar as aplicar_oficial
from app.oficiais_import import parse as parse_oficial
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from app.vinculo import nome_ja_usado, revincular
from tests.conftest import payload_oficial, payload_simulado


def _semear(db, admin):
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("novata"))), admin.id)
    aplicar_oficial(db, parse_oficial(json.dumps(payload_oficial("veterana"))), admin.id)
    aplicar_simulado(db, parse_simulado(json.dumps(payload_simulado())), admin.id)
    db.session.commit()


# --------------------------------------------------------------------------
# Vínculo
# --------------------------------------------------------------------------


def test_revincular_liga_as_duas_fontes(app, db, admin, criar_usuario):
    _semear(db, admin)
    # A mesma pessoa aparece no listão oficial e no ranking do simulado.
    pessoa = criar_usuario("pessoa", nome_oficial="PESSOA NOVATA UM")
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")

    revincular()
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    assert any(ln.user_id == pessoa.id for ln in resultado.linhas)
    prova = db.session.scalar(db.select(SimuladoTurma))
    assert any(ln.user_id == aluno.id for ln in prova.linhas)


def test_revincular_normaliza_acento_e_espaco(app, db, admin, criar_usuario):
    _semear(db, admin)
    usuario = criar_usuario("ze", nome_oficial="  pessoa   novata um  ")
    revincular()
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    assert any(ln.user_id == usuario.id for ln in resultado.linhas)


def test_revincular_desfaz_quando_nome_sai(app, db, admin, criar_usuario):
    _semear(db, admin)
    usuario = criar_usuario("ze", nome_oficial="PESSOA NOVATA UM")
    revincular()
    db.session.commit()

    usuario.nome_oficial = None
    revincular()
    db.session.commit()

    resultado = db.session.scalar(db.select(ResultadoOficial))
    assert all(ln.user_id is None for ln in resultado.linhas)


def test_nome_ja_usado_por_outra_conta(app, db, criar_usuario):
    dono = criar_usuario("dono", nome_oficial="FULANO DE TAL")
    outro = criar_usuario("outro")
    assert nome_ja_usado("FULANO DE TAL", outro.id) is True
    assert nome_ja_usado("FULANO DE TAL", dono.id) is False


# --------------------------------------------------------------------------
# Rotas: filtro por query string
# --------------------------------------------------------------------------


def test_detalhe_filtra_por_turma(app, db, client, admin, logar):
    _semear(db, admin)
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))

    todos = client.get(f"/oficiais/{resultado.id}").get_data(as_text=True)
    assert "PESSOA NOVATA UM" in todos and "PESSOA VETERANA UM" in todos

    so_novata = client.get(f"/oficiais/{resultado.id}?turma=novata").get_data(
        as_text=True
    )
    assert "PESSOA NOVATA UM" in so_novata
    assert "PESSOA VETERANA UM" not in so_novata


def test_posicao_no_colegio_renumera_dentro_do_filtro(app, db, client, admin, logar):
    """Além da classificação nacional (#100), a tela mostra a colocação no grupo.

    Ela vem do índice da lista já ordenada, então acompanha o filtro: o primeiro
    novato é 1º mesmo que existam veteranos melhor colocados nacionalmente."""
    _semear(db, admin)
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))

    todos = client.get(f"/oficiais/{resultado.id}").get_data(as_text=True)
    # PESSOA NOVATA UM é #100 (nacional) e vem antes de PESSOA VETERANA UM (#200).
    assert "No colégio" in todos
    assert todos.index("1º") < todos.index("PESSOA NOVATA UM")

    so_veterana = client.get(f"/oficiais/{resultado.id}?turma=veterana").get_data(
        as_text=True
    )
    assert "Entre veteranos" in so_veterana
    # Sozinho no recorte, o veterano #200 passa a ser o 1º.
    assert "1º" in so_veterana
    assert "#200" in so_veterana
    assert "PESSOA NOVATA UM" not in so_veterana


def test_turma_invalida_cai_em_todos(app, db, client, admin, logar):
    _semear(db, admin)
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))

    pagina = client.get(f"/oficiais/{resultado.id}?turma=xpto").get_data(as_text=True)
    assert "PESSOA NOVATA UM" in pagina and "PESSOA VETERANA UM" in pagina


# --------------------------------------------------------------------------
# Rotas: exclusão granular
# --------------------------------------------------------------------------


def test_excluir_uma_turma_preserva_a_outra(app, db, client, admin, logar):
    _semear(db, admin)
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))

    client.post(f"/oficiais/{resultado.id}/excluir", data={"turma": "novata"})

    resultado = db.session.get(ResultadoOficial, resultado.id)
    assert resultado is not None
    assert resultado.turmas_presentes == ["veterana"]


def test_excluir_ultima_turma_remove_o_concurso(app, db, client, admin, logar):
    _semear(db, admin)
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))
    rid = resultado.id

    client.post(f"/oficiais/{rid}/excluir", data={"turma": "novata"})
    client.post(f"/oficiais/{rid}/excluir", data={"turma": "veterana"})

    assert db.session.get(ResultadoOficial, rid) is None


def test_excluir_sem_turma_remove_tudo(app, db, client, admin, logar):
    _semear(db, admin)
    logar(admin)
    resultado = db.session.scalar(db.select(ResultadoOficial))
    rid = resultado.id

    client.post(f"/oficiais/{rid}/excluir", data={})

    assert db.session.get(ResultadoOficial, rid) is None


def test_usuario_comum_nao_exclui(app, db, client, admin, usuario, logar):
    _semear(db, admin)
    logar(usuario)
    resultado = db.session.scalar(db.select(ResultadoOficial))

    resposta = client.post(
        f"/oficiais/{resultado.id}/excluir", data={"turma": "novata"}
    )

    assert resposta.status_code == 403
    assert db.session.get(ResultadoOficial, resultado.id) is not None


def test_ranking_da_turma_filtra_e_renumera_na_rota(app, db, client, admin, logar):
    _semear(db, admin)
    aplicar_simulado(
        db, parse_simulado(json.dumps(payload_simulado("veterana"))), admin.id
    )
    db.session.commit()
    logar(admin)

    prova = db.session.scalar(db.select(SimuladoTurma))
    pagina = client.get(f"/simulados/turma/{prova.id}?turma=veterana").get_data(
        as_text=True
    )
    assert "ALUNO VETERANA UM" in pagina
    assert "ALUNO NOVATA UM" not in pagina
    assert "1º" in pagina, "o primeiro do recorte é 1º"


def test_linha_guarda_turma_e_serie_separadamente(app, db, admin):
    """CURSO é série da turma novata — nunca deve virar turma."""
    aplicar_simulado(
        db, parse_simulado(json.dumps(payload_simulado("novata"))), admin.id
    )
    db.session.commit()

    curso = db.session.scalar(
        db.select(SimuladoTurmaLinha).filter_by(serie="CURSO")
    )
    assert curso.serie == "CURSO"
    assert curso.turma == "novata"
