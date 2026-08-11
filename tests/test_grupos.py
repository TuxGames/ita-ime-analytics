"""Bloco 2: grupos — convite/aceite/saída, agregação sem tempo, período."""

import json
from datetime import date, timedelta

from app.grupo_evolucao import evolucao_do_grupo, membros_ativos
from app.models import Grupo, GrupoMembro, RegistroEstudo, SessaoTreino, Simulado, utcnow


def _criar_grupo(db, dono):
    grupo = Grupo(nome="Time de Física", criado_por=dono.id)
    db.session.add(grupo)
    db.session.flush()
    db.session.add(
        GrupoMembro(
            grupo_id=grupo.id, user_id=dono.id, status="ativo",
            convidado_em=utcnow(), respondido_em=utcnow(),
        )
    )
    db.session.commit()
    return grupo


def _convidar(db, grupo, usuario):
    membro = GrupoMembro(
        grupo_id=grupo.id, user_id=usuario.id, status="convidado", convidado_em=utcnow()
    )
    db.session.add(membro)
    db.session.commit()
    return membro


def _registro(db, usuario, dias_atras, questoes=10, acertos=7, materia="MATEMATICA"):
    from app.models import Materia

    db.session.add(
        RegistroEstudo(
            user_id=usuario.id,
            data=date.today() - timedelta(days=dias_atras),
            materia=Materia[materia],
            questoes=questoes,
            acertos=acertos,
        )
    )
    db.session.commit()


# --------------------------------------------------------------------------
# Convite / aceite / saída — o requisito central do bloco
# --------------------------------------------------------------------------


def test_convidado_nao_aparece_ate_aceitar(app, db, admin, criar_usuario):
    convidado = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, convidado)
    _registro(db, convidado, dias_atras=1)

    dados = evolucao_do_grupo(grupo, "semana")
    assert convidado.username not in [m["username"] for m in dados["membros"]]

    membro.status = "ativo"
    membro.respondido_em = utcnow()
    db.session.commit()

    dados = evolucao_do_grupo(grupo, "semana")
    assert convidado.username in [m["username"] for m in dados["membros"]]


def test_quem_sai_some_na_hora(app, db, admin, criar_usuario):
    membro_user = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, membro_user)
    membro.status = "ativo"
    db.session.commit()
    _registro(db, membro_user, dias_atras=1)

    assert membro_user.username in [m["username"] for m in evolucao_do_grupo(grupo, "semana")["membros"]]

    membro.status = "saiu"
    membro.respondido_em = utcnow()
    db.session.commit()

    dados = evolucao_do_grupo(grupo, "semana")
    assert membro_user.username not in [m["username"] for m in dados["membros"]]
    assert len(membros_ativos(grupo)) == 1  # só o dono


# --------------------------------------------------------------------------
# Nunca expor tempo
# --------------------------------------------------------------------------


def test_evolucao_do_membro_nao_traz_campo_de_tempo(app, db, admin, criar_usuario):
    membro_user = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, membro_user)
    membro.status = "ativo"
    db.session.commit()
    _registro(db, membro_user, dias_atras=1)
    # SessaoTreino tem tempo_total_seg — se o grupo puxasse dela, vazaria.
    db.session.add(
        SessaoTreino(user_id=membro_user.id, data=date.today(), questoes=20, tempo_total_seg=3600)
    )
    db.session.commit()

    dados = evolucao_do_grupo(grupo, "semana")
    bruto = json.dumps(dados)
    assert "tempo" not in bruto.lower()
    assert "3600" not in bruto


def test_rota_detalhe_grupo_nao_expoe_tempo(app, db, admin, criar_usuario, client, logar):
    grupo = _criar_grupo(db, admin)
    db.session.add(SessaoTreino(user_id=admin.id, data=date.today(), questoes=20, tempo_total_seg=3600))
    db.session.commit()

    logar(admin)
    resposta = client.get(f"/grupos/{grupo.id}")
    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True).lower()
    assert "3600" not in corpo
    assert "tempo_total" not in corpo


# --------------------------------------------------------------------------
# Período
# --------------------------------------------------------------------------


def _dias_atras_na_semana() -> int:
    """Offset que cai dentro da semana-calendário atual (desta segunda até hoje).

    A janela "semana" é semana-calendário de propósito (ver
    `app.grupo_evolucao.intervalo_do_periodo`). Toda segunda-feira a semana só
    tem o próprio dia, então "1 dia atrás" era domingo — semana passada — e o
    teste quebrava sozinho uma vez por semana. Segunda vira 0, resto do tempo 1.
    """
    return min(1, date.today().weekday())


def test_trocar_periodo_muda_numeros(app, db, admin, criar_usuario):
    grupo = _criar_grupo(db, admin)
    # Nunca 20: a semana tem no máximo 7 dias, então 20 fica sempre fora dela
    # e sempre dentro dos 30 dias, em qualquer dia em que a suíte rode.
    _registro(db, admin, dias_atras=_dias_atras_na_semana(), questoes=5)
    _registro(db, admin, dias_atras=20, questoes=8)  # fora da semana, dentro de 30 dias

    semana = evolucao_do_grupo(grupo, "semana")
    trinta = evolucao_do_grupo(grupo, "30dias")

    dono_semana = next(m for m in semana["membros"] if m["user_id"] == admin.id)
    dono_30 = next(m for m in trinta["membros"] if m["user_id"] == admin.id)
    assert dono_semana["questoes_totais"] == 5
    assert dono_30["questoes_totais"] == 13


# --------------------------------------------------------------------------
# Apagar grupo não mexe em dado de estudo
# --------------------------------------------------------------------------


def test_apagar_grupo_nao_remove_registro_nem_simulado_nem_sessao(app, db, admin, criar_usuario):
    grupo = _criar_grupo(db, admin)
    _registro(db, admin, dias_atras=1)
    db.session.add(SessaoTreino(user_id=admin.id, data=date.today(), questoes=5, tempo_total_seg=300))
    db.session.commit()

    reg_antes = db.session.scalar(db.select(db.func.count(RegistroEstudo.id)))
    sessao_antes = db.session.scalar(db.select(db.func.count(SessaoTreino.id)))

    db.session.delete(grupo)
    db.session.commit()

    assert db.session.scalar(db.select(db.func.count(Grupo.id))) == 0
    assert db.session.scalar(db.select(db.func.count(GrupoMembro.id))) == 0
    assert db.session.scalar(db.select(db.func.count(RegistroEstudo.id))) == reg_antes
    assert db.session.scalar(db.select(db.func.count(SessaoTreino.id))) == sessao_antes


# --------------------------------------------------------------------------
# Rotas: fluxo completo de convite
# --------------------------------------------------------------------------


def test_rota_convidar_cria_membro_pendente(app, db, admin, criar_usuario, client, logar):
    convidado = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)

    logar(admin)
    resposta = client.post(f"/grupos/{grupo.id}/convidar", data={"username": "bob"})
    assert resposta.status_code == 302

    membro = db.session.scalar(
        db.select(GrupoMembro).filter_by(grupo_id=grupo.id, user_id=convidado.id)
    )
    assert membro.status == "convidado"


def test_rota_detalhe_mostra_convite_para_quem_ainda_nao_aceitou(app, db, admin, criar_usuario, client, logar):
    convidado = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    _convidar(db, grupo, convidado)

    logar(convidado)
    resposta = client.get(f"/grupos/{grupo.id}")
    assert b"Convite" in resposta.data


def test_rota_aceitar_marca_membro_ativo(app, db, admin, criar_usuario, client, logar):
    convidado = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, convidado)

    logar(convidado)
    resposta = client.post(f"/grupos/{grupo.id}/aceitar")
    assert resposta.status_code == 302
    db.session.refresh(membro)
    assert membro.status == "ativo"


def test_rota_sair_marca_saiu_e_bloqueia_acesso_depois(app, db, admin, criar_usuario, client, logar):
    membro_user = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, membro_user)
    membro.status = "ativo"
    db.session.commit()

    logar(membro_user)
    resposta = client.post(f"/grupos/{grupo.id}/sair")
    assert resposta.status_code == 302
    db.session.refresh(membro)
    assert membro.status == "saiu"

    resposta = client.get(f"/grupos/{grupo.id}")
    assert resposta.status_code == 404


def test_convidar_de_novo_reabre_sem_violar_unique(app, db, admin, criar_usuario, client, logar):
    convidado = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, convidado)
    membro.status = "saiu"
    membro.respondido_em = utcnow()
    db.session.commit()

    logar(admin)
    resposta = client.post(f"/grupos/{grupo.id}/convidar", data={"username": "bob"})
    assert resposta.status_code == 302

    total = db.session.scalar(
        db.select(db.func.count(GrupoMembro.id)).filter_by(grupo_id=grupo.id, user_id=convidado.id)
    )
    assert total == 1
    db.session.refresh(membro)
    assert membro.status == "convidado"


def test_dono_remove_membro(app, db, admin, criar_usuario, client, logar):
    membro_user = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, membro_user)
    membro.status = "ativo"
    db.session.commit()

    logar(admin)
    resposta = client.post(f"/grupos/{grupo.id}/membro/{membro.id}/remover")
    assert resposta.status_code == 302
    assert db.session.get(GrupoMembro, membro.id) is None


def test_usuario_comum_nao_convida_nem_apaga(app, db, admin, criar_usuario, client, logar):
    membro_user = criar_usuario("bob")
    grupo = _criar_grupo(db, admin)
    membro = _convidar(db, grupo, membro_user)
    membro.status = "ativo"
    db.session.commit()

    logar(membro_user)
    assert client.post(f"/grupos/{grupo.id}/convidar", data={"username": "bob"}).status_code == 403
    assert client.post(f"/grupos/{grupo.id}/apagar").status_code == 403
