"""Import da 2ª fase: notas decimais, zero legítimo, média copiada.

Três coisas que a 1ª fase faz e a 2ª NÃO pode herdar:

1. Exigir total de questões. Na discursiva não existe; exigir matava o import
   no cabeçalho, reclamando de Português, Inglês e Redação.
2. Recusar quem zerou tudo. Na objetiva isso quase sempre é falta (chute
   acerta alguma); na discursiva zerar é comum e legítimo.
3. Validar acertos contra um total. Aqui a régua é a escala 0–10, com a mesma
   `validar_nota` que os listões oficiais usam.

E uma que ela ganha: o aviso de divergência da média — só para o ITA, nunca
bloqueando, nunca corrigindo.
"""

import json
from datetime import date

import pytest

from app.models import SimuladoTurma, SimuladoTurmaLinha
from app.simulado_turma_import import aplicar, parse
from app.validacao import ErroImport

from .conftest import payload_simulado, payload_simulado_discursivo


def _parse(payload):
    return parse(json.dumps(payload))


def _linha_de(dados, nome_parcial="UM"):
    return next(ln for ln in dados["linhas"] if nome_parcial in ln["nome"])


# --------------------------------------------------------------------------
# Sem total de questões
# --------------------------------------------------------------------------


def test_discursiva_nao_exige_total_de_questoes(app):
    """O bloqueio nº 1 do levantamento: `_questoes_da_banca` exigia total para
    toda matéria do cabeçalho, e a discursiva do IME traz PORT, ING e RED, que
    não estão em QUESTOES_PADRAO. O import morria antes da primeira linha."""
    dados = _parse(payload_simulado_discursivo(banca="IME"))

    assert dados["questoes"] == {}
    assert dados["fase"] == "discursiva"


def test_objetiva_continua_exigindo_total_de_questoes(app):
    """A régua velha não pode ter afrouxado junto."""
    with pytest.raises(ErroImport, match="questões"):
        _parse(payload_simulado(banca="BANCA_NOVA"))


# --------------------------------------------------------------------------
# Notas decimais
# --------------------------------------------------------------------------


def test_notas_decimais_entram_como_notas_e_nao_como_acertos(app):
    dados = _parse(payload_simulado_discursivo())

    linha = _linha_de(dados)
    assert linha["notas"]["MATEMATICA"] == 6.00
    assert linha["acertos"] == {}, "nota decimal caiu no campo de acertos"


def test_nota_fora_da_escala_para_o_import(app):
    """57,0 é 5,70 com a vírgula perdida — o erro mais comum da extração."""
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["notas"]["MAT"] = 57.0

    with pytest.raises(ErroImport, match="fora da escala"):
        _parse(payload)


def test_nota_negativa_para_o_import(app):
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["notas"]["MAT"] = -1.0

    with pytest.raises(ErroImport, match="fora da escala"):
        _parse(payload)


def test_materia_fora_do_cabecalho_para_o_import(app):
    """Coluna calculada (MÉDIA, MÉDIA FINAL) lida como se fosse matéria."""
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["notas"]["ING"] = 8.5

    with pytest.raises(ErroImport, match="não está na lista"):
        _parse(payload)


def test_materia_faltando_para_o_import(app):
    """Célula vazia não é zero: falta de matéria é erro de extração."""
    payload = payload_simulado_discursivo()
    del payload["resultados"][0]["notas"]["RED"]

    with pytest.raises(ErroImport, match="Célula vazia não é zero"):
        _parse(payload)


# --------------------------------------------------------------------------
# Zero é nota, não ausência
# --------------------------------------------------------------------------


def test_zerar_tudo_e_legitimo_na_discursiva(app):
    """O bloqueio nº 2. A planilha do ITA S5 tem uma linha 0,00 0,00 0,20 0,00
    0,00, e há quem zere tudo e ainda apareça com média. A regra da objetiva
    recusaria dado real."""
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["notas"] = {
        "MAT": 0.0, "QUIM": 0.0, "FIS": 0.0, "PORT": 0.0, "RED": 0.0
    }
    payload["resultados"][0]["media_oficial"] = 0.0

    dados = _parse(payload)

    linha = _linha_de(dados)
    assert linha["status"] == "presente"
    assert linha["notas"] == {
        "MATEMATICA": 0.0, "QUIMICA": 0.0, "FISICA": 0.0,
        "PORTUGUES": 0.0, "REDACAO": 0.0,
    }


def test_zerar_tudo_continua_recusado_na_objetiva(app):
    """Na 1ª fase zerar tudo quase certamente é falta — chute acerta alguma."""
    payload = payload_simulado()
    payload["resultados"][0]["acertos"] = {"MAT": 0, "FIS": 0, "QUIM": 0, "ING": 0}
    payload["resultados"][0]["geral_oficial"] = 0

    with pytest.raises(ErroImport, match="zerou em todas"):
        _parse(payload)


def test_ausente_na_discursiva_nao_traz_notas(app):
    dados = _parse(payload_simulado_discursivo())

    ausente = _linha_de(dados, "TRES")
    assert ausente["status"] == "ausente"
    assert ausente["notas"] == {}
    assert ausente["media_informada"] is None


# --------------------------------------------------------------------------
# As médias: copiadas, em campo próprio
# --------------------------------------------------------------------------


def test_media_da_planilha_vai_para_media_informada(app):
    dados = _parse(payload_simulado_discursivo())

    linha = _linha_de(dados)
    assert linha["media_informada"] == 5.67
    assert linha["media_oficial"] is None, "contaminou o campo da objetiva"
    assert linha["geral_oficial"] is None


def test_media_final_e_campo_separado(app):
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["media_final_oficial"] = 5.65

    linha = _linha_de(_parse(payload))

    assert linha["media_informada"] == 5.67
    assert linha["media_final_informada"] == 5.65


def test_sem_media_final_o_campo_fica_nulo(app):
    """Nunca calculada: a planilha de um bloco só não tem MÉDIA FINAL."""
    linha = _linha_de(_parse(payload_simulado_discursivo()))

    assert linha["media_final_informada"] is None


# --------------------------------------------------------------------------
# O aviso: só ITA, sem bloquear, sem corrigir
# --------------------------------------------------------------------------


def test_media_coerente_nao_gera_aviso(app):
    assert _parse(payload_simulado_discursivo())["avisos"] == []


def test_media_divergente_avisa_mas_nao_bloqueia(app):
    """Divergência é sinal de célula lida errado — mas quem decide é o humano,
    e o número que entra continua sendo o da planilha."""
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["media_oficial"] = 9.99

    dados = _parse(payload)

    assert len(dados["avisos"]) == 1
    assert "9.99" in dados["avisos"][0]
    assert "5.67" in dados["avisos"][0]
    # Não bloqueou, e não corrigiu:
    assert _linha_de(dados)["media_informada"] == 9.99


def test_o_ime_nunca_e_conferido_contra_conta_nossa(app):
    """Cinco famílias de hipótese morreram contra as 12 linhas do S6. Um aviso
    que dispara em toda linha treina o usuário a ignorar aviso."""
    payload = payload_simulado_discursivo(banca="IME")
    payload["resultados"][0]["media_oficial"] = 9.99

    assert _parse(payload)["avisos"] == []


def test_objetiva_do_ita_nao_gera_aviso_de_media_discursiva(app):
    """A fórmula é do bloco discursivo; aplicá-la à objetiva seria ruído."""
    assert _parse(payload_simulado())["avisos"] == []


def test_cabecalho_diferente_do_conhecido_cala_o_aviso(app):
    """Fórmula conhecida cobre cinco matérias exatas. Cabeçalho diferente é
    planilha que não conhecemos — e aí o app não opina."""
    payload = payload_simulado_discursivo()
    payload["materias"] = ["MAT", "QUIM", "FIS", "PORT"]
    for r in payload["resultados"]:
        if r["status"] == "presente":
            r["notas"].pop("RED")
            r["media_oficial"] = 9.99

    assert _parse(payload)["avisos"] == []


# --------------------------------------------------------------------------
# A segunda data: guardada e ignorada
# --------------------------------------------------------------------------


def test_data_secundaria_e_guardada(app):
    payload = payload_simulado_discursivo(data_secundaria="2026-04-14")

    assert _parse(payload)["data_secundaria"] == date(2026, 4, 14)


def test_data_secundaria_nao_vira_a_data_da_prova(app):
    """A 1ª fase do IME S6 é 04/07 e a 2ª diz "11/07 - 14/04". A segunda data
    não aponta para a outra fase — é resto de template. Guardar e ignorar."""
    payload = payload_simulado_discursivo(
        data="2026-07-11", data_secundaria="2026-04-14"
    )

    dados = _parse(payload)

    assert dados["data"] == date(2026, 7, 11)
    assert dados["data_secundaria"] == date(2026, 4, 14)


def test_data_secundaria_invalida_para_o_import(app):
    payload = payload_simulado_discursivo(data_secundaria="14/04/2026")

    with pytest.raises(ErroImport, match="data_secundaria"):
        _parse(payload)


# --------------------------------------------------------------------------
# Ponta a ponta
# --------------------------------------------------------------------------


def test_import_completo_da_2a_fase(app, db, admin):
    dados = _parse(payload_simulado_discursivo(data_secundaria="2026-04-14"))

    prova = aplicar(db, dados, admin.id)
    db.session.commit()

    assert prova.fase == "discursiva"
    assert prova.data_secundaria == date(2026, 4, 14)
    assert prova.questoes == {}

    linha = next(ln for ln in prova.linhas if "UM" in ln.nome)
    assert linha.notas["MATEMATICA"] == 6.00
    assert linha.acertos == {}
    assert linha.media_informada == 5.67
    assert linha.media_oficial is None


def test_ranking_da_2a_fase_ordena_pela_media_simples(app, db, admin):
    """`nota_de` na discursiva é a média SIMPLES do recorte — régua do filtro,
    não a média do colégio (que pesa exatas em dobro)."""
    prova = aplicar(db, _parse(payload_simulado_discursivo()), admin.id)
    db.session.commit()

    ranking = prova.ranking(prova.materias)

    nomes = [ln.nome for _, ln, _ in ranking]
    assert "UM" in nomes[0], f"ordem inesperada: {nomes}"
    # (6.00 + 6.35 + 3.40 + 6.67 + 7.20) / 5 = 5.924
    assert ranking[0][2] == 5.92
    assert ranking[0][2] != ranking[0][1].media_informada


def test_as_duas_fases_do_mesmo_simulado_caem_na_mesma_pessoa(app, db, admin):
    """Nome é o que casa as fases — não a data, que difere (IME S6: 04/07 e
    11/07), nem `data_secundaria`."""
    from app.models import Aluno

    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    aplicar(db, _parse(payload_simulado_discursivo("novata")), admin.id)
    db.session.commit()

    aluno = db.session.scalar(
        db.select(Aluno).filter(Aluno.nome.like("%NOVATA UM%"))
    )
    linhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(aluno_id=aluno.id)
    ).all()

    assert len(linhas) == 2
    assert {ln.turma_obj.fase for ln in linhas} == {"objetiva", "discursiva"}


def test_reimportar_a_discursiva_substitui_sem_duplicar(app, db, admin):
    aplicar(db, _parse(payload_simulado_discursivo("novata")), admin.id)
    db.session.commit()
    aplicar(db, _parse(payload_simulado_discursivo("novata")), admin.id)
    db.session.commit()

    provas = db.session.scalars(db.select(SimuladoTurma)).all()
    assert len(provas) == 1
    assert len(provas[0].linhas) == 3


# --------------------------------------------------------------------------
# Edição manual: cada fase no seu campo
# --------------------------------------------------------------------------


def _prova_discursiva(db, admin):
    prova = aplicar(db, _parse(payload_simulado_discursivo("novata")), admin.id)
    db.session.commit()
    return prova


def test_admin_edita_nota_decimal_da_discursiva(client, db, admin, logar):
    prova = _prova_discursiva(db, admin)
    linha = next(ln for ln in prova.linhas if ln.status == "presente")
    logar(admin)

    client.post(f"/simulados/turma/linha/{linha.id}/editar", data={
        "nome": linha.nome, "turma": linha.turma, "serie": linha.serie,
        "status": "presente",
        "notas_MATEMATICA": "7,25", "notas_QUIMICA": "6.35",
        "notas_FISICA": "3.40", "notas_PORTUGUES": "6.67", "notas_REDACAO": "7.20",
        "media_informada": "6,00",
    })

    db.session.refresh(linha)
    assert linha.notas["MATEMATICA"] == 7.25  # vírgula aceita, como no resto
    assert linha.media_informada == 6.00
    assert linha.acertos == {}, "nota decimal caiu na coluna de acertos"


def test_edicao_recusa_nota_fora_da_escala(client, db, admin, logar):
    prova = _prova_discursiva(db, admin)
    linha = next(ln for ln in prova.linhas if ln.status == "presente")
    antes = dict(linha.notas)
    logar(admin)

    resposta = client.post(
        f"/simulados/turma/linha/{linha.id}/editar",
        data={
            "nome": linha.nome, "turma": linha.turma, "serie": linha.serie,
            "status": "presente", "notas_MATEMATICA": "57",
        },
        follow_redirects=True,
    )

    assert "fora da escala" in resposta.get_data(as_text=True)
    db.session.refresh(linha)
    assert linha.notas == antes, "gravou apesar do erro"


def test_a_tela_da_discursiva_nao_promete_a_conta_da_objetiva(client, db, admin, logar):
    """O texto da tela dizia que a nota é acertos/questões e que é "a mesma
    conta do colégio". Na discursiva as duas afirmações são falsas."""
    prova = _prova_discursiva(db, admin)
    logar(admin)

    corpo = client.get(f"/simulados/turma/{prova.id}").get_data(as_text=True)

    assert "soma dos acertos" not in corpo
    assert "média simples" in corpo
    assert "não é a média do colégio" in corpo


def test_a_tela_mostra_a_media_copiada_ao_lado_da_calculada(client, db, admin, logar):
    """A nota grande é do recorte, calculada; a média da planilha é o número do
    colégio. As duas na tela, e rotuladas, para ninguém confundir."""
    prova = _prova_discursiva(db, admin)
    logar(admin)

    corpo = client.get(f"/simulados/turma/{prova.id}").get_data(as_text=True)

    assert "média da planilha 5.67" in corpo
    assert "5.92" in corpo  # a média simples do recorte


def test_o_ranking_no_cliente_recebe_notas_e_fase(client, db, admin, logar):
    """O JS recalcula o ranking ao mudar o recorte. Sem `fase` e sem `notas` no
    payload ele computaria em cima de `acertos` vazio e a lista sumiria."""
    prova = _prova_discursiva(db, admin)
    logar(admin)

    corpo = client.get(f"/simulados/turma/{prova.id}").get_data(as_text=True)

    assert '"fase": "discursiva"' in corpo
    assert '"notas"' in corpo


def test_campo_que_o_import_nao_le_gera_aviso(app):
    """A guarda que nasceu de um erro real: o prompt passou a emitir
    `media_final_oficial` e o parser continuou lendo `media_final`. A MÉDIA
    FINAL sumia em silêncio — import verde, tela vazia, ninguém sabendo."""
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["media_final"] = 5.65  # o nome ERRADO

    avisos = _parse(payload)["avisos"]

    assert any("media_final" in a and "DESCARTAR" in a for a in avisos)


def test_o_nome_certo_nao_gera_aviso(app):
    payload = payload_simulado_discursivo()
    payload["resultados"][0]["media_final_oficial"] = 5.65

    dados = _parse(payload)

    assert dados["avisos"] == []
    assert _linha_de(dados)["media_final_informada"] == 5.65


def test_a_fixture_usa_os_mesmos_campos_do_prompt(app):
    """Se a fixture divergir do prompt, os testes passam e o import real
    quebra — que é exatamente o buraco que esta guarda fecha."""
    assert _parse(payload_simulado_discursivo())["avisos"] == []
