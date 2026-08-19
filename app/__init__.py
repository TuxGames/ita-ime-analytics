import os

from flask import Flask, render_template

from config import Config
from .extensions import bcrypt, csrf, db, limiter, login_manager, migrate


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY não definido. Crie um .env com "
            'SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")'
        )

    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para acessar essa página."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"

    from . import models  # noqa: F401  (registra modelos para o Flask-Migrate)

    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .simulados.routes import simulados_bp
    from .concursos.routes import concursos_bp
    from .estudos.routes import estudos_bp
    from .oficiais.routes import oficiais_bp
    from .admin.routes import admin_bp
    from .grupos.routes import grupos_bp
    from .professor.routes import professor_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(simulados_bp, url_prefix="/simulados")
    app.register_blueprint(concursos_bp, url_prefix="/concursos")
    app.register_blueprint(estudos_bp, url_prefix="/estudos")
    app.register_blueprint(oficiais_bp, url_prefix="/oficiais")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(grupos_bp, url_prefix="/grupos")
    app.register_blueprint(professor_bp, url_prefix="/professor")

    from .grouping import compor_titulo, rotulo_curto

    app.jinja_env.filters["rotulo_curto"] = rotulo_curto
    app.jinja_env.globals["titulo_simulado"] = compor_titulo

    from .media_final import media_final_da_linha

    app.jinja_env.globals["media_final_da_linha"] = media_final_da_linha

    from .monograma import indice_de_cor, iniciais

    app.jinja_env.globals["iniciais_do_nome"] = iniciais
    app.jinja_env.globals["cor_do_nome"] = indice_de_cor

    from .versao import VERSAO

    app.jinja_env.globals["VERSAO"] = VERSAO

    @app.context_processor
    def papel_no_template():
        """`so_professor`: quem tem o papel de leitura e NÃO é admin.

        Context processor, e não `{% set %}` no base.html, porque um `set` no
        template pai não chega aos blocos dos filhos — e a home é um filho.
        Isto governa só o que a tela OFERECE; quem recusa de verdade são os
        decoradores em app/decorators.py.
        """
        from flask_login import current_user

        return {
            "so_professor": (
                current_user.is_authenticated
                and current_user.is_professor
                and not current_user.is_admin
            )
        }

    def timestamp_br(valor):
        """mtime (float) -> "13/08/2026 18:42". None vira travessão."""
        if not valor:
            return "—"
        from datetime import datetime

        return datetime.fromtimestamp(valor).strftime("%d/%m/%Y %H:%M")

    app.jinja_env.filters["timestamp_br"] = timestamp_br

    from .security import register_security_headers

    register_security_headers(app)

    from .cli import register_cli

    register_cli(app)

    from .conferencia import registrar_cli

    registrar_cli(app)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template("errors/429.html", description=e.description), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    return app
