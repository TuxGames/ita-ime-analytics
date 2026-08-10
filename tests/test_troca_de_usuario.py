"""Trocar de usuário com a fixture `logar`, sem passar pelo POST /login.

Contexto (para ninguém investigar isso de novo): durante os testes apareceu um
403 grudento — logar como A, fazer uma requisição, logar como B, e as rotas
seguirem devolvendo 403 com a identidade de A, inclusive em rotas antigas como
`/admin/turmas`.

Por este caminho a causa é do fixture, não do app: o fixture `app` segura um
`app_context()` pelo teste inteiro, o Flask reaproveita esse app context em cada
requisição, e o `g` — onde o Flask-Login cacheia `_login_user` — sobrevive de uma
requisição para a outra. A segunda requisição continuava com o usuário da
primeira mesmo com a sessão já apontando para o outro. Está explicado e
neutralizado em `tests/conftest.py` (`_descartar_usuario_cacheado`); se alguém
mexer lá, este teste quebra.

Verificado contra HTTP real (`requests.Session()` + servidor local, banco
descartável): a troca de conta com logout no meio sempre funcionou. O caminho
pelo POST /login está coberto em `tests/test_troca_de_conta.py`.
"""


def test_troca_de_usuario_no_mesmo_client(client, admin, usuario, logar):
    """Cada requisição enxerga a sessão atual, não a da requisição anterior."""
    logar(usuario)
    assert client.get("/admin/turmas").status_code == 403  # alice não é admin

    logar(admin)
    assert client.get("/admin/turmas").status_code == 200

    logar(usuario)
    assert client.get("/admin/turmas").status_code == 403
