"""O vínculo conta ↔ aluno sai só do código de convite ou da mão do admin.

O "Sou eu" deixava qualquer conta se declarar dona de qualquer linha, sem
ninguém conferir — a mesma porta que o convite existe para fechar. E o campo
"meu nome nas listas" era a outra metade: `revincular()` decide tudo a partir
de `User.nome_oficial`, então sem entrada nova nenhum vínculo por nome nasce.
"""

import json

import pytest

from app.convites import ErroConvite, vincular_a_mao
from app.models import Aluno, ResultadoLinha, SimuladoTurmaLinha, User, normalizar_nome
from app.oficiais_import import aplicar as aplicar_of, parse as parse_of
from app.simulado_turma_import import aplicar as aplicar_tur, parse as parse_tur
from app.vinculo import revincular

from .conftest import payload_oficial, payload_simulado

SENHA = "senha-de-teste-123"


def _aluno(db, nome="MARIA DE SOUZA LIMA"):
    a = Aluno(nome=nome, nome_norm=normalizar_nome(nome), turma="novata")
    db.session.add(a)
    db.session.commit()
    return a


def _conta(db, username="guilherme", liberada=True):
    """Como as 12 de produção: liberada pela migration, sem aluno."""
    u = User(username=username, is_admin=False, must_change_password=False,
             convite_ok=liberada)
    u.set_password(SENHA)
    db.session.add(u)
    db.session.commit()
    return u


# --------------------------------------------------------------------------
# Pré-requisito: o admin consegue vincular sem depender de resgate
# --------------------------------------------------------------------------


def test_admin_vincula_conta_existente_a_um_aluno(app, db, admin, client, logar):
    aluno = _aluno(db)
    conta = _conta(db)
    logar(admin)

    client.post(f"/admin/convites/{aluno.id}/vincular", data={"user_id": conta.id})

    atualizado = db.session.get(Aluno, aluno.id)
    assert atualizado.user_id == conta.id
    assert atualizado.vinculo_por_codigo is True, "precisa ser autoritativo"


def test_vinculo_a_mao_sobrevive_ao_revincular(app, db, admin):
    """`revincular()` roda após cada import; não pode desfazer a decisão do admin."""
    aluno = _aluno(db, "PESSOA NOVATA UM")
    conta = _conta(db)
    vincular_a_mao(aluno, conta)
    db.session.commit()

    revincular()
    db.session.commit()

    assert db.session.get(Aluno, aluno.id).user_id == conta.id


def test_aluno_que_ja_tem_conta_e_recusado(app, db, admin):
    aluno = _aluno(db)
    dono = _conta(db, "dono")
    outra = _conta(db, "outra")
    vincular_a_mao(aluno, dono)
    db.session.commit()

    with pytest.raises(ErroConvite, match="já está vinculado"):
        vincular_a_mao(aluno, outra)


def test_conta_que_ja_tem_aluno_e_recusada(app, db, admin):
    """Duas pessoas no mesmo aluno quebraria o ranking; o inverso também."""
    um = _aluno(db, "ALUNO UM")
    dois = _aluno(db, "ALUNO DOIS")
    conta = _conta(db)
    vincular_a_mao(um, conta)
    db.session.commit()

    with pytest.raises(ErroConvite, match="já está vinculado"):
        vincular_a_mao(dois, conta)


def test_seletor_so_mostra_conta_sem_aluno(client, db, admin, logar):
    aluno = _aluno(db, "HELENA DIAS MOURA")
    livre = _conta(db, "livre")
    ocupada = _conta(db, "ocupada")
    outro = _aluno(db, "OUTRO ALUNO")
    vincular_a_mao(outro, ocupada)
    db.session.commit()
    logar(admin)

    corpo = client.get("/admin/convites").get_data(as_text=True)

    assert 'value="%d"' % livre.id in corpo
    assert 'value="%d"' % ocupada.id not in corpo


def test_so_admin_vincula(client, db, usuario, logar):
    logar(usuario)

    assert client.post("/admin/convites/1/vincular", data={"user_id": 1}).status_code == 403


# --------------------------------------------------------------------------
# "Sou eu" fechado — botão fora E rota fechada
# --------------------------------------------------------------------------


def _linhas(db, admin):
    aplicar_of(db, parse_of(json.dumps(payload_oficial("novata"))), admin.id)
    aplicar_tur(db, parse_tur(json.dumps(payload_simulado("novata"))), admin.id)
    db.session.commit()
    return (
        db.session.scalar(db.select(ResultadoLinha).order_by(ResultadoLinha.id)),
        db.session.scalar(db.select(SimuladoTurmaLinha).order_by(SimuladoTurmaLinha.id)),
    )


def test_post_direto_no_sou_eu_do_listao_da_403(client, db, admin, logar):
    """Esconder o botão não basta: a rota tem que recusar POST direto."""
    linha_of, _ = _linhas(db, admin)
    conta = _conta(db)
    logar(conta)

    resposta = client.post(f"/oficiais/linha/{linha_of.id}/reivindicar")

    assert resposta.status_code == 403
    assert db.session.get(ResultadoLinha, linha_of.id).user_id is None
    assert db.session.get(User, conta.id).nome_oficial is None


def test_post_direto_no_sou_eu_do_ranking_da_403(client, db, admin, logar):
    _, linha_turma = _linhas(db, admin)
    conta = _conta(db)
    logar(conta)

    resposta = client.post(f"/simulados/turma/linha/{linha_turma.id}/reivindicar")

    assert resposta.status_code == 403
    assert db.session.get(SimuladoTurmaLinha, linha_turma.id).user_id is None


def test_nem_o_admin_usa_o_sou_eu(client, db, admin, logar):
    """A porta fecha para todo mundo: o caminho do admin é /admin/convites."""
    linha_of, _ = _linhas(db, admin)
    logar(admin)

    assert client.post(f"/oficiais/linha/{linha_of.id}/reivindicar").status_code == 403


def test_botao_sumiu_das_telas(client, db, admin, logar):
    _linhas(db, admin)
    logar(admin)

    for rota in ("/oficiais/1", "/simulados/turma/1"):
        corpo = client.get(rota).get_data(as_text=True)
        assert "sou eu" not in corpo.lower(), rota
        assert "reivindicar" not in corpo, rota


# --------------------------------------------------------------------------
# O campo do perfil saiu — e a conta sem aluno é orientada, não deixada no vazio
# --------------------------------------------------------------------------


def test_perfil_nao_tem_mais_o_campo_de_nome(client, db, admin, logar):
    logar(admin)

    corpo = client.get("/perfil").get_data(as_text=True)

    assert 'name="nome_oficial"' not in corpo


def test_post_de_nome_oficial_nao_grava_nada(client, db, logar):
    """Formulário antigo, aba velha, ou POST à mão: nada pode passar."""
    conta = _conta(db)
    logar(conta)

    client.post("/perfil", data={"nome_oficial": "ALUNO NOVATA UM"})

    assert db.session.get(User, conta.id).nome_oficial is None


def test_conta_sem_aluno_recebe_instrucao_e_nao_erro(client, db, admin, logar):
    """A condição da `arthurz`: liberada, sem aluno, sem dado nenhum."""
    _linhas(db, admin)
    conta = _conta(db, "arthurz")
    logar(conta)

    for rota in ("/", "/perfil", "/oficiais/", "/simulados/turma/", "/evolucao"):
        resposta = client.get(rota)
        assert resposta.status_code == 200, f"{rota} -> {resposta.status_code}"
        corpo = resposta.get_data(as_text=True)
        assert "Traceback" not in corpo
        assert "Erro inesperado" not in corpo

    perfil = client.get("/perfil").get_data(as_text=True)
    assert "ainda não está ligada a um aluno" in perfil
    assert "admin" in perfil.lower(), "tem que dizer o que fazer"


def test_perfil_de_conta_vinculada_diz_a_quem(client, db, admin, logar):
    aluno = _aluno(db, "ISABEL NUNES ROCHA")
    conta = _conta(db)
    vincular_a_mao(aluno, conta)
    db.session.commit()
    logar(conta)

    corpo = client.get("/perfil").get_data(as_text=True)

    assert "ISABEL NUNES ROCHA" in corpo


# --------------------------------------------------------------------------
# A evolução no início é um LINK, não a página embutida
# --------------------------------------------------------------------------


def _com_simulado(db, usuario):
    """O card de Evolução só existe quando há simulado registrado."""
    from datetime import date, timedelta

    from app.models import Concurso, Simulado

    c = Concurso(nome="ITA - 1ª Fase", data_prova=date.today() + timedelta(days=90),
                 created_by=usuario.id)
    db.session.add(c)
    db.session.commit()
    db.session.add(Simulado(user_id=usuario.id, concurso_id=c.id,
                            data_simulado=date.today(), nota_geral=50.0,
                            nota_automatica=True))
    db.session.commit()


def test_inicio_leva_a_evolucao_completa(client, db, admin, logar):
    _com_simulado(db, admin)
    logar(admin)

    corpo = client.get("/").get_data(as_text=True)

    assert "/evolucao" in corpo
    assert "Ver evolução completa" in corpo


def test_inicio_nao_ficou_mais_pesado(client, db, admin, logar):
    """Nada de embutir a página: os gráficos da evolução não podem vir junto."""
    _com_simulado(db, admin)
    logar(admin)

    corpo = client.get("/").get_data(as_text=True)

    assert "chart-percentil" not in corpo, "gráfico da evolução vazou para o início"
    assert "chart-materias" not in corpo
