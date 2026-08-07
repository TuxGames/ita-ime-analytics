"""Fase C: sincronização em lote dos rankings da turma para o perfil."""

import json
from datetime import date

from app.models import Concurso, Materia, Simulado, SimuladoTurma
from app.simulado_sync import linhas_pendentes, sincronizar_linha, sugerir_concurso, concursos_por_banca
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from app.vinculo import revincular
from tests.conftest import payload_simulado


def _semear(db, admin, aluno, rotulo="S3"):
    dados = payload_simulado(rotulo=rotulo)
    dados["resultados"][0]["nome"] = "ALUNO NOVATA UM"
    aplicar_simulado(db, parse_simulado(json.dumps(dados)), admin.id)
    db.session.commit()
    revincular()
    db.session.commit()
    return db.session.scalar(db.select(SimuladoTurma))


def _concurso_ita(db, admin):
    # Convenção real de cadastro: banca e ano no mesmo campo, sem " - " (é o
    # que "ITA 2027 - 2ª Fase" também respeitaria) — é o formato que aparece
    # em produção, diferente do "ITA - 2027" que compor_nome("ITA", "2027")
    # produziria se o ano fosse tratado como etapa.
    concurso = Concurso(
        nome="ITA 2027",
        data_prova=date(2027, 11, 1),
        created_by=admin.id,
    )
    concurso.set_materias(
        [Materia.MATEMATICA, Materia.FISICA, Materia.QUIMICA, Materia.INGLES]
    )
    db.session.add(concurso)
    db.session.commit()
    return concurso


def test_sugerir_concurso_casa_por_banca_unica(app, db, admin, criar_usuario):
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")
    turma = _semear(db, admin, aluno)
    concurso = _concurso_ita(db, admin)

    linha = next(ln for ln in turma.linhas if ln.user_id == aluno.id)
    mapa = concursos_por_banca()
    assert sugerir_concurso(linha, mapa).id == concurso.id


def test_sugerir_concurso_casa_ita_com_ita_2027(app, db, admin, criar_usuario):
    """O bug original: SimuladoTurma.banca é "ITA" (sem ano), Concurso.nome é
    "ITA 2027" — antes do Bloco 1 esses dois textos nunca casavam e a
    sincronização em lote sempre caía em escolha manual."""
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")
    turma = _semear(db, admin, aluno)
    assert turma.banca == "ITA"
    concurso = _concurso_ita(db, admin)
    assert concurso.nome == "ITA 2027"

    linha = next(ln for ln in turma.linhas if ln.user_id == aluno.id)
    mapa = concursos_por_banca()
    sugestao = sugerir_concurso(linha, mapa)
    assert sugestao is not None
    assert sugestao.id == concurso.id


def test_sugerir_concurso_ambiguo_com_duas_fases_da_mesma_banca(app, db, admin, criar_usuario):
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")
    turma = _semear(db, admin, aluno)
    _concurso_ita(db, admin)
    segunda_fase = Concurso(
        nome="ITA 2027 - 2ª Fase",
        data_prova=date(2027, 12, 1),
        created_by=admin.id,
    )
    db.session.add(segunda_fase)
    db.session.commit()

    linha = next(ln for ln in turma.linhas if ln.user_id == aluno.id)
    mapa = concursos_por_banca()
    assert sugerir_concurso(linha, mapa) is None


def test_sincronizar_duas_vezes_nao_duplica(app, db, admin, criar_usuario):
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")
    turma = _semear(db, admin, aluno)
    concurso = _concurso_ita(db, admin)
    linha = next(ln for ln in turma.linhas if ln.user_id == aluno.id)

    pendentes = linhas_pendentes(aluno.id)
    assert len(pendentes) == 1

    resultado = sincronizar_linha(linha, concurso, aluno.id)
    db.session.commit()
    assert resultado is not None
    assert resultado.turma_linha_id == linha.id
    assert resultado.origem == "import"
    # A fase da prova (SimuladoTurma.fase) acompanha o Simulado pessoal — antes
    # do Bloco 1 essa informação se perdia na sincronização.
    assert resultado.fase == "objetiva" == turma.fase
    assert resultado.titulo_curto == "ITA S3 · 1ª fase"

    # Segunda rodada: a linha não aparece mais como pendente.
    assert linhas_pendentes(aluno.id) == []

    total = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter_by(user_id=aluno.id)
    )
    assert total == 1


def test_sincronizar_nao_sobrescreve_simulado_manual(app, db, admin, criar_usuario):
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")
    turma = _semear(db, admin, aluno)
    concurso = _concurso_ita(db, admin)
    linha = next(ln for ln in turma.linhas if ln.user_id == aluno.id)

    manual = Simulado(
        user_id=aluno.id,
        concurso_id=concurso.id,
        rotulo=turma.rotulo,
        data_simulado=turma.data,
        nota_geral=7.5,
        nota_automatica=False,
        origem=None,
    )
    db.session.add(manual)
    db.session.commit()

    resultado = sincronizar_linha(linha, concurso, aluno.id)
    db.session.commit()

    assert resultado is None
    db.session.refresh(manual)
    assert manual.nota_geral == 7.5
    assert manual.origem is None
    assert manual.turma_linha_id is None

    total = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter_by(user_id=aluno.id)
    )
    assert total == 1


def test_rota_sincronizar_grava_e_repete_sem_duplicar(app, db, admin, criar_usuario, client, logar):
    aluno = criar_usuario("aluno", nome_oficial="ALUNO NOVATA UM")
    turma = _semear(db, admin, aluno)
    concurso = _concurso_ita(db, admin)
    linha = next(ln for ln in turma.linhas if ln.user_id == aluno.id)

    logar(aluno)
    resposta = client.get("/simulados/sincronizar")
    assert resposta.status_code == 200

    resposta = client.post(
        "/simulados/sincronizar", data={f"concurso_{linha.id}": concurso.id}
    )
    assert resposta.status_code == 302

    total = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter_by(user_id=aluno.id)
    )
    assert total == 1

    # Repetir não muda nada: não há mais linhas pendentes para escolher.
    resposta = client.get("/simulados/sincronizar")
    assert b"Nada pendente" in resposta.data

    resposta = client.post("/simulados/sincronizar", data={})
    assert resposta.status_code == 302
    total = db.session.scalar(
        db.select(db.func.count(Simulado.id)).filter_by(user_id=aluno.id)
    )
    assert total == 1
