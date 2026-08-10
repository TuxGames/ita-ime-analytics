from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError

import re

from ..extensions import bcrypt, db, limiter
from ..forms import ChangePasswordForm, LoginForm, RegisterForm
from ..models import User

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")

auth_bp = Blueprint("auth", __name__)

# Hash de referência para manter o tempo de resposta uniforme quando o username
# não existe (evita enumeração de usuário por timing). Gerado sob demanda porque
# o bcrypt precisa de app context para ler o cost factor.
_dummy_hash = None


def _burn_bcrypt_time(password: str) -> None:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = bcrypt.generate_password_hash("senha-inexistente-para-timing").decode(
            "utf-8"
        )
    bcrypt.check_password_hash(_dummy_hash, password)


def _safe_next_url(raw_next: str | None) -> str:
    """Só aceita caminho relativo interno — bloqueia open redirect."""
    if raw_next:
        parts = urlsplit(raw_next)
        if not parts.netloc and not parts.scheme and raw_next.startswith("/"):
            return raw_next
    return url_for("main.dashboard")


@auth_bp.before_app_request
def force_password_change():
    """Usuário com senha temporária só acessa a troca de senha e o logout."""
    if current_user.is_authenticated and current_user.must_change_password:
        allowed = {"auth.change_password", "auth.logout", "static"}
        if request.endpoint not in allowed:
            return redirect(url_for("auth.change_password"))


@auth_bp.app_errorhandler(CSRFError)
def csrf_invalido(erro):
    """No /login de quem já tem sessão ativa, o CSRF vencido virava um 400 seco.

    Era a outra metade do mesmo bug: como o GET /login redirecionava para o
    dashboard, o token nunca chegava a ser emitido, e o POST vindo de uma aba
    antiga morria em 400 sem dizer o motivo. Agora esse caso cai na mesma tela
    de aviso do login, que explica quem está logado. Qualquer outro CSRF
    inválido segue com o 400 padrão de sempre.
    """
    if current_user.is_authenticated and request.endpoint == "auth.login":
        return render_template("auth/login.html", form=None, ja_logado=True)
    return erro.get_response()


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit(
    "5 per 15 minutes",
    methods=["POST"],
    error_message="Muitas tentativas de login. Tente novamente em 15 minutos.",
)
def login():
    # Trocar de conta exige logout explícito. O que esta view NÃO faz mais é o
    # redirect calado para o dashboard: quem chegava aqui com sessão ativa era
    # jogado no dashboard do usuário anterior sem nenhum aviso, achando que
    # tinha entrado na própria conta. Daí o "403 misterioso" nas rotas de admin
    # — era a autorização do usuário anterior funcionando certo.
    if current_user.is_authenticated:
        return render_template("auth/login.html", form=None, ja_logado=True)

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(username=form.username.data))
        if user is not None and user.check_password(form.password.data):
            raw_next = request.args.get("next")
            session.clear()  # descarta sessão pré-login (anti session fixation)
            login_user(user)
            session.permanent = True
            current_app.logger.info(
                "Login OK: usuario=%s ip=%s", user.username, request.remote_addr
            )
            if user.must_change_password:
                return redirect(url_for("auth.change_password"))
            return redirect(_safe_next_url(raw_next))

        if user is None:
            _burn_bcrypt_time(form.password.data)
        # Log sem a senha; mensagem genérica não revela se o usuário existe
        current_app.logger.warning(
            "Login FALHOU: usuario=%r ip=%s", form.username.data, request.remote_addr
        )
        flash("Usuário ou senha inválidos.", "error")

    return render_template("auth/login.html", form=form, ja_logado=False)


@auth_bp.route("/registrar", methods=["GET", "POST"])
@limiter.limit(
    "5 per hour",
    methods=["POST"],
    error_message="Muitos cadastros a partir deste IP. Tente novamente mais tarde.",
)
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        # Reforço server-side do formato (defense-in-depth além do validator do form)
        if not _USERNAME_RE.match(username):
            form.username.errors.append("Usuário inválido.")
        elif db.session.scalar(db.select(User).filter_by(username=username)):
            # Em cadastro aberto, informar que o nome está em uso é inevitável.
            form.username.errors.append("Esse usuário já existe. Escolha outro.")
        else:
            user = User(username=username, is_admin=False, must_change_password=False)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            session.clear()  # anti session fixation
            login_user(user)
            session.permanent = True
            current_app.logger.info(
                "Cadastro novo: usuario=%s ip=%s", username, request.remote_addr
            )
            flash("Conta criada! Bem-vindo(a).", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("auth/registrar.html", form=form)


@auth_bp.route("/trocar-senha", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def change_password():
    form = ChangePasswordForm()
    forced = current_user.must_change_password

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            current_app.logger.warning(
                "Troca de senha FALHOU (senha atual errada): usuario=%s ip=%s",
                current_user.username,
                request.remote_addr,
            )
            flash("Senha atual incorreta.", "error")
        else:
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()
            current_app.logger.info(
                "Senha trocada: usuario=%s ip=%s", current_user.username, request.remote_addr
            )
            flash("Senha atualizada com sucesso.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("auth/trocar_senha.html", form=form, forced=forced)


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Você saiu da conta.", "info")
    return redirect(url_for("auth.login"))
