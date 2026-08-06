"""Aluno como entidade: resolução de nome, merge e vínculo por aluno."""

import json

import pytest

from app.alunos import (
    ErroMerge,
    candidatos_a_merge,
    contar_linhas,
    encontrar_aluno,
    mesclar,
    resolver_aluno,
)
from app.models import Aluno, AlunoApelido, ResultadoLinha, SimuladoTurmaLinha
from app.oficiais_import import aplicar as aplicar_oficial
from app.oficiais_import import parse as parse_oficial
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from app.vinculo import revincular
from tests.conftest import payload_oficial, payload_simulado


def _importar_simulado(db, admin, **ajustes):
    aplicar_simulado(
        db, parse_simulado(json.dumps(payload_simulado(**ajustes))), admin.id
    )
    db.session.commit()


# --------------------------------------------------------------------------
# Resolução de nome
# --------------------------------------------------------------------------


def test_resolver_cria_uma_vez_so(app, db):
    primeiro = resolver_aluno("Fulano de Tal")
    db.session.commit()
    segundo = resolver_aluno("FULANO DE TAL")  # mesma pessoa, outra caixa
    assert primeiro.id == segundo.id
    assert db.session.scalar(db.select(db.func.count(Aluno.id))) == 1


def test_resolver_normaliza_acento_e_espaco(app, db):
    a = resolver_aluno("JOÃO   DA  SILVA")
    db.session.commit()
    assert encontrar_aluno("joao da silva").id == a.id


def test_encontrar_nao_cria(app, db):
    assert encontrar_aluno("NINGUEM AQUI") is None
    assert db.session.scalar(db.select(db.func.count(Aluno.id))) == 0


def test_apelido_resolve_para_o_dono(app, db):
    aluno = resolver_aluno("MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO")
    db.session.add(
        AlunoApelido(
            aluno_id=aluno.id,
            nome_norm="MARCUS VINICIUS B DE OLIVEIRA MELO COELHO",
            origem="merge",
        )
    )
    db.session.commit()

    achado = resolver_aluno("Marcus Vinicius B de Oliveira Melo Coelho")
    assert achado.id == aluno.id
    assert db.session.scalar(db.select(db.func.count(Aluno.id))) == 1


# --------------------------------------------------------------------------
# Import preenche aluno_id
# --------------------------------------------------------------------------


def test_import_preenche_aluno_id(app, db, admin):
    _importar_simulado(db, admin)
    linhas = db.session.scalars(db.select(SimuladoTurmaLinha)).all()
    assert linhas and all(ln.aluno_id is not None for ln in linhas)


def test_mesma_pessoa_em_duas_fontes_vira_um_aluno(app, db, admin):
    """O nome aparece no ranking e no listão: um aluno só, duas linhas."""
    aplicar_simulado(
        db, parse_simulado(json.dumps(payload_simulado())), admin.id
    )
    oficial = payload_oficial()
    oficial["resultados"][0]["nome"] = "ALUNO NOVATA UM"
    aplicar_oficial(db, parse_oficial(json.dumps(oficial)), admin.id)
    db.session.commit()

    aluno = encontrar_aluno("ALUNO NOVATA UM")
    assert aluno is not None
    assert contar_linhas(aluno) == 2


def test_reimportar_com_nome_apelidado_nao_duplica(app, db, admin):
    """Aceite A.7: import futuro com a grafia antiga cai no aluno certo."""
    _importar_simulado(db, admin, rotulo="S1", data="2026-03-01")
    antigo = encontrar_aluno("ALUNO NOVATA UM")

    # Um segundo simulado traz a pessoa com o nome truncado.
    truncado = payload_simulado(rotulo="S2", data="2026-04-01")
    truncado["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(truncado)), admin.id)
    db.session.commit()

    duplicado = encontrar_aluno("ALUNO NOVATA U")
    assert duplicado.id != antigo.id, "sem curadoria, nasce mesmo duplicado"

    mesclar(antigo, duplicado)
    db.session.commit()

    # Um terceiro import com a grafia truncada agora resolve para o aluno certo.
    terceiro = payload_simulado(rotulo="S3", data="2026-05-01")
    terceiro["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(terceiro)), admin.id)
    db.session.commit()

    assert encontrar_aluno("ALUNO NOVATA U").id == antigo.id
    assert db.session.scalar(
        db.select(db.func.count(Aluno.id)).filter(
            Aluno.nome_norm.like("ALUNO NOVATA U%")
        )
    ) == 1


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------


def test_merge_preserva_todas_as_linhas_e_cria_apelido(app, db, admin):
    _importar_simulado(db, admin, rotulo="S1", data="2026-03-01")
    outro = payload_simulado(rotulo="S2", data="2026-04-01")
    outro["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(outro)), admin.id)
    db.session.commit()

    fica = encontrar_aluno("ALUNO NOVATA UM")
    sai = encontrar_aluno("ALUNO NOVATA U")
    total_antes = contar_linhas(fica) + contar_linhas(sai)

    migradas = mesclar(fica, sai)
    db.session.commit()

    assert migradas == 1
    assert contar_linhas(fica) == total_antes, "nenhuma linha some no merge"
    assert db.session.get(Aluno, sai.id) is None
    apelidos = {a.nome_norm for a in fica.apelidos}
    assert "ALUNO NOVATA U" in apelidos


def test_merge_recusa_contas_diferentes(app, db, admin, criar_usuario):
    _importar_simulado(db, admin, rotulo="S1", data="2026-03-01")
    outro = payload_simulado(rotulo="S2", data="2026-04-01")
    outro["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(outro)), admin.id)
    db.session.commit()

    a, b = encontrar_aluno("ALUNO NOVATA UM"), encontrar_aluno("ALUNO NOVATA U")
    a.user_id = criar_usuario("um").id
    b.user_id = criar_usuario("dois").id
    db.session.commit()

    with pytest.raises(ErroMerge, match="contas diferentes"):
        mesclar(a, b)


def test_merge_de_um_aluno_com_ele_mesmo_e_recusado(app, db, admin):
    _importar_simulado(db, admin)
    aluno = encontrar_aluno("ALUNO NOVATA UM")
    with pytest.raises(ErroMerge):
        mesclar(aluno, aluno)


def test_candidatos_sugerem_truncamento_e_abreviacao(app, db):
    resolver_aluno("MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO")
    resolver_aluno("MARCUS VINICIUS BERNARDINO DE OLIVEIRA M")
    resolver_aluno("DANIEL DOURADO OLIVEIRA XIMENES")
    resolver_aluno("DANIEL DOURADO O. XIMENES")
    resolver_aluno("PESSOA COMPLETAMENTE DIFERENTE")
    db.session.commit()

    pares = candidatos_a_merge()
    nomes = {frozenset((p["a"].nome, p["b"].nome)) for p in pares}
    assert frozenset(
        ("MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO",
         "MARCUS VINICIUS BERNARDINO DE OLIVEIRA M")
    ) in nomes
    assert frozenset(
        ("DANIEL DOURADO OLIVEIRA XIMENES", "DANIEL DOURADO O. XIMENES")
    ) in nomes
    assert not any("DIFERENTE" in p["a"].nome + p["b"].nome for p in pares)


# --------------------------------------------------------------------------
# Vínculo agora passa pelo Aluno
# --------------------------------------------------------------------------


def test_revincular_marca_aluno_e_propaga_para_linhas(app, db, admin, criar_usuario):
    _importar_simulado(db, admin)
    dono = criar_usuario("dono", nome_oficial="ALUNO NOVATA UM")
    revincular()
    db.session.commit()

    aluno = encontrar_aluno("ALUNO NOVATA UM")
    assert aluno.user_id == dono.id
    linhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(aluno_id=aluno.id)
    ).all()
    assert linhas and all(ln.user_id == dono.id for ln in linhas)


def test_vinculo_alcanca_grafia_apelidada(app, db, admin, criar_usuario):
    """Quem se reconheceu numa grafia continua reconhecido na outra."""
    _importar_simulado(db, admin, rotulo="S1", data="2026-03-01")
    outro = payload_simulado(rotulo="S2", data="2026-04-01")
    outro["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(outro)), admin.id)
    db.session.commit()

    fica, sai = encontrar_aluno("ALUNO NOVATA UM"), encontrar_aluno("ALUNO NOVATA U")
    mesclar(fica, sai)
    db.session.commit()

    # O usuário declara justamente a grafia que virou apelido.
    dono = criar_usuario("dono", nome_oficial="ALUNO NOVATA U")
    revincular()
    db.session.commit()

    assert fica.user_id == dono.id
    linhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(aluno_id=fica.id)
    ).all()
    assert len(linhas) == 2
    assert all(ln.user_id == dono.id for ln in linhas)


def test_revincular_solta_quando_o_nome_sai(app, db, admin, criar_usuario):
    _importar_simulado(db, admin)
    dono = criar_usuario("dono", nome_oficial="ALUNO NOVATA UM")
    revincular()
    db.session.commit()

    dono.nome_oficial = None
    revincular()
    db.session.commit()

    aluno = encontrar_aluno("ALUNO NOVATA UM")
    assert aluno.user_id is None
    assert all(
        ln.user_id is None
        for ln in db.session.scalars(db.select(SimuladoTurmaLinha))
    )


# --------------------------------------------------------------------------
# Telas de admin
# --------------------------------------------------------------------------


def test_telas_de_admin_respondem(app, db, client, admin, logar):
    _importar_simulado(db, admin)
    logar(admin)
    aluno = encontrar_aluno("ALUNO NOVATA UM")

    assert client.get("/admin/turmas").status_code == 200
    assert client.get("/admin/turmas/novata").status_code == 200
    assert client.get(f"/admin/alunos/{aluno.id}").status_code == 200
    assert client.get("/admin/merge").status_code == 200


def test_admin_e_so_para_admin(app, db, client, admin, usuario, logar):
    _importar_simulado(db, admin)
    logar(usuario)
    assert client.get("/admin/turmas").status_code == 403
    assert client.get("/admin/merge").status_code == 403


def test_editar_aluno_recusa_nome_de_outro(app, db, client, admin, logar):
    _importar_simulado(db, admin)
    logar(admin)
    alvo = encontrar_aluno("ALUNO NOVATA UM")

    resposta = client.post(
        f"/admin/alunos/{alvo.id}",
        data={"nome": "ALUNO NOVATA DOIS", "turma": "novata", "serie": "3º ANO",
              "ativo": "y"},
    )

    assert "mesma pessoa" in resposta.get_data(as_text=True)
    db.session.refresh(alvo)
    assert alvo.nome == "ALUNO NOVATA UM"


def test_merge_pela_rota(app, db, client, admin, logar):
    _importar_simulado(db, admin, rotulo="S1", data="2026-03-01")
    outro = payload_simulado(rotulo="S2", data="2026-04-01")
    outro["resultados"][0]["nome"] = "ALUNO NOVATA U"
    aplicar_simulado(db, parse_simulado(json.dumps(outro)), admin.id)
    db.session.commit()
    logar(admin)

    fica, sai = encontrar_aluno("ALUNO NOVATA UM"), encontrar_aluno("ALUNO NOVATA U")
    sai_id = sai.id
    client.post("/admin/merge", data={"sobrevivente": fica.id, "absorvido": sai_id})

    assert db.session.get(Aluno, sai_id) is None
    assert contar_linhas(fica) == 2
    assert db.session.scalar(db.select(db.func.count(ResultadoLinha.id))) == 0
