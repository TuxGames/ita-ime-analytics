"""A 2ª fase é do admin. Para o resto do mundo, ela NÃO EXISTE.

Não é link escondido: a rota devolve 404, a listagem não a traz, a evolução a
ignora, a sincronização não a atravessa e nenhum número derivado dela sai em
lugar nenhum. Enquanto a coordenação não confirmar como o colégio calcula nota
e média com 2ª fase, nenhum aluno vê um número que ninguém consegue auditar.

QUANDO A COORDENAÇÃO CONFIRMAR: esvazie `FASES_RESERVADAS` em
app/visibilidade.py. Este arquivo inteiro vai falhar — e é essa a lista exata
do que volta a ficar visível. Confira um por um e apague o arquivo.

O teste que importa é `test_ninguem_ve_nada_da_2a_fase`: ele varre as telas com
uma prova discursiva plantada e procura QUALQUER resquício — nome da prova,
nota decimal, média copiada, rótulo de fase.
"""

import json
from datetime import date

import pytest

from app.evolucao import evolucao_do_aluno
from app.exportacao import exportar_dados_usuario
from app.media_final import media_final_da_linha
from app.models import Aluno, Concurso, SimuladoTurma, SimuladoTurmaLinha, User
from app.simulado_sync import linhas_pendentes, sincronizar_linha
from app.simulado_turma_import import aplicar, parse
from app.visibilidade import FASES_RESERVADAS

from .test_planilhas_reais import ITA_S5_DISCURSIVO, ITA_S5_OBJETIVA

SENHA = "senha-de-teste-123"

# Pedaços que só existem na prova discursiva. Se qualquer um aparecer numa tela
# de não-admin, vazou.
MARCAS_DA_2A_FASE = [
    "2ª fase",          # o rótulo da fase
    "discursiva",       # o nome interno
    "6.35",             # nota decimal de matéria, só existe na 2ª fase
    "5.67",             # a média copiada do bloco discursivo
    "5.65",             # a MÉDIA FINAL
    "média da planilha",
]


def _duas_fases(db, admin):
    objetiva = aplicar(db, parse(json.dumps(ITA_S5_OBJETIVA)), admin.id)
    discursiva = aplicar(db, parse(json.dumps(ITA_S5_DISCURSIVO)), admin.id)
    db.session.commit()
    return objetiva, discursiva


def _conta(db, username, **kw):
    u = User(username=username, must_change_password=False, convite_ok=True, **kw)
    u.set_password(SENHA)
    db.session.add(u)
    db.session.commit()
    return u


def _vincular(db, user, nome_parcial="PESSOA A"):
    """Liga a conta ao aluno que aparece nas DUAS fases."""
    aluno = db.session.scalar(
        db.select(Aluno).filter(Aluno.nome.like(f"%{nome_parcial}%"))
    )
    aluno.user_id = user.id
    aluno.vinculo_por_codigo = True
    for linha in db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(aluno_id=aluno.id)
    ):
        linha.user_id = user.id
    db.session.commit()
    return aluno


# --------------------------------------------------------------------------
# A varredura: nada da 2ª fase em tela nenhuma
# --------------------------------------------------------------------------

TELAS = [
    "/", "/perfil", "/simulados/", "/simulados/turma/", "/evolucao",
    "/oficiais/", "/meus-dados",
]


@pytest.mark.parametrize("papel", ["aluno", "professor"])
def test_ninguem_ve_nada_da_2a_fase(papel, client, db, admin, logar):
    """O teste que segura este lote.

    Conta comum e conta de professor, com uma prova discursiva no banco: nem
    200 com dado, nem link, nem número derivado.
    """
    _duas_fases(db, admin)
    conta = _conta(db, papel, is_professor=(papel == "professor"))
    _vincular(db, conta)
    logar(conta)

    telas = TELAS + (["/professor/"] if papel == "professor" else [])
    for rota in telas:
        resposta = client.get(rota)
        assert resposta.status_code == 200, f"{rota} -> {resposta.status_code}"
        corpo = resposta.get_data(as_text=True)
        for marca in MARCAS_DA_2A_FASE:
            assert marca not in corpo, f"{marca!r} vazou em {rota}"


def test_a_ficha_do_professor_nao_mostra_a_2a_fase(client, db, admin, logar):
    """Professor também não: ele não é admin, e o número não está confirmado."""
    _duas_fases(db, admin)
    aluno = db.session.scalar(db.select(Aluno).filter(Aluno.nome.like("%PESSOA A%")))
    logar(_conta(db, "prof", is_professor=True))

    corpo = client.get(f"/professor/aluno/{aluno.id}").get_data(as_text=True)

    for marca in MARCAS_DA_2A_FASE:
        assert marca not in corpo, f"{marca!r} vazou na ficha"
    assert "ITA S5" in corpo, "a 1ª fase tem que continuar aparecendo"


# --------------------------------------------------------------------------
# Rota fechada, não link escondido
# --------------------------------------------------------------------------


@pytest.mark.parametrize("papel", ["aluno", "professor"])
def test_a_prova_discursiva_da_404(papel, client, db, admin, logar):
    """404 e não 403: para quem não é admin, ela não existe. Um 403
    confirmaria que há uma prova ali."""
    _, discursiva = _duas_fases(db, admin)
    logar(_conta(db, papel, is_professor=(papel == "professor")))

    assert client.get(f"/simulados/turma/{discursiva.id}").status_code == 404


def test_a_prova_objetiva_continua_abrindo(client, db, admin, logar):
    """O bloqueio é da FASE, não do ranking inteiro."""
    objetiva, _ = _duas_fases(db, admin)
    logar(_conta(db, "aluno"))

    assert client.get(f"/simulados/turma/{objetiva.id}").status_code == 200


def test_a_exportacao_da_prova_discursiva_nao_sai(client, db, admin, logar):
    """Esta rota já era `@admin_required`, então o 403 vem antes do 404 — dois
    bloqueios em série, e o de fora é o mais forte. O teste existe para o dia
    em que alguém abrir a exportação para não-admin: aí o `_get_turma` segura,
    e este teste continua valendo sem precisar ser reescrito."""
    _, discursiva = _duas_fases(db, admin)
    logar(_conta(db, "aluno"))

    resposta = client.get(
        f"/simulados/turma/{discursiva.id}/exportar?turma=veterana"
    )

    assert resposta.status_code in (403, 404)
    assert "6.35" not in resposta.get_data(as_text=True)


def test_a_listagem_nao_traz_a_discursiva(client, db, admin, logar):
    objetiva, discursiva = _duas_fases(db, admin)
    logar(_conta(db, "aluno"))

    corpo = client.get("/simulados/turma/").get_data(as_text=True)

    assert f"/simulados/turma/{objetiva.id}" in corpo
    assert f"/simulados/turma/{discursiva.id}" not in corpo


# --------------------------------------------------------------------------
# O pior caminho: o dado atravessando para dentro da conta
# --------------------------------------------------------------------------


def test_a_sincronizacao_nao_oferece_linha_discursiva(app, db, admin):
    """Se ela entrar aqui, vira Simulado pessoal e depois gráfico — sem passar
    por nenhuma tela de ranking."""
    _duas_fases(db, admin)
    conta = _conta(db, "aluno")
    _vincular(db, conta)

    pendentes = linhas_pendentes(conta.id)

    assert pendentes, "a 1ª fase tem que continuar sendo oferecida"
    assert all(ln.turma_obj.fase == "objetiva" for ln in pendentes)


def test_sincronizar_uma_linha_discursiva_a_mao_nao_grava(app, db, admin):
    """Cinto de segurança: mesmo chamando direto, nada entra na conta."""
    _, discursiva = _duas_fases(db, admin)
    conta = _conta(db, "aluno")
    _vincular(db, conta)
    concurso = Concurso(
        nome="ITA 2027", data_prova=date(2026, 12, 13), created_by=admin.id
    )
    db.session.add(concurso)
    db.session.commit()
    linha = next(ln for ln in discursiva.linhas if ln.user_id == conta.id)

    assert sincronizar_linha(linha, concurso, conta.id) is None


def test_a_exportacao_de_dados_nao_leva_a_2a_fase(app, db, admin):
    """"Baixar meus dados" é uma tela como outra qualquer."""
    _duas_fases(db, admin)
    conta = _conta(db, "aluno")
    _vincular(db, conta)

    bruto = json.dumps(exportar_dados_usuario(conta), default=str)

    assert "discursiva" not in bruto
    assert "6.35" not in bruto


# --------------------------------------------------------------------------
# Números derivados
# --------------------------------------------------------------------------


def test_a_evolucao_ignora_a_2a_fase(app, db, admin):
    """Nem no gráfico, nem no por matéria, nem no percentil."""
    _duas_fases(db, admin)
    conta = _conta(db, "aluno")
    aluno = _vincular(db, conta)

    dados = evolucao_do_aluno(aluno.id, user=conta)

    assert len(dados["labels"]) == 1, f"veio a 2ª fase: {dados['labels']}"
    assert "2ª fase" not in dados["labels"][0]
    bruto = json.dumps(dados, default=str)
    assert "6.35" not in bruto


def test_o_admin_ve_as_duas_fases_na_evolucao(app, db, admin):
    """O outro lado: para o admin nada mudou."""
    _duas_fases(db, admin)
    aluno = db.session.scalar(db.select(Aluno).filter(Aluno.nome.like("%PESSOA A%")))

    dados = evolucao_do_aluno(aluno.id, user=admin)

    assert len(dados["labels"]) == 2


def test_a_media_final_nao_aparece_para_nao_admin(app, db, admin):
    """Um número que a pessoa não consegue auditar contra nenhuma tela é pior
    que número nenhum."""
    _, discursiva = _duas_fases(db, admin)
    conta = _conta(db, "aluno")
    linha = next(ln for ln in discursiva.linhas if "PESSOA A" in ln.nome)

    assert media_final_da_linha(linha, conta) is None
    assert media_final_da_linha(linha, admin) == (5.65, "copiada")


def test_a_contagem_do_inicio_nao_conta_a_2a_fase(client, db, admin, logar):
    """"Você aparece em 2 rankings" com 1 visível conta que existe um segundo."""
    _duas_fases(db, admin)
    conta = _conta(db, "aluno")
    _vincular(db, conta)
    logar(conta)

    corpo = client.get("/").get_data(as_text=True)

    assert ">2<" not in corpo or "ranking" not in corpo.lower()
    for marca in MARCAS_DA_2A_FASE:
        assert marca not in corpo


# --------------------------------------------------------------------------
# O admin: tudo continua funcionando, é assim que ele confere
# --------------------------------------------------------------------------


def test_o_admin_ve_a_prova_discursiva(client, db, admin, logar):
    _, discursiva = _duas_fases(db, admin)
    logar(admin)

    resposta = client.get(f"/simulados/turma/{discursiva.id}")

    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "2ª fase" in corpo
    assert "6.35" in corpo
    assert "final 5.65" in corpo


def test_o_admin_ve_as_duas_na_listagem(client, db, admin, logar):
    objetiva, discursiva = _duas_fases(db, admin)
    logar(admin)

    corpo = client.get("/simulados/turma/").get_data(as_text=True)

    assert f"/simulados/turma/{objetiva.id}" in corpo
    assert f"/simulados/turma/{discursiva.id}" in corpo


def test_o_admin_importa_normalmente(client, db, admin, logar):
    logar(admin)

    resposta = client.post(
        "/simulados/turma/importar",
        data={"payload": json.dumps(ITA_S5_DISCURSIVO), "acao": "confirmar"},
        follow_redirects=True,
    )

    assert resposta.status_code == 200
    prova = db.session.scalar(
        db.select(SimuladoTurma).filter_by(fase="discursiva")
    )
    assert prova is not None, "o admin precisa conseguir importar"


# --------------------------------------------------------------------------
# A porta de saída
# --------------------------------------------------------------------------


def test_a_reserva_esta_documentada_e_e_uma_constante(app):
    """Constante no código, não flag no banco: é estado do RECURSO inteiro, com
    condição de saída clara, e apagar código é mais fácil de revisar do que
    caçar uma flag."""
    import app.visibilidade as v

    assert FASES_RESERVADAS == frozenset({"discursiva"})
    assert "coordenação" in v.__doc__
    assert "FASES_RESERVADAS" in v.__doc__
