"""Converte docs/TERMOS.md no parcial que a página de termos inclui.

Por que na build e não em runtime: o texto muda uma vez por semestre, e
renderizar Markdown a cada visita significaria uma biblioteca a mais no
PythonAnywhere para nada. `markdown-it-py` já existe aqui (vem junto do `rich`)
e fica declarado só no requirements-dev.txt — produção não instala nada novo.

Por que gerado e commitado, em vez de duplicado à mão num template: texto
duplicado diverge no primeiro ajuste. A fonte é `docs/TERMOS.md` e só ela; o
parcial é derivado, e carrega o sha256 do fonte no topo. `test_termos.py`
compara os dois e reprova se alguém editar o .md sem rodar este script.

Uso:  python scripts/gerar_termos.py        (grava)
      python scripts/gerar_termos.py --conferir   (só diz se está desatualizado)
"""

import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTE = RAIZ / "docs" / "TERMOS.md"
DESTINO = RAIZ / "app" / "templates" / "_termos_gerado.html"

# Sintaxe que sabemos que a página estiliza. Qualquer coisa fora disto é erro,
# não improviso: melhor o script parar e alguém decidir, do que gerar HTML sem
# CSS e a página sair torta em produção.
TAGS_CONHECIDAS = {
    "h1", "h2", "h3", "p", "ul", "ol", "li", "strong", "em", "hr", "code",
    "table", "thead", "tbody", "tr", "th", "td", "a", "blockquote",
}


def sha_do_fonte() -> str:
    return hashlib.sha256(FONTE.read_bytes()).hexdigest()


def render() -> str:
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark").enable("table")
    corpo = md.render(FONTE.read_text(encoding="utf-8"))

    import re

    achadas = {t.lower() for t in re.findall(r"<\s*([a-zA-Z0-9]+)", corpo)}
    estranhas = achadas - TAGS_CONHECIDAS
    if estranhas:
        raise SystemExit(
            f"TERMOS.md usa sintaxe que a página não estiliza: {sorted(estranhas)}.\n"
            "Acrescente o CSS em app/static/css/app.css e a tag em TAGS_CONHECIDAS."
        )

    # Estilo inline quebraria a CSP 'self'. markdown-it não gera nenhum, mas a
    # checagem é barata e o dia em que gerar ninguém vai estar olhando.
    if "style=" in corpo:
        raise SystemExit("o HTML gerado tem estilo inline, que a CSP bloqueia")

    return (
        "{# GERADO por scripts/gerar_termos.py — NÃO EDITE À MÃO. #}\n"
        "{# A fonte é docs/TERMOS.md; edite lá e rode o script de novo. #}\n"
        f"{{# fonte-sha256: {sha_do_fonte()} #}}\n"
        f"{corpo}"
    )


def sha_registrado() -> str | None:
    if not DESTINO.exists():
        return None
    for linha in DESTINO.read_text(encoding="utf-8").splitlines()[:5]:
        if "fonte-sha256:" in linha:
            return linha.split("fonte-sha256:")[1].strip().rstrip("#").strip()
    return None


def main() -> int:
    if "--conferir" in sys.argv:
        atual, registrado = sha_do_fonte(), sha_registrado()
        if atual == registrado:
            print("em dia")
            return 0
        print(f"DESATUALIZADO: TERMOS.md mudou.\n  rode: python {Path(__file__).name}")
        return 1

    DESTINO.write_text(render(), encoding="utf-8", newline="\n")
    print(f"gerado {DESTINO.relative_to(RAIZ)} ({DESTINO.stat().st_size} bytes)")
    return 0


sys.exit(main())
