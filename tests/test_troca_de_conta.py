"""Trocar de conta no mesmo cliente.

Contexto: durante os testes apareceu um 403 teimoso — logar como A, fazer uma
requisição, logar como B, e as rotas seguirem devolvendo 403, inclusive em
rotas antigas como /admin/turmas. A investigação (reproduzida também em HTTP
real, com requests.Session, não só no test_client) achou DUAS coisas:

1. No test_client, o `g` vazava identidade entre requisições — artefato do
   fixture, corrigido em tests/conftest.py. Ver tests/test_troca_de_usuario.py.

2. Em produção, `/login` com sessão ativa redirecionava calado para o
   dashboard. A sessão continuava a do usuário anterior e o 403 era a
   autorização dele funcionando certo. Quem tentava entrar não recebia aviso
   nenhum e achava que tinha entrado na própria conta.

A decisão foi manter a exigência de logout explícito para trocar de conta — o
que mudou é que agora isso é dito na tela, em vez de acontecer em silêncio.
Estes testes fixam esse contrato.
"""

import pytest

from app import create_app
from app.extensions import db as _db
from app.extensions import login_manager
from app.models import User

from .conftest import ConfigTeste

SENHA = "senha-de-teste-123"


def _login(client, nome, senha=SENHA):
    return client.post(
        "/login", data={"username": nome, "password": senha}, follow_redirects=False
    )


def _id_na_sessao(client):
    with client.session_transaction() as sessao:
        return sessao.get("_user_id")


def test_login_com_sessao_ativa_nao_troca_de_conta(client, admin, usuario):
    """Sem logout no meio: era exatamente o caso que produzia o 403."""
    _login(client, usuario.username)
    assert _id_na_sessao(client) == str(usuario.id)
    assert client.get("/admin/turmas").status_code == 403  # alice não é admin

    resposta = _login(client, admin.username)

    # Não autentica, mas também não redireciona calado: explica a situação.
    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Você já está logado" in corpo
    assert usuario.username in corpo  # diz de quem é a sessão

    # A sessão de quem já estava logado continua intacta.
    assert _id_na_sessao(client) == str(usuario.id)
    assert client.get("/admin/turmas").status_code == 403


def test_get_login_com_sessao_ativa_mostra_o_aviso(client, usuario):
    """Antes redirecionava para o dashboard sem dizer nada — o silêncio era o bug."""
    resposta = client.get("/login")
    assert "Você já está logado" not in resposta.get_data(as_text=True)

    _login(client, usuario.username)
    resposta = client.get("/login")

    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Você já está logado" in corpo
    assert usuario.username in corpo
    assert "/logout" in corpo  # botão de sair bem à mão
    assert "name=\"username\"" not in corpo  # sem formulário de login para confundir


def test_sair_pelo_aviso_leva_a_tela_de_login_limpa(client, admin, usuario):
    """O caminho que a tela oferece precisa funcionar de ponta a ponta."""
    _login(client, usuario.username)

    client.post("/logout")
    resposta = client.get("/login")

    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Você já está logado" not in corpo
    assert "name=\"username\"" in corpo  # formulário de volta

    _login(client, admin.username)
    assert _id_na_sessao(client) == str(admin.id)
    assert client.get("/admin/turmas").status_code == 200


def test_login_com_senha_errada_nao_derruba_a_sessao_atual(client, admin, usuario):
    """Tentativa falha de login não pode deslogar quem já estava."""
    _login(client, admin.username)

    _login(client, usuario.username, senha="senha-errada")

    assert _id_na_sessao(client) == str(admin.id)
    assert client.get("/admin/turmas").status_code == 200


@pytest.mark.parametrize("protecao", ["strong", "basic", None])
def test_troca_de_conta_independe_da_protecao_de_sessao(protecao, client, admin, usuario):
    """A suspeita inicial era o session_protection="strong" do Flask-Login. Não
    era: com "strong" ligado (o valor de produção, ver app/__init__.py) o ciclo
    logout → login troca de conta normalmente. A conftest desliga a proteção só
    porque a fixture `logar` forja a sessão na mão, sem o `_id` que o modo
    "strong" exige."""
    anterior = login_manager.session_protection
    login_manager.session_protection = protecao
    try:
        _login(client, usuario.username)
        client.get("/admin/turmas")
        client.post("/logout")

        _login(client, admin.username)

        assert _id_na_sessao(client) == str(admin.id)
        assert client.get("/admin/turmas").status_code == 200
    finally:
        login_manager.session_protection = anterior


class ConfigComCsrf(ConfigTeste):
    """A suíte roda com CSRF desligado; este caso precisa dele ligado."""

    WTF_CSRF_ENABLED = True


def test_post_login_com_sessao_ativa_nao_morre_em_400_de_csrf():
    """A outra metade do silêncio.

    Como o GET /login redirecionava, o token nunca era emitido: o POST vindo de
    uma aba antiga morria num 400 seco, sem dizer que já havia sessão ativa.
    Agora esse caso cai na mesma tela de aviso.

    Monta um app próprio (sem app_context externo, como em produção) porque a
    fixture da suíte desliga o CSRF.
    """
    protecao_anterior = login_manager.session_protection
    aplicativo = create_app(ConfigComCsrf)
    login_manager.session_protection = None
    try:
        with aplicativo.app_context():
            _db.create_all()
            alice = User(username="alice", is_admin=False, must_change_password=False)
            alice.set_password(SENHA)
            _db.session.add(alice)
            _db.session.commit()
            id_alice = str(alice.id)

        cliente = aplicativo.test_client()
        with cliente.session_transaction() as sessao:
            sessao["_user_id"] = id_alice
            sessao["_fresh"] = True

        # Sem csrf_token nenhum, que é o que uma aba velha manda.
        resposta = cliente.post("/login", data={"username": "admin", "password": SENHA})

        assert resposta.status_code == 200, "deveria explicar, não devolver 400"
        assert "Você já está logado" in resposta.get_data(as_text=True)

        with cliente.session_transaction() as sessao:
            assert sessao.get("_user_id") == id_alice  # sessão intacta

        with aplicativo.app_context():
            _db.session.remove()
            _db.drop_all()
    finally:
        login_manager.session_protection = protecao_anterior


def test_csrf_invalido_fora_do_login_continua_400():
    """O tratamento acima é cirúrgico: não pode afrouxar o CSRF do resto do app."""
    protecao_anterior = login_manager.session_protection
    aplicativo = create_app(ConfigComCsrf)
    login_manager.session_protection = None
    try:
        with aplicativo.app_context():
            _db.create_all()
            alice = User(username="alice", is_admin=False, must_change_password=False)
            alice.set_password(SENHA)
            _db.session.add(alice)
            _db.session.commit()
            id_alice = str(alice.id)

        cliente = aplicativo.test_client()
        with cliente.session_transaction() as sessao:
            sessao["_user_id"] = id_alice
            sessao["_fresh"] = True

        assert cliente.post("/logout").status_code == 400

        with aplicativo.app_context():
            _db.session.remove()
            _db.drop_all()
    finally:
        login_manager.session_protection = protecao_anterior
