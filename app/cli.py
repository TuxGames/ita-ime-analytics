"""Comandos CLI: criação de contas é só por aqui (não há cadastro self-service)."""
import os
import re
import secrets
import sqlite3
from datetime import datetime

import click
from flask import current_app

from .extensions import db
from .models import Concurso, Simulado, User

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _gerar_senha_temporaria() -> str:
    return secrets.token_urlsafe(12)


def _caminho_sqlite(uri: str) -> str | None:
    """Extrai o caminho do arquivo de uma URI sqlite:///... . None se não for
    SQLite em arquivo (ex.: "sqlite://" em memória, ou outro banco)."""
    prefixo = "sqlite:///"
    if not uri.startswith(prefixo):
        return None
    return uri[len(prefixo):] or None


def _fase_base(etapa: str) -> str:
    """'2ª Fase, dia 3' -> '2ª Fase'. 'Dia 1' e '1ª Fase' (sem ', dia') ficam iguais."""
    return etapa.split(", dia")[0].strip() if ", dia" in etapa else etapa


def register_cli(app):
    @app.cli.command("backup")
    @click.option(
        "--para",
        "destino",
        default=None,
        help="Pasta de destino do backup (padrão: instance/backups).",
    )
    def backup(destino):
        """Cópia consistente do banco SQLite, via VACUUM INTO.

        VACUUM INTO (e não cp/shutil.copy) porque copiar o arquivo aberto sob
        escrita concorrente pode pegar o banco no meio de uma transação e
        corromper o backup; VACUUM INTO faz a cópia dentro do próprio SQLite,
        de forma consistente."""
        uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
        caminho_origem = _caminho_sqlite(uri)
        if caminho_origem is None:
            raise click.ClickException(
                "Backup só funciona com banco SQLite em arquivo "
                f"(SQLALCHEMY_DATABASE_URI atual: {uri!r})."
            )
        if not os.path.exists(caminho_origem):
            raise click.ClickException(f"Banco não encontrado em '{caminho_origem}'.")

        pasta = destino or os.path.join(os.path.dirname(caminho_origem) or ".", "backups")
        os.makedirs(pasta, exist_ok=True)
        nome = f"itaime-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        caminho_destino = os.path.join(pasta, nome)

        conexao = sqlite3.connect(caminho_origem)
        try:
            conexao.execute("VACUUM INTO ?", (caminho_destino,))
        finally:
            conexao.close()

        tamanho_kb = os.path.getsize(caminho_destino) / 1024
        click.echo(f"Backup criado: {caminho_destino} ({tamanho_kb:.1f} KB)")

    @app.cli.command("consolidar-fases")
    @click.option("--yes", is_flag=True, help="Aplica de fato (sem isso, só mostra o plano).")
    def consolidar_fases(yes):
        """Junta concursos que diferem só por ', dia N' numa fase única.

        Ex.: 'ITA 2027 - 2ª Fase, dia 1..4' -> 'ITA 2027 - 2ª Fase'. Repontua os
        simulados para a fase, une as matérias e mantém a data mais cedo. Bancas
        como EFOMM/EsPCEx ('Dia 1'/'Dia 2') e '1ª Fase' não têm ', dia' e ficam
        intactas. Sem --yes é só um preview (dry-run)."""
        concursos = db.session.scalars(
            db.select(Concurso).order_by(Concurso.data_prova)
        ).all()

        grupos = {}
        for c in concursos:
            chave = (c.banca, _fase_base(c.etapa))
            grupos.setdefault(chave, []).append(c)

        planos = [(k, v) for k, v in grupos.items() if len(v) > 1]
        if not planos:
            click.echo("Nada a consolidar: nenhuma fase com dias separados.")
            return

        click.echo("Plano de consolidação:")
        for (banca, fase_base), itens in planos:
            alvo_nome = Concurso.compor_nome(banca, fase_base)
            origem = ", ".join(f"'{c.nome}'" for c in itens)
            n_sim = sum(
                db.session.scalar(
                    db.select(db.func.count(Simulado.id)).filter_by(concurso_id=c.id)
                )
                for c in itens
            )
            click.echo(f"  {origem}\n    -> '{alvo_nome}'  ({n_sim} simulado(s) afetado(s))")

        if not yes:
            click.echo("\n(dry-run) Rode de novo com --yes para aplicar.")
            return

        for (banca, fase_base), itens in planos:
            itens.sort(key=lambda c: c.data_prova)
            alvo = itens[0]  # mantém o de data mais cedo
            # a fase passa a cobrir do primeiro ao último dia
            datas = [c.data_prova for c in itens] + [
                c.data_fim for c in itens if c.data_fim
            ]
            alvo.data_prova = min(datas)
            alvo.data_fim = max(datas) if max(datas) > min(datas) else None
            mats = set()
            for c in itens:
                mats.update(c.materias)
            for c in itens[1:]:
                for s in db.session.scalars(
                    db.select(Simulado).filter_by(concurso_id=c.id)
                ).all():
                    s.concurso_id = alvo.id
            alvo.nome = Concurso.compor_nome(banca, fase_base)
            alvo.set_materias(mats)
            db.session.flush()  # aplica o rename antes de remover os outros
            for c in itens[1:]:
                db.session.delete(c)

        db.session.commit()
        click.echo("Consolidação aplicada.")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.option("--admin", is_flag=True, help="Cria o usuário como administrador.")
    def create_user(username, admin):
        """Cria um usuário com senha temporária (troca forçada no primeiro login)."""
        if not USERNAME_RE.match(username):
            raise click.ClickException(
                "Username inválido: use 3-32 caracteres (letras, números, _ . -)."
            )
        if db.session.scalar(db.select(User).filter_by(username=username)):
            raise click.ClickException(f"Usuário '{username}' já existe.")

        temp_password = _gerar_senha_temporaria()
        user = User(username=username, is_admin=admin, must_change_password=True)
        user.set_password(temp_password)
        db.session.add(user)
        db.session.commit()

        papel = "admin" if admin else "usuário"
        click.echo(f"Criado {papel} '{username}'.")
        click.echo(f"Senha temporária: {temp_password}")
        click.echo("O usuário será obrigado a trocar a senha no primeiro login.")

    @app.cli.command("list-users")
    def list_users():
        """Lista todos os usuários (username, admin, nº de simulados)."""
        users = db.session.scalars(db.select(User).order_by(User.username)).all()
        if not users:
            click.echo("Nenhum usuário cadastrado.")
            return
        for u in users:
            n = db.session.scalar(
                db.select(db.func.count(Simulado.id)).filter_by(user_id=u.id)
            )
            papel = "admin" if u.is_admin else "user "
            click.echo(f"  [{papel}] {u.username}  ({n} simulado(s))")

    @app.cli.command("delete-user")
    @click.argument("username")
    @click.option("--yes", is_flag=True, help="Não pedir confirmação.")
    @click.option(
        "--reassign-concursos-to",
        metavar="USERNAME",
        help="Transfere os concursos criados por este usuário para outro admin "
        "(necessário se ele tiver criado concursos, pois são compartilhados).",
    )
    def delete_user(username, yes, reassign_concursos_to):
        """Exclui um usuário e TODOS os simulados dele (com as matérias em cascata).

        Concursos são compartilhados: se o usuário criou algum, a exclusão é
        bloqueada até você reatribuí-los com --reassign-concursos-to <admin>.
        """
        user = db.session.scalar(db.select(User).filter_by(username=username))
        if user is None:
            raise click.ClickException(f"Usuário '{username}' não encontrado.")

        # Não deixa apagar o último admin (senão ninguém mais cria/edita concursos).
        if user.is_admin:
            outros_admins = db.session.scalar(
                db.select(db.func.count(User.id)).filter(
                    User.is_admin.is_(True), User.id != user.id
                )
            )
            if outros_admins == 0:
                raise click.ClickException(
                    f"'{username}' é o único admin. Promova outro usuário a admin "
                    "antes de excluí-lo."
                )

        # Concursos criados por ele (compartilhados) precisam de destino.
        concursos = db.session.scalars(
            db.select(Concurso).filter_by(created_by=user.id)
        ).all()
        if concursos:
            if not reassign_concursos_to:
                nomes = ", ".join(c.nome for c in concursos)
                raise click.ClickException(
                    f"'{username}' criou {len(concursos)} concurso(s) compartilhado(s): "
                    f"{nomes}.\nReatribua-os antes de excluir: "
                    f"--reassign-concursos-to <username_admin>."
                )
            destino = db.session.scalar(
                db.select(User).filter_by(username=reassign_concursos_to)
            )
            if destino is None:
                raise click.ClickException(
                    f"Usuário de destino '{reassign_concursos_to}' não encontrado."
                )
            if destino.id == user.id:
                raise click.ClickException(
                    "O destino dos concursos não pode ser o próprio usuário excluído."
                )
            if not destino.is_admin:
                raise click.ClickException(
                    f"'{reassign_concursos_to}' não é admin; concursos só pertencem a admins."
                )

        n_simulados = db.session.scalar(
            db.select(db.func.count(Simulado.id)).filter_by(user_id=user.id)
        )

        resumo = f"Excluir '{username}' e {n_simulados} simulado(s) dele"
        if concursos:
            resumo += f"; {len(concursos)} concurso(s) irão para '{reassign_concursos_to}'"
        if not yes and not click.confirm(f"{resumo}. Confirmar?"):
            click.echo("Cancelado.")
            return

        if concursos:
            for c in concursos:
                c.created_by = destino.id

        # Apaga os simulados via ORM para acionar o cascade em SimuladoMateria.
        for s in db.session.scalars(
            db.select(Simulado).filter_by(user_id=user.id)
        ).all():
            db.session.delete(s)

        db.session.delete(user)
        db.session.commit()

        click.echo(f"Usuário '{username}' excluído ({n_simulados} simulado(s) removido(s)).")
        if concursos:
            click.echo(
                f"{len(concursos)} concurso(s) reatribuído(s) a '{reassign_concursos_to}'."
            )

    @app.cli.command("reset-password")
    @click.argument("username")
    def reset_password(username):
        """Gera nova senha temporária para um usuário (troca forçada no próximo login)."""
        user = db.session.scalar(db.select(User).filter_by(username=username))
        if user is None:
            raise click.ClickException(f"Usuário '{username}' não encontrado.")

        temp_password = _gerar_senha_temporaria()
        user.set_password(temp_password)
        user.must_change_password = True
        db.session.commit()

        click.echo(f"Senha de '{username}' redefinida.")
        click.echo(f"Senha temporária: {temp_password}")
