"""Casamento de concurso por banca + fase (o <select> "Conta para qual concurso").

O bug: com vários concursos da mesma banca — que é o caso de produção
(AFA, EFOMM Dia 1/2, EN Dia 1/2, EsPCEx Dia 1/2, IME 1ª/2ª Fase, ITA 1ª/2ª
Fase) — a resolução por banca do Bloco 1 nunca decidia, e o <select> abria no
PRIMEIRO concurso da lista. Num simulado do IME ele mostrava "EFOMM - Dia 1",
e um toque distraído arquivava o simulado no concurso errado.
"""

import json
from datetime import date

from app.grouping import casar_concurso, etapa_casa_fase
from app.models import Concurso, Materia, SimuladoTurma
from app.simulado_sync import opcoes_de_concurso
from app.simulado_turma_import import aplicar as aplicar_simulado
from app.simulado_turma_import import parse as parse_simulado
from app.vinculo import revincular
from tests.conftest import payload_simulado


# A lista real de produção, na ordem em que ela é cadastrada.
NOMES_PRODUCAO = [
    "AFA",
    "EFOMM - Dia 1",
    "EFOMM - Dia 2",
    "EN - Dia 1",
    "EN - Dia 2",
    "EsPCEx - Dia 1",
    "EsPCEx - Dia 2",
    "IME - 1ª Fase",
    "ITA - 1ª Fase",
    "ITA - 2ª Fase",
    "IME - 2ª Fase",
]


def _semear_concursos(db, admin, nomes=NOMES_PRODUCAO):
    """Cria os concursos na ordem dada (data crescente = ordem da lista)."""
    criados = []
    for i, nome in enumerate(nomes):
        concurso = Concurso(
            nome=nome, data_prova=date(2027, 1, 1 + i), created_by=admin.id
        )
        concurso.set_materias(
            [Materia.MATEMATICA, Materia.FISICA, Materia.QUIMICA, Materia.INGLES]
        )
        db.session.add(concurso)
        criados.append(concurso)
    db.session.commit()
    return criados


def _turma(db, admin, banca="IME", fase="objetiva", rotulo="S3"):
    # `questoes` explícito: só as bancas de QUESTOES_PADRAO têm total implícito,
    # e aqui os rankings são de IME/EFOMM/UNICAMP também.
    dados = payload_simulado(
        rotulo=rotulo,
        banca=banca,
        questoes={"MAT": 12, "FIS": 12, "QUIM": 12, "ING": 12},
    )
    aplicar_simulado(db, parse_simulado(json.dumps(dados)), admin.id)
    db.session.commit()
    turma = db.session.scalar(db.select(SimuladoTurma).filter_by(banca=banca))
    turma.fase = fase
    db.session.commit()
    return turma


# ---------------------------------------------------------------------------
# etapa_casa_fase: normalização
# ---------------------------------------------------------------------------


def test_etapa_casa_fase_normaliza_acento_e_caixa():
    """"1ª Fase", "1a fase" e "1ª FASE" têm que casar igual."""
    for etapa in ("1ª Fase", "1a fase", "1ª FASE", "1A FASE"):
        assert etapa_casa_fase(etapa, "objetiva") is True
        assert etapa_casa_fase(etapa, "discursiva") is False
    for etapa in ("2ª Fase", "2a fase", "2ª FASE"):
        assert etapa_casa_fase(etapa, "discursiva") is True
        assert etapa_casa_fase(etapa, "objetiva") is False


def test_etapa_casa_fase_aceita_sufixo_depois_da_fase():
    """"2ª Fase, dia 1" continua sendo a discursiva."""
    assert etapa_casa_fase("2ª Fase, dia 1", "discursiva") is True


def test_etapa_de_dia_e_etapa_vazia_nunca_casam():
    """EFOMM/EN/EsPCEx não têm 1ª/2ª fase; "AFA" não tem etapa nenhuma."""
    for etapa in ("Dia 1", "Dia 2", ""):
        assert etapa_casa_fase(etapa, "objetiva") is False
        assert etapa_casa_fase(etapa, "discursiva") is False


def test_etapa_casa_fase_sem_fase_no_ranking():
    assert etapa_casa_fase("1ª Fase", None) is False
    assert etapa_casa_fase("1ª Fase", "") is False


# ---------------------------------------------------------------------------
# casar_concurso: os casos pedidos
# ---------------------------------------------------------------------------


def test_ime_objetiva_sugere_primeira_fase(app, db, admin):
    """O caso do bug: IME objetiva não pode abrir em "EFOMM - Dia 1"."""
    concursos = _semear_concursos(db, admin)
    compativeis, sugestao = casar_concurso(concursos, "IME", "objetiva")

    assert sugestao is not None
    assert sugestao.nome == "IME - 1ª Fase"
    assert [c.nome for c in compativeis] == ["IME - 1ª Fase", "IME - 2ª Fase"]
    # E o primeiro da lista completa continua sendo outra banca — ou seja, sem
    # a regra nova a pré-seleção cairia justamente no concurso errado.
    assert concursos[0].nome == "AFA"


def test_ita_discursiva_sugere_segunda_fase(app, db, admin):
    concursos = _semear_concursos(db, admin)
    compativeis, sugestao = casar_concurso(concursos, "ITA", "discursiva")

    assert sugestao is not None
    assert sugestao.nome == "ITA - 2ª Fase"
    assert [c.nome for c in compativeis] == ["ITA - 1ª Fase", "ITA - 2ª Fase"]


def test_ita_objetiva_sugere_primeira_fase(app, db, admin):
    concursos = _semear_concursos(db, admin)
    _, sugestao = casar_concurso(concursos, "ITA", "objetiva")
    assert sugestao.nome == "ITA - 1ª Fase"


def test_efomm_fica_ambiguo_mas_filtra_por_banca(app, db, admin):
    """Dia 1/Dia 2 não têm noção de fase: duas opções, nenhuma pré-selecionada."""
    concursos = _semear_concursos(db, admin)
    compativeis, sugestao = casar_concurso(concursos, "EFOMM", "objetiva")

    assert sugestao is None
    assert [c.nome for c in compativeis] == ["EFOMM - Dia 1", "EFOMM - Dia 2"]


def test_banca_com_concurso_unico_continua_resolvendo(app, db, admin):
    """Comportamento do Bloco 1 preservado: AFA é única, resolve mesmo sem fase."""
    concursos = _semear_concursos(db, admin)
    compativeis, sugestao = casar_concurso(concursos, "AFA", "objetiva")

    assert sugestao is not None
    assert sugestao.nome == "AFA"
    assert [c.nome for c in compativeis] == ["AFA"]


def test_banca_sem_concurso_devolve_lista_cheia(app, db, admin):
    """Sem correspondência de banca, `compativeis` vem vazio e a tela mostra tudo."""
    concursos = _semear_concursos(db, admin)
    compativeis, sugestao = casar_concurso(concursos, "UNICAMP", "objetiva")

    assert sugestao is None
    assert compativeis == []


def test_banca_vazia_nao_quebra(app, db, admin):
    concursos = _semear_concursos(db, admin)
    assert casar_concurso(concursos, "", "objetiva") == ([], None)
    assert casar_concurso(concursos, None, None) == ([], None)


def test_ano_no_nome_do_concurso_ainda_casa(app, db, admin):
    """"ITA 2027 - 1ª Fase" tem que casar com o ranking "ITA" igual."""
    concursos = _semear_concursos(
        db, admin, ["ITA 2027 - 1ª Fase", "ITA 2027 - 2ª Fase"]
    )
    _, sugestao = casar_concurso(concursos, "ITA", "discursiva")
    assert sugestao.nome == "ITA 2027 - 2ª Fase"


# ---------------------------------------------------------------------------
# opcoes_de_concurso: o que o <select> recebe
# ---------------------------------------------------------------------------


def test_opcoes_separam_compativeis_de_outros_sem_perder_ninguem(app, db, admin):
    """Filtrar não pode esconder concurso: os dois grupos somam a lista inteira."""
    concursos = _semear_concursos(db, admin)
    turma = _turma(db, admin, banca="IME", fase="objetiva")

    compativeis, outros, sugestao = opcoes_de_concurso(turma, concursos)

    assert sugestao.nome == "IME - 1ª Fase"
    assert [c.nome for c in compativeis] == ["IME - 1ª Fase", "IME - 2ª Fase"]
    assert len(compativeis) + len(outros) == len(concursos)
    assert set(c.id for c in compativeis) & set(c.id for c in outros) == set()


def test_opcoes_sem_banca_correspondente_joga_tudo_em_outros(app, db, admin):
    concursos = _semear_concursos(db, admin)
    turma = _turma(db, admin, banca="UNICAMP", fase="objetiva")

    compativeis, outros, sugestao = opcoes_de_concurso(turma, concursos)

    assert compativeis == []
    assert sugestao is None
    assert len(outros) == len(concursos)


# ---------------------------------------------------------------------------
# As duas telas, de ponta a ponta
# ---------------------------------------------------------------------------


def test_turma_detalhe_preseleciona_o_concurso_certo(app, db, admin, client, logar):
    """A tela do "Trazer": o IME - 1ª Fase é que vem selected, não o primeiro."""
    _semear_concursos(db, admin)
    admin.nome_oficial = "ALUNO NOVATA UM"
    db.session.commit()
    turma = _turma(db, admin, banca="IME", fase="objetiva")
    revincular()
    db.session.commit()

    logar(admin)
    html = client.get(f"/simulados/turma/{turma.id}").get_data(as_text=True)

    ime_1a = db.session.scalar(db.select(Concurso).filter_by(nome="IME - 1ª Fase"))
    afa = db.session.scalar(db.select(Concurso).filter_by(nome="AFA"))
    assert f'<option value="{ime_1a.id}" selected>' in html
    assert f'<option value="{afa.id}" selected>' not in html
    # Os dois optgroups aparecem — nada foi escondido.
    assert 'label="Compatíveis"' in html
    assert 'label="Outros concursos"' in html
    assert f'value="{afa.id}"' in html


def test_sincronizar_preseleciona_o_concurso_certo(app, db, admin, client, logar):
    """O mesmo na sincronização em lote — as duas telas não podem divergir."""
    _semear_concursos(db, admin)
    admin.nome_oficial = "ALUNO NOVATA UM"
    db.session.commit()
    turma = _turma(db, admin, banca="ITA", fase="discursiva")
    revincular()
    db.session.commit()

    logar(admin)
    html = client.get("/simulados/sincronizar").get_data(as_text=True)

    ita_2a = db.session.scalar(db.select(Concurso).filter_by(nome="ITA - 2ª Fase"))
    ita_1a = db.session.scalar(db.select(Concurso).filter_by(nome="ITA - 1ª Fase"))
    assert f'<option value="{ita_2a.id}" selected>' in html
    assert f'<option value="{ita_1a.id}" selected>' not in html
    assert 'label="Compatíveis"' in html
    assert turma.rotulo in html


def test_turma_detalhe_sem_sugestao_abre_vazio(app, db, admin, client, logar):
    """EFOMM: sem desempate, o select abre em branco em vez de pré-selecionar
    o primeiro. Assim não dá para arquivar no errado com um toque distraído."""
    _semear_concursos(db, admin)
    admin.nome_oficial = "ALUNO NOVATA UM"
    db.session.commit()
    turma = _turma(db, admin, banca="EFOMM", fase="objetiva")
    revincular()
    db.session.commit()

    logar(admin)
    html = client.get(f"/simulados/turma/{turma.id}").get_data(as_text=True)

    assert "— escolha o concurso —" in html
    assert "selected" not in html.split('id="concurso_id"')[1].split("</select>")[0]


def test_usuario_ainda_pode_escolher_concurso_de_outra_banca(app, db, admin, client, logar):
    """Filtrar é sugestão, não trava: o POST com um concurso de "Outros" passa."""
    _semear_concursos(db, admin)
    admin.nome_oficial = "ALUNO NOVATA UM"
    db.session.commit()
    turma = _turma(db, admin, banca="IME", fase="objetiva")
    revincular()
    db.session.commit()

    afa = db.session.scalar(db.select(Concurso).filter_by(nome="AFA"))
    logar(admin)
    resposta = client.post(
        f"/simulados/turma/{turma.id}/trazer",
        data={"concurso_id": afa.id},
        follow_redirects=True,
    )

    assert resposta.status_code == 200
    from app.models import Simulado

    simulado = db.session.scalar(db.select(Simulado).filter_by(user_id=admin.id))
    assert simulado is not None
    assert simulado.concurso_id == afa.id
