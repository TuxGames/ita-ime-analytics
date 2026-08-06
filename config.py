"""Configuração central do app. Tudo que é segredo vem de variável de ambiente."""
import os
from datetime import timedelta


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # Definido no .env (gerado com: python -c "import secrets; print(secrets.token_hex(32))")
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Caminho relativo resolve para a pasta instance/ (fora de qualquer pasta servida)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///itaime.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessão: HttpOnly + SameSite sempre; Secure por padrão (desligar só em dev local via .env)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_HOURS", "12")))

    # bcrypt com cost factor 13 (checklist exige >= 12)
    BCRYPT_LOG_ROUNDS = 13

    # Token CSRF válido pela duração da sessão (evita erro em form deixado aberto no celular)
    WTF_CSRF_TIME_LIMIT = None

    # Rate limiting em memória: suficiente para 1 worker (caso do PythonAnywhere)
    RATELIMIT_STORAGE_URI = "memory://"

    # Atrás do proxy do PythonAnywhere, ativa ProxyFix para request.remote_addr real
    BEHIND_PROXY = _env_bool("BEHIND_PROXY", False)
