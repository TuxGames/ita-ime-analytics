"""Código de convite: quem entra no app e a que aluno a conta pertence.

O cadastro é aberto, mas conta nova nasce trancada — o dado protegido é nome
completo, série, turma e nota de 73 alunos. Cada critério de aceite tem teste.
"""

import json

import pytest

from app.convites import (
    ErroConvite,
    convite_coringa_do_usuario,
    coringas,
    emitir_coringa,
    alunos_sem_conta,
    contas_sem_aluno,
    convite_ativo,
    desvincular,
    emitir,
    gerar_codigo,
    normalizar_codigo,
    resgatar,
    revogar,
)
from app.models import Aluno, ConviteAluno, User
from app.oficiais_import import aplicar, parse
from app.vinculo import revincular

from .conftest import payload_oficial

SENHA = "senha-de-teste-123"


def _aluno(db, nome="MARIA DE SOUZA LIMA"):
    from app.models import normalizar_nome

    a = Aluno(nome=nome, nome_norm=normalizar_nome(nome), turma="novata")
    db.session.add(a)
    db.session.commit()
    return a


def _conta_nova(db, username="novata1"):
    """Conta como o /registrar cria: trancada."""
    u = User(username=username, is_admin=False, must_change_password=False)
    u.set_password(SENHA)
    db.session.add(u)
    db.session.commit()
    return u


# --------------------------------------------------------------------------
# O código em si
# --------------------------------------------------------------------------


def test_codigo_nao_tem_caractere_ambiguo(app, db):
    for _ in range(50):
        codigo = gerar_codigo()
        assert len(codigo) == ConviteAluno.TAMANHO
        assert not set(codigo) & set("O0I1L"), codigo


def test_codigo_e_unico(app, db, admin):
    aluno1, aluno2 = _aluno(db, "ANA UM"), _aluno(db, "ANA DOIS")
    c1 = emitir(aluno1, admin.id)
    c2 = emitir(aluno2, admin.id)
    db.session.commit()

    assert c1.codigo != c2.codigo


@pytest.mark.parametrize(
    "digitado", ["abcd2345", "ABCD-2345", "abcd 2345", "  AbCd-2345  "]
)
def test_normalizacao_aceita_o_que_a_pessoa_digita(digitado):
    assert normalizar_codigo(digitado) == "ABCD2345"


def test_emitir_reaproveita_codigo_nao_usado(app, db, admin):
    aluno = _aluno(db)
    primeiro = emitir(aluno, admin.id)
    db.session.commit()
    segundo = emitir(aluno, admin.id)
    db.session.commit()

    assert primeiro.id == segundo.id, "não pode acumular códigos válidos para a mesma pessoa"


# --------------------------------------------------------------------------
# Aceite 1: conta nova sem código não acessa nada
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rota", ["/", "/simulados/", "/estudos/", "/perfil", "/oficiais/", "/grupos/"]
)
def test_conta_sem_codigo_nao_acessa_rota_nenhuma(rota, client, db, logar):
    nova = _conta_nova(db)
    logar(nova)

    resposta = client.get(rota)

    assert resposta.status_code == 302
    assert "/convite" in resposta.headers["Location"]


def test_conta_sem_codigo_alcanca_a_tela_do_codigo_e_o_logout(client, db, logar):
    nova = _conta_nova(db)
    logar(nova)

    assert client.get("/convite").status_code == 200
    assert client.post("/logout").status_code == 302


def test_conta_sem_codigo_nem_troca_senha(client, db, logar):
    """A trava do convite vem antes da de senha."""
    nova = _conta_nova(db)
    nova.must_change_password = True
    db.session.commit()
    logar(nova)

    resposta = client.get("/trocar-senha")

    assert "/convite" in resposta.headers["Location"]


# --------------------------------------------------------------------------
# Aceite 2 e 3: uso único, e código de outro aluno não vincula errado
# --------------------------------------------------------------------------


def test_resgate_vincula_a_conta_ao_aluno_do_codigo(app, db, admin, client, logar):
    aluno = _aluno(db)
    convite = emitir(aluno, admin.id)
    db.session.commit()
    nova = _conta_nova(db)
    logar(nova)

    resposta = client.post("/convite", data={"codigo": convite.formatado})

    assert resposta.status_code == 302
    assert db.session.get(User, nova.id).convite_ok is True
    assert db.session.get(Aluno, aluno.id).user_id == nova.id
    assert db.session.get(Aluno, aluno.id).vinculo_por_codigo is True


def test_codigo_usado_nao_funciona_de_novo(app, db, admin, client, logar):
    aluno = _aluno(db)
    convite = emitir(aluno, admin.id)
    db.session.commit()
    codigo = convite.codigo

    primeira = _conta_nova(db, "primeira")
    logar(primeira)
    client.post("/convite", data={"codigo": codigo})

    segunda = _conta_nova(db, "segunda")
    logar(segunda)
    resposta = client.post("/convite", data={"codigo": codigo})

    assert resposta.status_code == 200, "volta com erro, não redireciona"
    assert "já foi usado" in resposta.get_data(as_text=True)
    assert db.session.get(User, segunda.id).convite_ok is False


def test_codigo_de_um_aluno_nao_vincula_a_outro(app, db, admin, client, logar):
    ana = _aluno(db, "ANA PAULA CORREA")
    bruno = _aluno(db, "BRUNO ALVES DIAS")
    convite_bruno = emitir(bruno, admin.id)
    db.session.commit()
    nova = _conta_nova(db)
    logar(nova)

    client.post("/convite", data={"codigo": convite_bruno.codigo})

    assert db.session.get(Aluno, bruno.id).user_id == nova.id
    assert db.session.get(Aluno, ana.id).user_id is None


def test_codigo_inexistente_nao_libera(app, db, client, logar):
    nova = _conta_nova(db)
    logar(nova)

    resposta = client.post("/convite", data={"codigo": "ZZZZ9999"})

    assert "não encontrado" in resposta.get_data(as_text=True)
    assert db.session.get(User, nova.id).convite_ok is False


def test_aluno_ja_vinculado_recusa_novo_resgate(app, db, admin):
    aluno = _aluno(db)
    dono = _conta_nova(db, "dono")
    aluno.user_id = dono.id
    db.session.commit()
    convite = emitir(aluno, admin.id)
    db.session.commit()

    outra = _conta_nova(db, "outra")
    with pytest.raises(ErroConvite, match="outra conta"):
        resgatar(convite.codigo, outra)


def test_revogar_so_vale_para_codigo_nao_usado(app, db, admin):
    aluno = _aluno(db)
    convite = emitir(aluno, admin.id)
    db.session.commit()

    assert revogar(convite) is True
    db.session.commit()
    assert convite_ativo(aluno.id) is None

    outro = emitir(aluno, admin.id)
    db.session.commit()
    conta = _conta_nova(db)
    resgatar(outro.codigo, conta)
    db.session.commit()

    assert revogar(outro) is False, "convite usado é registro de como a conta entrou"


# --------------------------------------------------------------------------
# Aceite 4: as contas que já existiam continuam funcionando
# --------------------------------------------------------------------------


def test_conta_ja_liberada_navega_normalmente(client, db, admin, logar):
    """`admin` vem da fixture como conta existente e liberada."""
    admin.convite_ok = True
    db.session.commit()
    logar(admin)

    assert client.get("/").status_code == 200
    assert client.get("/perfil").status_code == 200


def test_quem_ja_tem_convite_nao_ve_a_tela_do_codigo(client, db, admin, logar):
    admin.convite_ok = True
    db.session.commit()
    logar(admin)

    resposta = client.get("/convite")

    assert resposta.status_code == 302
    assert "/convite" not in resposta.headers["Location"]


# --------------------------------------------------------------------------
# Aceite 5: import depois do resgate não desfaz o vínculo
# --------------------------------------------------------------------------


def test_revincular_nao_desfaz_vinculo_por_codigo(app, db, admin):
    """O ponto que não pode falhar: `revincular()` roda após cada import."""
    aluno = _aluno(db, "PESSOA NOVATA UM")
    convite = emitir(aluno, admin.id)
    db.session.commit()
    conta = _conta_nova(db)
    resgatar(convite.codigo, conta)
    db.session.commit()

    # A conta NÃO declara nome_oficial casável — antes, isto zerava o vínculo.
    conta.nome_oficial = "NOME QUE NAO EXISTE EM LISTA NENHUMA"
    db.session.commit()

    revincular()
    db.session.commit()

    assert db.session.get(Aluno, aluno.id).user_id == conta.id


def test_import_completo_nao_desfaz_vinculo_por_codigo(app, db, admin):
    """O caminho real: importar um listão dispara o revincular."""
    aplicar(db, parse(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()

    aluno = db.session.scalar(db.select(Aluno).order_by(Aluno.id))
    convite = emitir(aluno, admin.id)
    db.session.commit()
    conta = _conta_nova(db)
    resgatar(convite.codigo, conta)
    db.session.commit()

    aplicar(db, parse(json.dumps(payload_oficial("veterana"))), admin.id)
    db.session.commit()
    revincular()
    db.session.commit()

    assert db.session.get(Aluno, aluno.id).user_id == conta.id
    assert db.session.get(Aluno, aluno.id).vinculo_por_codigo is True


def test_vinculo_por_nome_continua_valendo_para_quem_nao_tem_codigo(app, db, admin):
    """A inversão não pode matar o casamento por nome de quem não foi reivindicado."""
    aluno = _aluno(db, "CARLOS EDUARDO NUNES")
    conta = _conta_nova(db)
    conta.nome_oficial = "CARLOS EDUARDO NUNES"
    conta.convite_ok = True
    db.session.commit()

    revincular()
    db.session.commit()

    assert db.session.get(Aluno, aluno.id).user_id == conta.id
    assert db.session.get(Aluno, aluno.id).vinculo_por_codigo is False


def test_desvincular_devolve_o_aluno_ao_casamento_por_nome(app, db, admin):
    aluno = _aluno(db, "DANIELA ROCHA SILVA")
    convite = emitir(aluno, admin.id)
    db.session.commit()
    conta = _conta_nova(db)
    resgatar(convite.codigo, conta)
    db.session.commit()

    desvincular(aluno)
    db.session.commit()

    assert aluno.user_id is None
    assert aluno.vinculo_por_codigo is False
    assert db.session.get(User, conta.id).convite_ok is True, "a conta segue liberada"


# --------------------------------------------------------------------------
# A tela de admin
# --------------------------------------------------------------------------


def test_tela_de_convites_e_so_do_admin(client, db, usuario, logar):
    usuario.convite_ok = True
    db.session.commit()
    logar(usuario)

    assert client.get("/admin/convites").status_code == 403


def test_tela_lista_quem_falta_convidar_e_contas_soltas(client, db, admin, logar):
    aluno = _aluno(db, "ELISA MARTINS COSTA")
    admin.convite_ok = True
    db.session.commit()
    logar(admin)

    corpo = client.get("/admin/convites").get_data(as_text=True)

    assert "ELISA MARTINS COSTA" in corpo
    assert "Sem conta e sem código" in corpo
    assert "Contas sem aluno" in corpo
    assert admin.username in corpo


def test_admin_gera_e_a_tela_mostra_o_codigo(client, db, admin, logar):
    aluno = _aluno(db, "FABIO SOUZA RAMOS")
    admin.convite_ok = True
    db.session.commit()
    logar(admin)

    client.post(f"/admin/convites/{aluno.id}/gerar")

    convite = convite_ativo(aluno.id)
    assert convite is not None
    assert convite.formatado in client.get("/admin/convites").get_data(as_text=True)


def test_listas_de_trabalho_do_admin(app, db, admin):
    aluno = _aluno(db, "GABRIEL PINTO LEAL")
    conta = _conta_nova(db)

    assert aluno in alunos_sem_conta()
    assert conta in [i["user"] for i in contas_sem_aluno()]

    convite = emitir(aluno, admin.id)
    db.session.commit()
    resgatar(convite.codigo, conta)
    db.session.commit()

    assert aluno not in alunos_sem_conta()
    assert conta not in [i["user"] for i in contas_sem_aluno()]


# --------------------------------------------------------------------------
# Código coringa: libera a conta SEM vincular a aluno
# --------------------------------------------------------------------------


def test_coringa_libera_sem_vincular(app, db, admin, client, logar):
    coringa = emitir_coringa("coordenador", admin.id)
    db.session.commit()
    aluno = _aluno(db, "HELENA DIAS MOURA")
    nova = _conta_nova(db)
    logar(nova)

    resposta = client.post("/convite", data={"codigo": coringa.formatado})

    assert resposta.status_code == 302
    assert db.session.get(User, nova.id).convite_ok is True, "liberou"
    assert db.session.get(Aluno, aluno.id).user_id is None, "não vinculou ninguém"
    assert db.session.get(User, nova.id).nome_oficial is None, "não herdou nome de aluno"


def test_coringa_e_de_uso_unico(app, db, admin, client, logar):
    coringa = emitir_coringa("professor de física", admin.id)
    db.session.commit()

    primeira = _conta_nova(db, "prof1")
    logar(primeira)
    client.post("/convite", data={"codigo": coringa.codigo})

    segunda = _conta_nova(db, "prof2")
    logar(segunda)
    resposta = client.post("/convite", data={"codigo": coringa.codigo})

    assert "já foi usado" in resposta.get_data(as_text=True)
    assert db.session.get(User, segunda.id).convite_ok is False


def test_coringa_exige_rotulo(app, db, admin):
    with pytest.raises(ErroConvite, match="para que serve"):
        emitir_coringa("   ", admin.id)


def test_coringa_nao_reaproveita_pendente(app, db, admin):
    """Dois convidados sem aluno = dois coringas, cada um com seu rótulo."""
    um = emitir_coringa("coordenador", admin.id)
    dois = emitir_coringa("professor de física", admin.id)
    db.session.commit()

    assert um.codigo != dois.codigo
    assert len(coringas()) == 2


def test_coringa_nao_aparece_como_convite_de_aluno(app, db, admin):
    """`convite_ativo` é do aluno; coringa não pode vazar para lá."""
    aluno = _aluno(db, "IGOR SANTOS PRADO")
    emitir_coringa("coordenador", admin.id)
    db.session.commit()

    assert convite_ativo(aluno.id) is None


def test_conta_coringa_aparece_identificada_na_lista(app, db, admin, client, logar):
    coringa = emitir_coringa("coordenador", admin.id)
    db.session.commit()
    conta = _conta_nova(db, "coord")
    resgatar(coringa.codigo, conta)
    db.session.commit()

    item = next(i for i in contas_sem_aluno() if i["user"].id == conta.id)
    assert item["coringa"] is not None
    assert item["coringa"].rotulo == "coordenador"
    assert convite_coringa_do_usuario(conta.id) is not None

    admin.convite_ok = True
    db.session.commit()
    logar(admin)
    corpo = client.get("/admin/convites").get_data(as_text=True)
    assert "coringa · coordenador" in corpo


def test_conta_sem_coringa_aparece_como_pendencia(app, db, admin, client, logar):
    """As contas que já existiam continuam sendo o que falta acertar."""
    solta = _conta_nova(db, "antiga")
    solta.convite_ok = True
    db.session.commit()

    item = next(i for i in contas_sem_aluno() if i["user"].id == solta.id)
    assert item["coringa"] is None

    admin.convite_ok = True
    db.session.commit()
    logar(admin)
    assert "falta vincular" in client.get("/admin/convites").get_data(as_text=True)


def test_admin_gera_coringa_pela_tela(client, db, admin, logar):
    admin.convite_ok = True
    db.session.commit()
    logar(admin)

    client.post("/admin/convites/coringa", data={"rotulo": "coordenador da turma"})

    lista = coringas()
    assert len(lista) == 1
    assert lista[0].rotulo == "coordenador da turma"
    assert lista[0].tipo == "coringa"
    assert lista[0].aluno_id is None


def test_coringa_sem_rotulo_nao_gera(client, db, admin, logar):
    admin.convite_ok = True
    db.session.commit()
    logar(admin)

    client.post("/admin/convites/coringa", data={"rotulo": ""})

    assert coringas() == []


# --------------------------------------------------------------------------
# As telas aguentam conta sem aluno
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rota",
    ["/", "/simulados/", "/simulados/turma/", "/oficiais/", "/estudos/", "/perfil", "/evolucao"],
)
def test_telas_nao_quebram_para_conta_coringa(rota, client, db, admin, logar):
    """Conta coringa não tem aluno, então não tem linha própria em ranking
    nenhum. As telas têm que aguentar isso sem erro e sem estado de erro."""
    aplicar(db, parse(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()

    coringa = emitir_coringa("coordenador", admin.id)
    db.session.commit()
    conta = _conta_nova(db, "coord")
    resgatar(coringa.codigo, conta)
    db.session.commit()
    logar(conta)

    resposta = client.get(rota)

    assert resposta.status_code == 200, f"{rota} respondeu {resposta.status_code}"
    corpo = resposta.get_data(as_text=True)
    assert "Traceback" not in corpo
    assert "Erro inesperado" not in corpo
