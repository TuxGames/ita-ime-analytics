"""`fase` na chave da prova: as duas fases do mesmo simulado convivem.

Antes disto a chave era (banca, rotulo, data), e as duas fases compartilham as
três. O pior caso não era um erro na tela: era `aplicar()` encontrar a prova da
OUTRA fase, cair no ramo de reimport e apagar as linhas dela em silêncio.

Este arquivo cobre os quatro grupos do levantamento:

  A. as buscas pela tripla antiga (import e preview)
  B. a guarda que virou letra morta
  C. o simulado pessoal, que casava por (user_id, rotulo)
  D. as telas que mostrariam a mesma prova duas vezes
"""

import json
from datetime import date

import pytest

from app.evolucao import evolucao_do_aluno
from app.models import Aluno, Concurso, Simulado, SimuladoTurma
from app.simulado_sync import simulado_pessoal_da_prova
from app.simulado_turma_import import aplicar, parse

from .conftest import payload_simulado


def _parse(payload):
    return parse(json.dumps(payload))


def _concurso(db, admin):
    c = Concurso(nome="ITA 2027", data_prova=date(2026, 12, 13), created_by=admin.id)
    db.session.add(c)
    db.session.commit()
    return c


def _as_duas_fases(db, admin, turma="novata"):
    aplicar(db, _parse(payload_simulado(turma)), admin.id)
    aplicar(db, _parse(payload_simulado(turma, fase="discursiva")), admin.id)
    db.session.commit()
    provas = db.session.scalars(db.select(SimuladoTurma)).all()
    objetiva = next(p for p in provas if p.fase == "objetiva")
    discursiva = next(p for p in provas if p.fase == "discursiva")
    return objetiva, discursiva


# --------------------------------------------------------------------------
# A. As buscas
# --------------------------------------------------------------------------


def test_importar_a_2a_fase_nao_apaga_a_1a(app, db, admin):
    """O pior caso de todos, e o motivo de a migration existir.

    Sem `fase` na busca de `aplicar()`, a segunda importação encontrava a prova
    da primeira e removia as linhas daquela turma antes de gravar as novas.
    Perda silenciosa de dado real.
    """
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()
    antes = len(db.session.scalar(db.select(SimuladoTurma)).linhas)
    assert antes > 0

    objetiva, discursiva = _as_duas_fases(db, admin)

    assert len(objetiva.linhas) == antes, "a 2ª fase apagou as linhas da 1ª"
    assert len(discursiva.linhas) > 0


def test_as_duas_fases_convivem_no_banco(app, db, admin):
    objetiva, discursiva = _as_duas_fases(db, admin)

    assert objetiva.id != discursiva.id
    assert (objetiva.banca, objetiva.rotulo, objetiva.data) == (
        discursiva.banca, discursiva.rotulo, discursiva.data
    )


def test_a_chave_ainda_recusa_a_mesma_fase_duas_vezes(app, db, admin):
    """A fase relaxou a chave, não a desligou: reimportar a MESMA fase continua
    caindo no ramo de reimport, que substitui em vez de duplicar."""
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()

    assert len(db.session.scalars(db.select(SimuladoTurma)).all()) == 1


def test_preview_do_import_acha_a_prova_da_fase_certa(client, db, admin, logar):
    """Sem `fase`, o preview de uma 2ª fase encontrava a 1ª e dizia "já
    existe", mostrando a prova errada ao admin."""
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()
    logar(admin)

    resposta = client.post(
        "/simulados/turma/importar",
        data={"payload": json.dumps(payload_simulado("novata", fase="discursiva"))},
    )

    assert resposta.status_code == 200
    assert "Traceback" not in resposta.get_data(as_text=True)


# --------------------------------------------------------------------------
# B. A guarda que saiu
# --------------------------------------------------------------------------


def test_o_cabecalho_ainda_e_conferido_entre_turmas(app, db, admin):
    """Tirar a checagem de fase não podia derrubar as outras: as duas TURMAS da
    mesma prova continuam tendo que trazer o mesmo cabeçalho."""
    from app.validacao import ErroImport

    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()

    outro = payload_simulado("veterana")
    outro["materias"] = ["MAT", "FIS"]
    outro["materias_media"] = ["MAT", "FIS"]
    outro["questoes"] = {"MAT": 12, "FIS": 12}
    for r in outro["resultados"]:
        if r["status"] == "presente":
            r["acertos"] = {"MAT": 5, "FIS": 5}
            r["geral_oficial"] = 10  # senão a validação da coluna GERAL pega antes

    with pytest.raises(ErroImport, match="matérias"):
        aplicar(db, _parse(outro), admin.id)


# --------------------------------------------------------------------------
# C. O simulado pessoal
# --------------------------------------------------------------------------


def test_cada_fase_tem_o_proprio_simulado_pessoal(app, db, admin):
    """`(user_id, rotulo)` deixou de identificar a prova quando a 2ª fase
    passou a existir: o S5 objetivo e o S5 discursivo são registros
    diferentes."""
    objetiva, discursiva = _as_duas_fases(db, admin)
    concurso = _concurso(db, admin)
    db.session.add(Simulado(
        user_id=admin.id, concurso_id=concurso.id, rotulo=objetiva.rotulo,
        fase="objetiva", data_simulado=objetiva.data, nota_geral=7.0,
        origem="import",
    ))
    db.session.commit()

    assert simulado_pessoal_da_prova(admin.id, objetiva) is not None
    assert simulado_pessoal_da_prova(admin.id, discursiva) is None


def test_registro_manual_sem_fase_protege_as_duas(app, db, admin):
    """`Simulado.fase` é anulável: quem digitou à mão pode não ter dito a fase.

    Um `filter_by(fase=...)` seco não casaria com esse registro e passaria a
    criar um segundo simulado ao lado — quebrando a promessa de que registro
    manual nunca é tocado. O lado seguro do erro é proteger as duas fases.
    """
    objetiva, discursiva = _as_duas_fases(db, admin)
    concurso = _concurso(db, admin)
    db.session.add(Simulado(
        user_id=admin.id, concurso_id=concurso.id, rotulo=objetiva.rotulo,
        fase=None, data_simulado=objetiva.data, nota_geral=7.0, origem=None,
    ))
    db.session.commit()

    for prova in (objetiva, discursiva):
        achado = simulado_pessoal_da_prova(admin.id, prova)
        assert achado is not None, "o registro manual deixou de proteger"
        assert not achado.veio_de_import


def test_a_fase_exata_ganha_do_registro_sem_fase(app, db, admin):
    """Havendo os dois, o da fase certa é o que importa."""
    objetiva, _ = _as_duas_fases(db, admin)
    concurso = _concurso(db, admin)
    sem_fase = Simulado(
        user_id=admin.id, concurso_id=concurso.id, rotulo=objetiva.rotulo,
        fase=None, data_simulado=objetiva.data, nota_geral=7.0, origem=None,
    )
    com_fase = Simulado(
        user_id=admin.id, concurso_id=concurso.id, rotulo=objetiva.rotulo,
        fase="objetiva", data_simulado=objetiva.data, nota_geral=8.0,
        origem="import",
    )
    db.session.add_all([sem_fase, com_fase])
    db.session.commit()

    assert simulado_pessoal_da_prova(admin.id, objetiva).id == com_fase.id


# --------------------------------------------------------------------------
# D. As telas
# --------------------------------------------------------------------------


def test_a_evolucao_distingue_as_duas_fases_no_rotulo(app, db, admin):
    """As duas fases compartilham a data. Sem a fase no rótulo, o gráfico
    mostraria dois pontos escritos exatamente igual."""
    _as_duas_fases(db, admin)
    aluno = db.session.scalar(db.select(Aluno).order_by(Aluno.id))

    labels = evolucao_do_aluno(aluno.id)["labels"]

    assert len(labels) == len(set(labels)), f"rótulos repetidos: {labels}"
    assert any("1ª fase" in x or "1a fase" in x.lower() for x in labels)
    assert any("2ª fase" in x or "2a fase" in x.lower() for x in labels)


def test_a_ordem_da_evolucao_nao_fica_por_conta_do_banco(app, db, admin):
    """Data empatada precisa de desempate explícito: objetiva antes de
    discursiva, que é a ordem em que a pessoa fez as provas."""
    _as_duas_fases(db, admin)
    aluno = db.session.scalar(db.select(Aluno).order_by(Aluno.id))

    labels = evolucao_do_aluno(aluno.id)["labels"]

    primeira = next(i for i, x in enumerate(labels) if "1ª fase" in x)
    segunda = next(i for i, x in enumerate(labels) if "2ª fase" in x)
    assert primeira < segunda


def test_a_ficha_do_professor_distingue_as_fases(client, db, admin, logar):
    from app.ficha import ficha_do_aluno

    _as_duas_fases(db, admin)
    aluno = db.session.scalar(db.select(Aluno).order_by(Aluno.id))

    provas = [s["prova"] for s in ficha_do_aluno(aluno)["simulados"]]

    assert len(provas) == len(set(provas)), f"a ficha repete o nome: {provas}"


def test_a_listagem_de_rankings_mostra_as_duas(client, db, admin, logar):
    _as_duas_fases(db, admin)
    logar(admin)

    resposta = client.get("/simulados/turma/")

    assert resposta.status_code == 200
    assert "Traceback" not in resposta.get_data(as_text=True)
