"""Fixtures da suíte.

O app roda em SQLite na memória, com CSRF, rate limit e proteção de sessão
desligados: são comportamentos reais (e testados à parte, no HTTP), mas aqui só
atrapalhariam a checagem da lógica de import e ranking.
"""

import os
import sys
from datetime import date

import pytest
from flask import g

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.extensions import login_manager  # noqa: E402
from app.models import User  # noqa: E402
from config import Config  # noqa: E402


class ConfigTeste(Config):
    SECRET_KEY = "chave-fixa-de-teste-nao-usar-em-producao"
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # em memória
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    TESTING = True
    # bcrypt no custo de produção (13) deixaria a suíte lenta demais.
    BCRYPT_LOG_ROUNDS = 4


@pytest.fixture
def app():
    aplicativo = create_app(ConfigTeste)
    # "strong" invalida a sessão forjada pelo test_client.
    login_manager.session_protection = None

    def _descartar_usuario_cacheado():
        """Faz o `g` se comportar como em produção: um por requisição.

        Em produção cada requisição empurra um app context novo, e com ele um
        `g` novo. Aqui o `app_context()` abaixo dura o teste inteiro, e o
        RequestContext.push() do Flask REAPROVEITA o app context já empilhado
        (flask/ctx.py) — então o `g` sobrevive de uma requisição para a outra.
        O Flask-Login guarda o usuário resolvido em `g._login_user` e só
        recarrega da sessão quando a chave não existe (flask_login/utils.py:369).
        Resultado: trocar de usuário no meio de um teste não tinha efeito — a
        segunda requisição continuava com a identidade da primeira, e rotas de
        admin devolviam 403 com a sessão apontando para o admin. Isso é artefato
        do fixture, não do app: no HTTP real a troca de conta funciona.
        """
        g.pop("_login_user", None)

    # Precisa rodar ANTES do force_password_change (registrado pelo blueprint de
    # auth dentro do create_app), que também lê current_user.
    aplicativo.before_request_funcs.setdefault(None, []).insert(
        0, _descartar_usuario_cacheado
    )

    with aplicativo.app_context():
        _db.create_all()
        yield aplicativo
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


def _criar_usuario(nome, admin=False, nome_oficial=None):
    usuario = User(
        username=nome,
        is_admin=admin,
        nome_oficial=nome_oficial,
        # Sem isso o app manda todo mundo para /trocar-senha antes de qualquer
        # rota, e os testes de rota nunca chegam no que querem checar.
        must_change_password=False,
        # Mesma ideia para a trava de convite: estas fixtures representam conta
        # legítima e já liberada (como as que a migration libera em produção).
        # A trava em si é testada em tests/test_convites.py, que cria contas
        # trancadas de propósito.
        convite_ok=True,
    )
    usuario.set_password("senha-de-teste-123")
    _db.session.add(usuario)
    _db.session.commit()
    return usuario


@pytest.fixture
def admin(db):
    return _criar_usuario("admin", admin=True)


@pytest.fixture
def usuario(db):
    return _criar_usuario("alice")


@pytest.fixture
def criar_usuario(db):
    """Para quando o teste precisa de mais gente do que as fixtures acima."""
    return _criar_usuario


@pytest.fixture
def logar(client):
    """Autentica o test_client como o usuário dado, sem passar pelo /login."""

    def _logar(usuario):
        with client.session_transaction() as sessao:
            sessao["_user_id"] = str(usuario.id)
            sessao["_fresh"] = True

    return _logar


# ---------------------------------------------------------------------------
# Fábricas de payload — os testes montam JSON válido sem repetir boilerplate.
# ---------------------------------------------------------------------------


def payload_oficial(turma="novata", concurso="AFA 2027", **ajustes):
    dados = {
        "tipo": "oficial",
        "concurso": concurso,
        "turma": turma,
        "fonte": "GGE",
        "data": None,
        "escala": 10,
        "materias": ["MAT", "FIS"],
        "metrica": "MP",
        "resultados": [
            {
                "nome": f"PESSOA {turma.upper()} UM",
                "status": "classificado",
                "classificacao": 100 if turma == "novata" else 200,
                "metrica": 7.0,
                "notas": {"MAT": 7.0, "FIS": 7.0},
            },
            {
                "nome": f"PESSOA {turma.upper()} DOIS",
                "status": "sem_aproveitamento",
                "classificacao": None,
                "metrica": 4.0,
                "notas": {"MAT": 4.0, "FIS": 4.0},
            },
            {"nome": f"PESSOA {turma.upper()} TRES", "status": "nao_encontrado"},
        ],
    }
    dados.update(ajustes)
    return dados


def payload_simulado(turma="novata", rotulo="S3", banca="ITA", **ajustes):
    dados = {
        "tipo": "simulado",
        "fase": "objetiva",
        "banca": banca,
        "rotulo": rotulo,
        "data": "2026-04-11",
        "turma": turma,
        "fonte": "GGE",
        "materias": ["MAT", "FIS", "QUIM", "ING"],
        "materias_media": ["MAT", "FIS", "QUIM"],
        "questoes": None,
        "resultados": [
            {
                "nome": f"ALUNO {turma.upper()} UM",
                "serie": "3º ANO",
                "status": "presente",
                "acertos": {"MAT": 9, "FIS": 5, "QUIM": 5, "ING": 11},
                "media_oficial": 5.28,
                "geral_oficial": 30,
            },
            {
                "nome": f"ALUNO {turma.upper()} DOIS",
                "serie": "2º ANO",
                "status": "presente",
                "acertos": {"MAT": 6, "FIS": 6, "QUIM": 6, "ING": 6},
                "media_oficial": 5.00,
                "geral_oficial": 24,
            },
            {
                "nome": f"ALUNO {turma.upper()} TRES",
                "serie": "CURSO",
                "status": "ausente",
            },
        ],
    }
    dados.update(ajustes)
    return dados


@pytest.fixture
def oficial():
    return payload_oficial


@pytest.fixture
def simulado():
    return payload_simulado


@pytest.fixture
def hoje():
    return date.today()
