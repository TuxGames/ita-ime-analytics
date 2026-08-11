"""Renomear o grupo — só o dono, mesma validação da criação."""

from app.models import Grupo, GrupoMembro, utcnow

SENHA = "senha-de-teste-123"


def _grupo_com(db, dono, *membros):
    grupo = Grupo(nome="Nome Antigo", criado_por=dono.id)
    db.session.add(grupo)
    db.session.flush()
    for u in (dono, *membros):
        db.session.add(
            GrupoMembro(
                grupo_id=grupo.id, user_id=u.id, status="ativo",
                convidado_em=utcnow(), respondido_em=utcnow(),
            )
        )
    db.session.commit()
    return grupo


def test_dono_renomeia(client, db, admin, logar):
    grupo = _grupo_com(db, admin)
    logar(admin)

    resposta = client.post(f"/grupos/{grupo.id}/editar", data={"nome": "Time de Física"})

    assert resposta.status_code == 302
    assert db.session.get(Grupo, grupo.id).nome == "Time de Física"


def test_membro_que_nao_e_dono_leva_403(client, db, admin, criar_usuario, logar):
    bob = criar_usuario("bob")
    grupo = _grupo_com(db, admin, bob)
    logar(bob)

    assert client.get(f"/grupos/{grupo.id}/editar").status_code == 403
    assert client.post(f"/grupos/{grupo.id}/editar", data={"nome": "Meu agora"}).status_code == 403
    assert db.session.get(Grupo, grupo.id).nome == "Nome Antigo"


def test_estranho_leva_404(client, db, admin, criar_usuario, logar):
    """Quem não tem vínculo nenhum não descobre nem que o grupo existe."""
    grupo = _grupo_com(db, admin)
    logar(criar_usuario("carol"))

    assert client.get(f"/grupos/{grupo.id}/editar").status_code == 404


def test_nome_vazio_nao_passa(client, db, admin, logar):
    grupo = _grupo_com(db, admin)
    logar(admin)

    resposta = client.post(f"/grupos/{grupo.id}/editar", data={"nome": "   "})

    assert resposta.status_code == 200  # volta com erro no formulário
    assert db.session.get(Grupo, grupo.id).nome == "Nome Antigo"


def test_nome_longo_demais_nao_passa(client, db, admin, logar):
    """Mesmo limite de 60 da criação — o form é o mesmo."""
    grupo = _grupo_com(db, admin)
    logar(admin)

    resposta = client.post(f"/grupos/{grupo.id}/editar", data={"nome": "x" * 61})

    assert resposta.status_code == 200
    assert db.session.get(Grupo, grupo.id).nome == "Nome Antigo"


def test_espacos_das_pontas_somem(client, db, admin, logar):
    grupo = _grupo_com(db, admin)
    logar(admin)

    client.post(f"/grupos/{grupo.id}/editar", data={"nome": "  Time de Física  "})

    assert db.session.get(Grupo, grupo.id).nome == "Time de Física"


def test_tela_do_grupo_oferece_editar_so_para_o_dono(client, db, admin, criar_usuario, logar):
    bob = criar_usuario("bob")
    grupo = _grupo_com(db, admin, bob)

    logar(admin)
    assert f"/grupos/{grupo.id}/editar" in client.get(f"/grupos/{grupo.id}").get_data(as_text=True)

    logar(bob)
    assert f"/grupos/{grupo.id}/editar" not in client.get(f"/grupos/{grupo.id}").get_data(as_text=True)
