"""Diagnóstico de deploy: mede, nunca muda.

A tela nasceu de um deploy real em que o disco tinha uma versão e o worker
servia outra, e o `touch` no WSGI não reiniciou nada. A comparação
memória × disco é o mostrador que teria pego aquilo.
"""

import pathlib

import pytest

from app import diagnostico


# --------------------------------------------------------------------------
# A comparação que motivou a tela
# --------------------------------------------------------------------------


def test_versao_em_memoria_e_a_do_processo():
    from app.versao import VERSAO

    assert diagnostico.versao_em_memoria() == VERSAO


def test_versao_no_disco_le_o_arquivo_e_nao_o_cache(monkeypatch, tmp_path):
    """Importar de novo devolveria o módulo em cache — ou seja, a memória.
    Ler o arquivo é o que permite detectar que o disco está à frente."""
    falso = tmp_path / "versao.py"
    falso.write_text('VERSAO = "9.9.99"\n', encoding="utf-8")
    monkeypatch.setattr(diagnostico, "CAMINHO_VERSAO", falso)

    assert diagnostico.versao_no_disco() == "9.9.99"


def test_detecta_o_deploy_que_nao_pegou(monkeypatch, tmp_path):
    """O caso real: disco novo, memória velha."""
    falso = tmp_path / "versao.py"
    falso.write_text('VERSAO = "9.9.99"\n', encoding="utf-8")
    monkeypatch.setattr(diagnostico, "CAMINHO_VERSAO", falso)

    assert diagnostico.precisa_reiniciar() is True
    assert diagnostico.retrato()["precisa_reiniciar"] is True


def test_quando_bate_nao_pede_reinicio():
    assert diagnostico.precisa_reiniciar() is False


def test_versao_ilegivel_nao_quebra(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostico, "CAMINHO_VERSAO", tmp_path / "nao-existe.py")

    assert diagnostico.versao_no_disco() is None
    assert diagnostico.precisa_reiniciar() is False, "sem leitura, não acusa falso positivo"


# --------------------------------------------------------------------------
# Os fatos do worker
# --------------------------------------------------------------------------


def test_commit_local_sai_do_git_sem_precisar_do_binario():
    """O worker pode não ter `git` no PATH; o SHA está em arquivo de texto."""
    dados = diagnostico.commit_local()

    assert dados["erro"] is None, dados
    assert dados["sha"] and len(dados["sha"]) == 40, dados
    assert dados["branch"]


def test_commit_local_sem_git_avisa_em_vez_de_estourar(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostico, "CAMINHO_GIT", tmp_path / "sem-git")

    dados = diagnostico.commit_local()

    assert dados["sha"] is None
    assert "zip" in dados["erro"]


def test_identidade_responde_sem_erro():
    dados = diagnostico.identidade()

    assert "usuario" in dados and "uid" in dados
    assert isinstance(dados["escreve_na_raiz"], bool)
    assert isinstance(dados["toca_o_wsgi"], bool)


def test_proxy_e_git_sao_reportados():
    """São os dois fatos que decidem o plano B."""
    proxy = diagnostico.proxy_do_worker()
    git = diagnostico.git_no_path()

    assert isinstance(proxy["tem_proxy"], bool)
    assert isinstance(proxy["variaveis"], dict)
    assert isinstance(git["disponivel"], bool)


def test_timeout_de_rede_e_curto_e_explicito():
    """Sem proxy a conexão TRAVA em vez de falhar rápido; uma página de
    diagnóstico que pendura é pior que nenhuma."""
    assert 0 < diagnostico.TIMEOUT_REDE <= 10


# --------------------------------------------------------------------------
# A tela: só leitura, e só admin
# --------------------------------------------------------------------------


def test_so_admin_ve_o_diagnostico(client, db, usuario, logar):
    logar(usuario)

    assert client.get("/admin/deploy").status_code == 403
    assert client.post("/admin/deploy/testar-rede").status_code == 403


def test_deslogado_nao_ve(client, db):
    assert client.get("/admin/deploy").status_code == 302


def test_get_mostra_o_estado_sem_tocar_a_rede(client, db, admin, logar, monkeypatch):
    """O GET não pode sair da máquina: rede só no POST."""
    def _explode(*a, **kw):
        raise AssertionError("o GET não pode fazer rede")

    monkeypatch.setattr(diagnostico, "testar_github", _explode)
    monkeypatch.setattr(diagnostico, "sha_remoto", _explode)
    logar(admin)

    resposta = client.get("/admin/deploy")

    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Em memória" in corpo
    assert "No disco" in corpo
    assert "git no PATH" in corpo
    assert "Proxy visível" in corpo


def test_teste_de_rede_e_post_e_nao_get(client, db, admin, logar):
    logar(admin)

    assert client.get("/admin/deploy/testar-rede").status_code == 405


def test_a_tela_avisa_quando_precisa_reiniciar(client, db, admin, logar, monkeypatch, tmp_path):
    falso = tmp_path / "versao.py"
    falso.write_text('VERSAO = "9.9.99"\n', encoding="utf-8")
    monkeypatch.setattr(diagnostico, "CAMINHO_VERSAO", falso)
    logar(admin)

    corpo = client.get("/admin/deploy").get_data(as_text=True)

    assert "O deploy não pegou" in corpo
    assert "9.9.99" in corpo


def test_a_tela_nao_promete_agir():
    """Enquanto for só diagnóstico, tem que dizer que não muda nada."""
    html = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "templates" / "admin" / "deploy.html"
    ).read_text(encoding="utf-8")

    assert "não muda nada" in html


def _codigo_do_diagnostico() -> str:
    return (
        pathlib.Path(__file__).resolve().parent.parent / "app" / "diagnostico.py"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "proibido",
    [
        "import subprocess",
        "os.system",
        "os.popen",
        "os.remove",
        "os.rename",
        "shutil.rmtree",
        "shutil.copy",
        ".write_text(",
        ".write_bytes(",
        ".mkdir(",
        ".unlink(",
    ],
)
def test_diagnostico_nao_executa_nem_escreve(proibido):
    """Só leitura: nada de rodar comando, apagar, mover ou gravar arquivo.

    Os padrões são precisos de propósito: procurar "open(" pegaria o
    `abridor.open()` do urllib, e "subprocess" pegaria a palavra num comentário.
    Guarda que grita à toa é guarda que alguém desliga.
    """
    assert proibido not in _codigo_do_diagnostico(), (
        f"diagnostico.py não pode conter {proibido}"
    )


def test_nada_da_requisicao_vira_argumento():
    """Nem URL, nem branch, nem caminho: os alvos são fixos no código."""
    codigo = _codigo_do_diagnostico()

    assert "from flask import" not in codigo, "o módulo não conhece a requisição"
    assert "flask.request" not in codigo
    assert "github.com/TuxGames/ita-ime-analytics.git" in codigo
