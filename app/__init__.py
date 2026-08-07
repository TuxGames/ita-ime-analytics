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

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(simulados_bp, url_prefix="/simulados")
    app.register_blueprint(concursos_bp, url_prefix="/concursos")
    app.register_blueprint(estudos_bp, url_prefix="/estudos")
    app.register_blueprint(oficiais_bp, url_prefix="/oficiais")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .grouping import compor_titulo, rotulo_curto

    app.jinja_env.filters["rotulo_curto"] = rotulo_curto
    app.jinja_env.globals["titulo_simulado"] = compor_titulo

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
