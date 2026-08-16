"""Papel de professor: vê nota, nunca vê estudo.

A linha: nota de simulado o colégio já distribui para a turma inteira, então a
ficha é conveniência sobre dado que circula. Registro de estudo, treino e grupo
a pessoa digitou aqui achando que era dela — se vazar, ela para de registrar.

O jeito de errar isto é vazamento por reaproveitamento, então há um teste que
varre a ficha inteira atrás de qualquer resquício de dado privado.
"""

import json
from datetime import date, timedelta

import pytest

from app.ficha import (
    CAMPOS_DA_LISTA,
    CAMPOS_PERMITIDOS,
    alunos_para_ficha,
    ficha_do_aluno,
)
from app.models import (
    Aluno,
    Grupo,
    GrupoMembro,
    Materia,
    RegistroEstudo,
    SessaoTreino,
    User,
    utcnow,
)
from app.oficiais_import import aplicar as aplicar_of, parse as parse_of
from app.simulado_turma_import import aplicar as aplicar_tur, parse as parse_tur

from .conftest import payload_oficial, payload_simulado

SENHA = "senha-de-teste-123"

# Valores plantados no dado PRIVADO do aluno. Se qualquer um aparecer na ficha,
# houve vazamento — são improváveis o bastante para não colidir com nota.
MARCA_ESTUDO = 4242
MARCA_TREINO = 31337
MARCA_OBS = "SEGREDO-DO-ALUNO-NAO-PODE-VAZAR"
MARCA_GRUPO = "GRUPO-PRIVADO-DO-ALUNO"


def _professor(db, username="prof"):
    u = User(username=username, is_admin=False, is_professor=True,
             must_change_password=False, convite_ok=False)
    u.set_password(SENHA)
    db.session.add(u)
    db.session.commit()
    return u


def _aluno_com_tudo(db, admin):
    """Aluno com desempenho E com dado privado, para o teste de vazamento."""
    aplicar_tur(db, parse_tur(json.dumps(payload_simulado("novata"))), admin.id)
    aplicar_of(db, parse_of(json.dumps(payload_oficial("novata"))), admin.id)
    db.session.commit()

    aluno = db.session.scalar(db.select(Aluno).order_by(Aluno.id))
    dono = User(username="dono_da_ficha", must_change_password=False, convite_ok=True)
    dono.set_password(SENHA)
    db.session.add(dono)
    db.session.commit()
    aluno.user_id = dono.id
    aluno.vinculo_por_codigo = True

    # --- dado PRIVADO, que a ficha não pode tocar ---
    db.session.add(RegistroEstudo(user_id=dono.id, data=date.today(),
                                  materia=Materia.MATEMATICA,
                                  questoes=MARCA_ESTUDO, acertos=1))
    db.session.add(SessaoTreino(user_id=dono.id, data=date.today(), questoes=7,
                                tempo_total_seg=MARCA_TREINO, observacao=MARCA_OBS))
    grupo = Grupo(nome=MARCA_GRUPO, criado_por=dono.id)
    db.session.add(grupo)
    db.session.flush()
    db.session.add(GrupoMembro(grupo_id=grupo.id, user_id=dono.id, status="ativo",
                               convidado_em=utcnow(), respondido_em=utcnow()))
    db.session.commit()
    return aluno, dono


# --------------------------------------------------------------------------
# O que a ficha carrega — e o que ela NUNCA pode carregar
# --------------------------------------------------------------------------


def test_ficha_so_tem_os_campos_da_lista_branca(app, db, admin):
    aluno, _ = _aluno_com_tudo(db, admin)

    dados = ficha_do_aluno(aluno)

    assert set(dados) == CAMPOS_PERMITIDOS, (
        "campo novo na ficha: confirme que não é dado privado antes de liberar"
    )


def test_a_lista_de_alunos_tambem_e_so_identificacao(app, db, admin):
    """A lista e o lugar mais facil de esquecer: ela "so mostra nome".

    Se voltar a entregar o `Aluno` do ORM, o template ganha `a.user` e daí um
    caminho para estudo e treino sem ninguém escrever uma linha nova de query.
    """
    _aluno_com_tudo(db, admin)

    lista = alunos_para_ficha()

    assert lista, "tem que listar os alunos"
    for item in lista:
        assert isinstance(item, dict), "objeto do ORM na lista abre caminho para a.user"
        assert set(item) == CAMPOS_DA_LISTA


def test_ficha_nao_carrega_dado_privado(app, db, admin):
    """A guarda que segura isto daqui a seis meses.

    Serializa a ficha INTEIRA e procura as marcas plantadas em estudo, treino,
    observação e grupo. Falha se qualquer uma aparecer, não importa por qual
    caminho tenha entrado.
    """
    aluno, _ = _aluno_com_tudo(db, admin)

    bruto = json.dumps(ficha_do_aluno(aluno), default=str)

    for marca in (MARCA_ESTUDO, MARCA_TREINO, MARCA_OBS, MARCA_GRUPO):
        assert str(marca) not in bruto, f"vazou {marca!r} para a ficha"
    for palavra in ("tempo_total", "questoes_totais", "sessao", "treino", "grupo"):
        assert palavra not in bruto.lower(), f"a ficha carrega {palavra!r}"


def test_a_tela_da_ficha_nao_mostra_dado_privado(client, db, admin, logar):
    aluno, _ = _aluno_com_tudo(db, admin)
    logar(_professor(db))

    corpo = client.get(f"/professor/aluno/{aluno.id}").get_data(as_text=True)

    for marca in (str(MARCA_ESTUDO), str(MARCA_TREINO), MARCA_OBS, MARCA_GRUPO):
        assert marca not in corpo, f"vazou {marca!r} para a tela"


def test_ficha_reusa_o_calculo_de_evolucao(app, db, admin):
    """Um segundo cálculo divergiria do primeiro sem ninguém saber qual vale."""
    from app.evolucao import evolucao_do_aluno

    aluno, _ = _aluno_com_tudo(db, admin)

    assert ficha_do_aluno(aluno)["evolucao"] == evolucao_do_aluno(aluno.id, None)


def test_ficha_traz_desempenho_de_verdade(app, db, admin):
    aluno, _ = _aluno_com_tudo(db, admin)

    dados = ficha_do_aluno(aluno)

    assert dados["nome"] == aluno.nome
    assert dados["simulados"], "tem que trazer os simulados"
    assert dados["simulados"][0]["nota"] is not None
    assert dados["resumo"]["provas"] >= 1


def test_ficha_traz_os_oficiais(app, db, admin):
    """Nas fixtures, ranking e listão usam nomes diferentes, então o aluno com
    oficiais é outro — por isso a checagem é separada."""
    from app.models import ResultadoLinha

    _aluno_com_tudo(db, admin)
    linha = db.session.scalar(
        db.select(ResultadoLinha).filter(ResultadoLinha.aluno_id.isnot(None))
    )
    assert linha is not None, "o import de oficial precisa casar o aluno"

    dados = ficha_do_aluno(db.session.get(Aluno, linha.aluno_id))

    assert dados["oficiais"], "tem que trazer os oficiais"
    assert dados["oficiais"][0]["concurso"]


# --------------------------------------------------------------------------
# O papel: só olha
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rota",
    ["/estudos/", "/estudos/treino", "/estudos/plano", "/estudos/registrar", "/grupos/"],
)
def test_professor_nao_acessa_area_privada_por_get(rota, client, db, logar):
    logar(_professor(db))

    resposta = client.get(rota)

    assert resposta.status_code == 403
    assert "privado" in resposta.get_data(as_text=True).lower()


@pytest.mark.parametrize(
    "rota", ["/estudos/treino/salvar", "/grupos/novo", "/grupos/1/sair"]
)
def test_professor_nao_acessa_area_privada_por_post(rota, client, db, logar):
    """Esconder do menu não basta: POST direto tem que recusar."""
    logar(_professor(db))

    assert client.post(rota).status_code == 403


@pytest.mark.parametrize(
    "rota",
    ["/admin/turmas", "/admin/convites", "/admin/merge", "/admin/deploy", "/admin/historico"],
)
def test_professor_nao_e_admin(rota, client, db, logar):
    logar(_professor(db))

    assert client.get(rota).status_code == 403


@pytest.mark.parametrize(
    "rota,dados",
    [
        ("/admin/convites/1/gerar", {}),
        ("/admin/convites/coringa", {"rotulo": "x"}),
        ("/admin/convites/1/vincular", {"user_id": 1}),
        ("/oficiais/importar", {}),
        ("/simulados/turma/importar", {}),
    ],
)
def test_professor_nao_escreve_nada(rota, dados, client, db, logar):
    """Só olha: não importa, não emite código, não vincula, não mescla."""
    logar(_professor(db))

    assert client.post(rota, data=dados).status_code == 403


def test_usuario_comum_nao_ve_ficha(client, db, usuario, logar):
    logar(usuario)

    assert client.get("/professor/").status_code == 403
    assert client.get("/professor/aluno/1").status_code == 403


def test_admin_tambem_ve_a_ficha(client, db, admin, logar):
    """Admin é dono do app; não faz sentido negar a ele o que o professor vê."""
    logar(admin)

    assert client.get("/professor/").status_code == 200


# --------------------------------------------------------------------------
# Visibilidade e estado da conta
# --------------------------------------------------------------------------


def test_professor_ve_ranking_e_oficiais_sem_codigo(client, db, admin, logar):
    """É o mesmo tipo de dado da ficha — o papel já autoriza."""
    _aluno_com_tudo(db, admin)
    prof = _professor(db)
    assert prof.convite_ok is False
    logar(prof)

    assert client.get("/simulados/turma/").status_code == 200
    assert client.get("/oficiais/").status_code == 200


def test_conta_de_professor_nao_tem_aluno_e_nada_quebra(client, db, admin, logar):
    """Mesmo caso da coringa: sem aluno, sem estado de erro."""
    _aluno_com_tudo(db, admin)
    prof = _professor(db)
    logar(prof)

    assert db.session.scalar(db.select(Aluno).filter_by(user_id=prof.id)) is None
    for rota in ("/", "/perfil", "/professor/", "/simulados/", "/evolucao", "/oficiais/"):
        resposta = client.get(rota)
        assert resposta.status_code == 200, f"{rota} -> {resposta.status_code}"
        corpo = resposta.get_data(as_text=True)
        assert "Traceback" not in corpo
        assert "Erro inesperado" not in corpo


def test_admin_marca_e_desmarca_professor(client, db, admin, logar):
    conta = User(username="futuro_prof", must_change_password=False, convite_ok=True)
    conta.set_password(SENHA)
    db.session.add(conta)
    db.session.commit()
    logar(admin)

    client.post(f"/admin/convites/professor/{conta.id}")
    assert db.session.get(User, conta.id).is_professor is True

    client.post(f"/admin/convites/professor/{conta.id}")
    assert db.session.get(User, conta.id).is_professor is False


def test_conta_nasce_sem_o_papel(app, db):
    """Ninguém vira professor por acidente."""
    u = User(username="novata", must_change_password=False)
    u.set_password(SENHA)
    db.session.add(u)
    db.session.commit()

    assert u.is_professor is False


def test_so_admin_marca_professor(client, db, usuario, logar):
    logar(usuario)

    assert client.post("/admin/convites/professor/1").status_code == 403


def test_professor_nao_promove_ninguem(client, db, logar):
    logar(_professor(db))

    assert client.post("/admin/convites/professor/1").status_code == 403


def test_ficha_de_aluno_inexistente_da_404(client, db, logar):
    logar(_professor(db))

    assert client.get("/professor/aluno/9999").status_code == 404


def test_menu_nao_oferece_o_que_a_rota_recusa(client, db, logar):
    """A rota fechada é a garantia; o menu é a cortesia.

    Oferecer "Estudos" para quem vai levar 403 ao clicar é convidar o professor
    a bater numa porta trancada. No lugar dele entra o que ele veio fazer.
    """
    logar(_professor(db))

    corpo = client.get("/").get_data(as_text=True)

    assert "/estudos/" not in corpo, "o menu ainda leva o professor para o 403"
    assert "/professor/" in corpo, "o professor precisa achar as fichas"


def test_menu_do_aluno_continua_igual(client, db, usuario, logar):
    """A troca é só para o papel — ninguém mais pode perder o menu."""
    logar(usuario)

    corpo = client.get("/").get_data(as_text=True)

    assert "/estudos/" in corpo
    assert "/professor/" not in corpo
