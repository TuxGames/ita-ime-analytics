from functools import wraps

from flask import abort, render_template
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


def exige_convite(f):
    """Só quem resgatou código vê LISTA DE GENTE (ranking da turma, listões).

    O código deixou de ser catraca de acesso e virou credencial de
    VISIBILIDADE. A preocupação que originou tudo nunca foi "estranho usando o
    site" — foi "estranho vendo nome e nota dos alunos". Então treino, estudos,
    simulados próprios e evolução própria não pedem código; o que expõe o nome
    de outra pessoa, pede.

    Não é 403 seco: quem não tem código precisa entender que ele existe e que
    vem do admin, senão a tela vira um beco. `convite_ok` é o que libera —
    NÃO ter aluno não bloqueia nada, senão a conta coringa (o coordenador)
    perderia justamente o que ela existe para ver.
    """

    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.convite_ok:
            return render_template("precisa_de_codigo.html"), 403
        return f(*args, **kwargs)

    return wrapper
