"""Tela do histórico de import — só leitura, só admin.

A tabela `historico_imports` era só de escrita: gravava todo import aplicado e
ninguém nunca via. Estes testes fixam a tela que a torna consultável, e que
NÃO existe rollback por aqui.
"""

import json

from app.models import HistoricoImport, utcnow


def _registro(db, admin, tipo="simulado", alvo="ITA S3 - 2026-04-11", payload=None):
    r = HistoricoImport(
        tipo=tipo,
        alvo=alvo,
        created_by=admin.id,
        created_at=utcnow(),
        payload_json=json.dumps(payload if payload is not None else {"tipo": tipo, "x": 1}),
    )
    db.session.add(r)
    db.session.commit()
    return r


# --------------------------------------------------------------------------
# Permissão
# --------------------------------------------------------------------------


def test_usuario_comum_nao_ve_historico(client, db, admin, usuario, logar):
    r = _registro(db, admin)
    logar(usuario)

    assert client.get("/admin/historico").status_code == 403
    assert client.get(f"/admin/historico/{r.id}").status_code == 403
    assert client.get(f"/admin/historico/{r.id}/baixar").status_code == 403


def test_deslogado_nao_ve_historico(client, db, admin):
    r = _registro(db, admin)

    assert client.get("/admin/historico").status_code == 302
    assert client.get(f"/admin/historico/{r.id}").status_code == 302


# --------------------------------------------------------------------------
# Listagem
# --------------------------------------------------------------------------


def test_lista_mais_recente_primeiro(client, db, admin, logar):
    from datetime import timedelta

    velho = _registro(db, admin, alvo="AFA 2027 - novata")
    novo = _registro(db, admin, alvo="ITA S5 - veterana")
    velho.created_at = novo.created_at - timedelta(days=3)
    db.session.commit()
    logar(admin)

    corpo = client.get("/admin/historico").get_data(as_text=True)

    assert corpo.index("ITA S5 - veterana") < corpo.index("AFA 2027 - novata")


def test_lista_traz_tipo_alvo_quem_e_quando(client, db, admin, logar):
    r = _registro(db, admin, tipo="oficial", alvo="AFA 2027 - novata")
    logar(admin)

    corpo = client.get("/admin/historico").get_data(as_text=True)

    assert "oficial" in corpo
    assert "AFA 2027 - novata" in corpo
    assert admin.username in corpo
    assert r.created_at.strftime("%d/%m/%Y") in corpo


def test_lista_nao_despeja_o_json(client, db, admin, logar):
    """Cuidado com tamanho: o payload é só do detalhe."""
    _registro(db, admin, payload={"marca": "PAYLOAD-INTEIRO-AQUI", "linhas": list(range(500))})
    logar(admin)

    corpo = client.get("/admin/historico").get_data(as_text=True)

    assert "PAYLOAD-INTEIRO-AQUI" not in corpo
    assert "KB de JSON" in corpo, "mostra o tamanho, não o conteúdo"


def test_lista_vazia(client, db, admin, logar):
    logar(admin)

    corpo = client.get("/admin/historico").get_data(as_text=True)

    assert "Nenhum import registrado" in corpo


# --------------------------------------------------------------------------
# Detalhe e download
# --------------------------------------------------------------------------


def test_detalhe_mostra_json_formatado(client, db, admin, logar):
    r = _registro(db, admin, payload={"tipo": "simulado", "resultados": [{"nome": "ANA"}]})
    logar(admin)

    corpo = client.get(f"/admin/historico/{r.id}").get_data(as_text=True)

    assert "&#34;nome&#34;: &#34;ANA&#34;" in corpo or '"nome": "ANA"' in corpo
    assert "\n  " in corpo, "indentado, não numa linha só"


def test_detalhe_de_json_invalido_nao_quebra(client, db, admin, logar):
    """Payload que não é JSON válido aparece como veio, sem estourar a tela."""
    r = _registro(db, admin)
    r.payload_json = "{isso nao e json"
    db.session.commit()
    logar(admin)

    resposta = client.get(f"/admin/historico/{r.id}")

    assert resposta.status_code == 200
    assert "isso nao e json" in resposta.get_data(as_text=True)


def test_json_gigante_e_cortado_na_tela(client, db, admin, logar):
    from app.admin.routes import LIMITE_JSON_NA_TELA

    r = _registro(db, admin, payload={"linhas": ["x" * 200] * 2000})
    assert len(r.payload_json) > LIMITE_JSON_NA_TELA
    logar(admin)

    corpo = client.get(f"/admin/historico/{r.id}").get_data(as_text=True)

    assert "grande demais para caber na tela" in corpo
    assert len(corpo) < LIMITE_JSON_NA_TELA * 2, "não despejou o payload inteiro"


def test_baixar_devolve_o_payload_original(client, db, admin, logar):
    payload = {"tipo": "simulado", "resultados": [{"nome": "ANA", "acertos": {"MAT": 9}}]}
    r = _registro(db, admin, payload=payload)
    logar(admin)

    resposta = client.get(f"/admin/historico/{r.id}/baixar")

    assert resposta.status_code == 200
    assert resposta.mimetype == "application/json"
    assert "attachment" in resposta.headers["Content-Disposition"]
    assert f"import-simulado-{r.id}.json" in resposta.headers["Content-Disposition"]
    # Byte a byte o que foi gravado, sem reformatar.
    assert json.loads(resposta.get_data(as_text=True)) == payload


def test_historico_inexistente_da_404(client, db, admin, logar):
    logar(admin)

    assert client.get("/admin/historico/9999").status_code == 404
    assert client.get("/admin/historico/9999/baixar").status_code == 404


def test_nao_existe_rollback(client, db, admin, logar):
    """Fora de escopo por decisão: a tela é para comparar e reaplicar à mão."""
    r = _registro(db, admin)
    logar(admin)

    assert client.post(f"/admin/historico/{r.id}/desfazer").status_code in (404, 405)
    corpo = client.get(f"/admin/historico/{r.id}").get_data(as_text=True)
    assert "desfazer" not in corpo.lower()
