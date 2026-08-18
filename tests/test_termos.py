"""Página de termos: pública, e com uma fonte só.

O jeito de errar isto é o texto virar dois: o .md que o autor edita e um
template que alguém "ajustou rapidinho". No dia seguinte eles discordam e a
página passa a mentir sobre o que o site faz. Por isso o parcial é GERADO e
carrega o sha256 do fonte — e este teste reprova se os dois se separarem.
"""

import hashlib
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTE = RAIZ / "docs" / "TERMOS.md"
GERADO = RAIZ / "app" / "templates" / "_termos_gerado.html"


def test_o_html_gerado_bate_com_o_markdown():
    """Reprova se alguém editar TERMOS.md sem rodar scripts/gerar_termos.py.

    Compara hash, não conteúdo: assim o teste não precisa de markdown-it-py,
    que é dependência só de desenvolvimento e não existe em produção.
    """
    assert GERADO.exists(), "rode: python scripts/gerar_termos.py"

    achado = re.search(r"fonte-sha256:\s*([0-9a-f]{64})", GERADO.read_text(encoding="utf-8"))
    assert achado, "o parcial gerado perdeu o carimbo do fonte"

    atual = hashlib.sha256(FONTE.read_bytes()).hexdigest()
    assert achado.group(1) == atual, (
        "docs/TERMOS.md mudou e a página não. Rode: python scripts/gerar_termos.py"
    )


def test_o_texto_nao_esta_duplicado_em_template_nenhum():
    """Uma frase do meio do documento só pode existir em dois lugares: o .md e
    o parcial gerado a partir dele."""
    marca = "não usar esse acesso para bisbilhotar"
    assert marca in FONTE.read_text(encoding="utf-8")

    onde = [
        p for p in (RAIZ / "app" / "templates").rglob("*.html")
        if marca in p.read_text(encoding="utf-8")
    ]

    assert [p.name for p in onde] == ["_termos_gerado.html"], (
        f"texto de termos duplicado em {[p.name for p in onde]}"
    )


def test_o_html_gerado_nao_tem_estilo_inline():
    """A CSP é 'self': estilo inline não renderiza e a página sai torta."""
    corpo = GERADO.read_text(encoding="utf-8")

    assert "style=" not in corpo
    assert "<script" not in corpo


# --------------------------------------------------------------------------
# A rota
# --------------------------------------------------------------------------


def test_termos_abre_sem_login(client):
    """O caso central da seção 5: quem aparece num ranking e nunca criou conta.

    Exigir login para ler o que o site faz com o nome da pessoa seria o oposto
    do que o próprio texto promete.
    """
    resposta = client.get("/termos")

    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Termos de uso e aviso de privacidade" in corpo
    assert "Qualquer pessoa pode pedir para ser removida" in corpo


def test_termos_preserva_o_caixa_alta_do_autor(client):
    """Os "NÃO" em caixa alta são escolha do autor, não acidente de conversão."""
    corpo = client.get("/termos").get_data(as_text=True)

    assert "NÃO enxerga dado de outras pessoas" in corpo
    assert "<strong>NÃO veem</strong>" in corpo


def test_a_tabela_de_quem_ve_o_que_virou_tabela_de_verdade(client):
    """A seção 4 é o centro do documento e é uma tabela Markdown."""
    corpo = client.get("/termos").get_data(as_text=True)

    assert "<table>" in corpo
    assert "<th>Você é</th>" in corpo


def test_link_para_os_termos_em_toda_tela(client, db, usuario, logar):
    """Rodapé do base.html: vale para quem está logado e para quem não está."""
    assert 'href="/termos"' in client.get("/login").get_data(as_text=True)
    assert 'href="/termos"' in client.get("/registrar").get_data(as_text=True)

    logar(usuario)
    assert 'href="/termos"' in client.get("/").get_data(as_text=True)


def test_quem_cria_conta_ve_o_link_antes_de_criar(client):
    corpo = client.get("/registrar").get_data(as_text=True)

    assert "termos de uso e privacidade" in corpo


def test_senha_temporaria_ainda_le_os_termos(client, db, usuario, logar):
    """A guarda de troca de senha redireciona tudo — menos isto.

    Seria estranho que a única pessoa impedida de ler o que o site faz com os
    dados dela fosse justamente quem ainda não trocou a senha.
    """
    usuario.must_change_password = True
    db.session.commit()
    logar(usuario)

    assert client.get("/termos").status_code == 200
    assert client.get("/").status_code == 302  # o resto segue redirecionando
