"""O que o worker web sabe sobre si mesmo. SÓ LEITURA.

Existe por causa de um deploy real: o disco tinha 2.5.03, o site servia 2.5.02,
e o primeiro `touch` no WSGI não reiniciou o worker. Ninguém teria percebido se
não fosse o hábito de conferir o rodapé. Este módulo transforma exatamente essa
comparação em mostrador — versão em memória contra versão no disco.

Nada aqui escreve, move, apaga ou executa comando de mudança. A única função
que sai da máquina é `testar_github()`, e ela só faz uma leitura HTTP com
timeout curto — chamada a partir de um POST, nunca de um GET.
"""

import os
import pathlib
import re
import shutil
import socket
import urllib.error
import urllib.request

from .versao import VERSAO

# Raiz do projeto: a pasta que contém app/, wsgi.py e o .git.
RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Caminhos FIXOS no código. Nada aqui vem da requisição — é regra da tela.
CAMINHO_VERSAO = RAIZ / "app" / "versao.py"
CAMINHO_GIT = RAIZ / ".git"
# O WSGI que o PythonAnywhere executa (tocar nele é o que pede reload).
WSGI_PRODUCAO = pathlib.Path("/var/www/itaime_pythonanywhere_com_wsgi.py")

# O proxy da conta free. Só é USADO no teste de rede; nunca é gravado.
PROXY_PYTHONANYWHERE = "http://proxy.server:3128"
# Curto e explícito: sem proxy a conexão TRAVA até o timeout em vez de falhar
# rápido, e uma página de diagnóstico que pendura é pior que nenhuma.
TIMEOUT_REDE = 6.0


def versao_em_memoria() -> str:
    """A versão do código que ESTE processo carregou."""
    return VERSAO


def versao_no_disco() -> str | None:
    """A versão que está no arquivo agora — pode ser mais nova que a da memória.

    Lê com regex em vez de importar: importar de novo devolveria o módulo já
    em cache, ou seja, a versão da memória — justamente o que não queremos.
    """
    try:
        texto = CAMINHO_VERSAO.read_text(encoding="utf-8")
    except OSError:
        return None
    achado = re.search(r'^VERSAO\s*=\s*"([^"]+)"', texto, re.M)
    return achado.group(1) if achado else None


def precisa_reiniciar() -> bool:
    """Disco à frente da memória = o deploy chegou mas o worker não recarregou."""
    disco = versao_no_disco()
    return bool(disco) and disco != versao_em_memoria()


def _ler(caminho: pathlib.Path) -> str | None:
    try:
        return caminho.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def commit_local() -> dict:
    """Commit da árvore, lido direto do .git — sem depender do `git` no PATH.

    O worker pode não ter o binário; a informação, porém, está em arquivos de
    texto. Ler é mais confiável do que executar aqui.
    """
    dados = {"sha": None, "branch": None, "erro": None}
    head = _ler(CAMINHO_GIT / "HEAD")
    if head is None:
        dados["erro"] = "não achei o .git (o deploy foi por zip?)"
        return dados

    if head.startswith("ref: "):
        ref = head[5:].strip()
        dados["branch"] = ref.rsplit("/", 1)[-1]
        sha = _ler(CAMINHO_GIT / ref)
        if sha is None:  # ref empacotada
            empacotadas = _ler(CAMINHO_GIT / "packed-refs") or ""
            for linha in empacotadas.splitlines():
                if linha.endswith(" " + ref):
                    sha = linha.split(" ", 1)[0]
                    break
        dados["sha"] = sha
    else:
        dados["sha"] = head  # HEAD solto (detached)
        dados["branch"] = "(detached)"
    return dados


def quando(caminho: pathlib.Path):
    """mtime do arquivo, ou None se ele não existe/não dá para ler."""
    try:
        return caminho.stat().st_mtime
    except OSError:
        return None


def identidade() -> dict:
    """Quem é o processo e o que ele pode escrever.

    `os.access` responde pelo usuário EFETIVO do worker, que é o que importa —
    o console pode ter outra resposta.
    """
    dados = {
        "usuario": None,
        "uid": None,
        "raiz": str(RAIZ),
        "escreve_na_raiz": os.access(RAIZ, os.W_OK),
        "wsgi": str(WSGI_PRODUCAO),
        "wsgi_existe": WSGI_PRODUCAO.exists(),
        "toca_o_wsgi": False,
    }
    try:
        dados["uid"] = os.getuid()
    except AttributeError:
        dados["uid"] = "(Windows)"
    try:
        import getpass

        dados["usuario"] = getpass.getuser()
    except Exception:
        dados["usuario"] = os.environ.get("USER") or "(desconhecido)"

    if dados["wsgi_existe"]:
        dados["toca_o_wsgi"] = os.access(WSGI_PRODUCAO, os.W_OK)
    return dados


def proxy_do_worker() -> dict:
    """As variáveis de proxy que ESTE processo enxerga.

    O console tem `http_proxy`/`https_proxy`; o worker web pode não ter. É essa
    divergência de AMBIENTE (não de permissão) que decide se `git pull` de
    dentro do site é viável ou se o caminho é uma tarefa agendada.
    """
    nomes = ("http_proxy", "https_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY")
    achadas = {n: os.environ.get(n) for n in nomes if os.environ.get(n)}
    return {
        "variaveis": achadas,
        "tem_proxy": bool(achadas),
    }


def git_no_path() -> dict:
    """O worker consegue executar `git`? Decide o plano B."""
    caminho = shutil.which("git")
    return {"disponivel": caminho is not None, "caminho": caminho}


def testar_github(timeout: float = TIMEOUT_REDE) -> list[dict]:
    """Tenta alcançar o GitHub DE DENTRO do worker. Só leitura HTTP.

    Duas tentativas, porque elas respondem perguntas diferentes:
      1. com o ambiente como está — é assim que um `git pull` sairia hoje;
      2. forçando o proxy do PythonAnywhere — diz se bastaria configurá-lo.

    Se (1) falhar e (2) passar, o caminho é dar o proxy ao subprocesso. Se as
    duas falharem, a saída do worker está fechada e o plano B é a tarefa
    agendada.
    """
    alvo = "https://github.com/TuxGames/ita-ime-analytics.git/info/refs?service=git-upload-pack"
    resultados = []

    for rotulo, handler in (
        ("ambiente como está", None),
        ("forçando proxy.server:3128", urllib.request.ProxyHandler(
            {"http": PROXY_PYTHONANYWHERE, "https": PROXY_PYTHONANYWHERE}
        )),
    ):
        abridor = (
            urllib.request.build_opener(handler)
            if handler is not None
            else urllib.request.build_opener()
        )
        item = {"tentativa": rotulo, "ok": False, "detalhe": None}
        try:
            with abridor.open(alvo, timeout=timeout) as resposta:
                item["ok"] = resposta.status == 200
                item["detalhe"] = f"HTTP {resposta.status}"
        except urllib.error.HTTPError as erro:
            # Respondeu: a rede chegou lá, ainda que com status de erro.
            item["ok"] = True
            item["detalhe"] = f"HTTP {erro.code} (a rede chegou)"
        except (urllib.error.URLError, socket.timeout, OSError) as erro:
            item["detalhe"] = f"{type(erro).__name__}: {erro}"
        resultados.append(item)

    return resultados


def sha_remoto(timeout: float = TIMEOUT_REDE) -> dict:
    """O commit do `master` no origin, perguntado ao GitHub. Só leitura.

    Usa o protocolo burro do git por HTTP: a primeira linha útil da resposta
    traz o SHA de cada ref. Evita depender do binário `git` no worker.
    """
    alvo = "https://github.com/TuxGames/ita-ime-analytics.git/info/refs?service=git-upload-pack"
    dados = {"sha": None, "erro": None}
    for handler in (None, urllib.request.ProxyHandler(
        {"http": PROXY_PYTHONANYWHERE, "https": PROXY_PYTHONANYWHERE}
    )):
        abridor = (
            urllib.request.build_opener(handler)
            if handler is not None
            else urllib.request.build_opener()
        )
        try:
            with abridor.open(alvo, timeout=timeout) as resposta:
                corpo = resposta.read().decode("utf-8", "replace")
            achado = re.search(r"([0-9a-f]{40}) refs/heads/master", corpo)
            if achado:
                dados["sha"] = achado.group(1)
                return dados
            dados["erro"] = "resposta sem refs/heads/master"
        except Exception as erro:  # noqa: BLE001 — diagnóstico reporta qualquer falha
            dados["erro"] = f"{type(erro).__name__}: {erro}"
    return dados


def retrato() -> dict:
    """Tudo que dá para saber SEM sair da máquina. É o que o GET mostra."""
    memoria = versao_em_memoria()
    disco = versao_no_disco()
    return {
        "versao_memoria": memoria,
        "versao_disco": disco,
        "precisa_reiniciar": bool(disco) and disco != memoria,
        "commit": commit_local(),
        "identidade": identidade(),
        "proxy": proxy_do_worker(),
        "git": git_no_path(),
        "quando_codigo": quando(CAMINHO_VERSAO),
        "quando_wsgi": quando(WSGI_PRODUCAO),
    }
