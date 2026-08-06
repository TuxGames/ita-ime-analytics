from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(f):
    """Exige login E is_admin. 403 para usuário autenticado sem permissão."""

    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return wrapper
