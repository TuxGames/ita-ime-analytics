"""Placar de notas dentro do grupo — opcional, ligado pelo dono."""

from datetime import date, timedelta

from app.grupo_evolucao import nota_do_simulado, ranking_de_notas
from app.models import (
    Concurso,
    Grupo,
    GrupoMembro,
    Materia,
    Simulado,
    SimuladoMateria,
    utcnow,
)


def _dias_atras_na_semana() -> int:
    """Offset dentro da semana-calendário — na segunda ela só tem o próprio dia."""
    return min(1, date.today().weekday())


def _concurso(db, admin):
    c = Concurso(
        nome="ITA 2027", created_by=admin.id, data_prova=date.today() + timedelta(days=200)
    )
    db.session.add(c)
    db.session.commit()
    return c


def _simulado(db, usuario, concurso, acertos_por_materia, dias_atras=None, nota_geral=0.0):
    """Um simulado com detalhamento por matéria: {Materia: (acertos, total)}."""
    if dias_atras is None:
        dias_atras = _dias_atras_na_semana()
    s = Simulado(
        user_id=usuario.id,
        concurso_id=concurso.id,
        data_simulado=date.today() - timedelta(days=dias_atras),
        nota_geral=nota_geral,
    )
    db.session.add(s)
    db.session.flush()
    for materia, (acertos, total) in acertos_por_materia.items():
        db.session.add(
            SimuladoMateria(
                simulado_id=s.id, materia=materia, acertos=acertos, total_questoes=total
            )
        )
    db.session.commit()
    return s


def _grupo(db, dono, *membros):
    g = Grupo(nome="Time", criado_por=dono.id)
    db.session.add(g)
    db.session.flush()
    for u in (dono, *membros):
        db.session.add(
            GrupoMembro(
                grupo_id=g.id, user_id=u.id, status="ativo",
                convidado_em=utcnow(), respondido_em=utcnow(),
            )
        )
    db.session.commit()
    return g


# --------------------------------------------------------------------------
# A conta da nota
# --------------------------------------------------------------------------


def test_nota_e_proporcional_as_questoes(app, db, admin):
    """Mesma regra do ranking da turma: IME 26/40 -> 6,50, não média simples."""
    concurso = _concurso(db, admin)
    s = _simulado(db, admin, concurso, {
        Materia.MATEMATICA: (11, 15),
        Materia.FISICA: (11, 15),
        Materia.QUIMICA: (4, 10),
    })

    assert nota_do_simulado(s) == 6.5


def test_nota_respeita_o_filtro_de_materias(app, db, admin):
    concurso = _concurso(db, admin)
    s = _simulado(db, admin, concurso, {
        Materia.MATEMATICA: (10, 10),
        Materia.FISICA: (0, 10),
    })

    assert nota_do_simulado(s) == 5.0
    assert nota_do_simulado(s, [Materia.MATEMATICA]) == 10.0
    assert nota_do_simulado(s, [Materia.FISICA]) == 0.0


def test_simulado_sem_detalhe_usa_nota_geral_mas_some_com_filtro(app, db, admin):
    """Digitado à mão só tem nota_geral: serve sem filtro, mas com filtro não dá
    para honrar o recorte, então a prova fica de fora."""
    concurso = _concurso(db, admin)
    s = _simulado(db, admin, concurso, {}, nota_geral=8.0)

    assert nota_do_simulado(s) == 8.0
    assert nota_do_simulado(s, [Materia.MATEMATICA]) is None


# --------------------------------------------------------------------------
# O placar
# --------------------------------------------------------------------------


def test_placar_ordena_e_renumera_dentro_do_grupo(app, db, admin, criar_usuario):
    bob = criar_usuario("bob")
    concurso = _concurso(db, admin)
    _simulado(db, admin, concurso, {Materia.MATEMATICA: (5, 10)})   # 5,00
    _simulado(db, bob, concurso, {Materia.MATEMATICA: (9, 10)})     # 9,00
    grupo = _grupo(db, admin, bob)

    dados = ranking_de_notas(grupo, "semana")

    assert [p["posicao"] for p in dados["placar"]] == [1, 2]
    assert [p["username"] for p in dados["placar"]] == ["bob", "admin"]
    assert dados["placar"][0]["media"] == 9.0


def test_empate_fica_na_mesma_posicao(app, db, admin, criar_usuario):
    bob = criar_usuario("bob")
    concurso = _concurso(db, admin)
    _simulado(db, admin, concurso, {Materia.MATEMATICA: (7, 10)})
    _simulado(db, bob, concurso, {Materia.MATEMATICA: (7, 10)})
    grupo = _grupo(db, admin, bob)

    dados = ranking_de_notas(grupo, "semana")

    assert [p["posicao"] for p in dados["placar"]] == [1, 1]


def test_quem_nao_fez_simulado_fica_fora_do_placar(app, db, admin, criar_usuario):
    bob = criar_usuario("bob")
    concurso = _concurso(db, admin)
    _simulado(db, admin, concurso, {Materia.MATEMATICA: (7, 10)})
    grupo = _grupo(db, admin, bob)

    dados = ranking_de_notas(grupo, "semana")

    assert [p["username"] for p in dados["placar"]] == ["admin"]
    assert [p["username"] for p in dados["sem_nota"]] == ["bob"]


def test_placar_respeita_o_periodo(app, db, admin):
    concurso = _concurso(db, admin)
    _simulado(db, admin, concurso, {Materia.MATEMATICA: (9, 10)})
    _simulado(db, admin, concurso, {Materia.MATEMATICA: (1, 10)}, dias_atras=20)
    grupo = _grupo(db, admin)

    semana = ranking_de_notas(grupo, "semana")
    trinta = ranking_de_notas(grupo, "30dias")

    assert semana["placar"][0]["media"] == 9.0, "só o simulado da semana"
    assert trinta["placar"][0]["media"] == 5.0, "média dos dois"


def test_convidado_nao_entra_no_placar(app, db, admin, criar_usuario):
    """Mesma regra do resto do grupo: só quem aceitou aparece."""
    bob = criar_usuario("bob")
    concurso = _concurso(db, admin)
    _simulado(db, bob, concurso, {Materia.MATEMATICA: (10, 10)})
    grupo = _grupo(db, admin)
    db.session.add(
        GrupoMembro(grupo_id=grupo.id, user_id=bob.id, status="convidado", convidado_em=utcnow())
    )
    db.session.commit()

    dados = ranking_de_notas(grupo, "semana")

    assert "bob" not in [p["username"] for p in dados["placar"]]
    assert "bob" not in [p["username"] for p in dados["sem_nota"]]


# --------------------------------------------------------------------------
# A opção do dono
# --------------------------------------------------------------------------


def test_grupo_novo_nasce_sem_placar(app, db, admin, client, logar):
    """Default False: ninguém passa a ver placar sem pedir."""
    logar(admin)
    client.post("/grupos/novo", data={"nome": "Time"})

    grupo = db.session.scalar(db.select(Grupo))
    assert grupo.mostrar_ranking is False


def test_tela_so_mostra_placar_quando_ligado(app, db, admin, client, logar):
    concurso = _concurso(db, admin)
    _simulado(db, admin, concurso, {Materia.MATEMATICA: (7, 10)})
    grupo = _grupo(db, admin)
    logar(admin)

    corpo = client.get(f"/grupos/{grupo.id}").get_data(as_text=True)
    assert "Placar de notas" not in corpo

    grupo.mostrar_ranking = True
    db.session.commit()

    corpo = client.get(f"/grupos/{grupo.id}").get_data(as_text=True)
    assert "Placar de notas" in corpo
    assert "7.00" in corpo


def test_dono_liga_e_desliga_pela_tela_de_edicao(app, db, admin, client, logar):
    grupo = _grupo(db, admin)
    logar(admin)

    client.post(f"/grupos/{grupo.id}/editar", data={"nome": "Time", "mostrar_ranking": "y"})
    assert db.session.get(Grupo, grupo.id).mostrar_ranking is True

    # Checkbox ausente no POST = desmarcado.
    client.post(f"/grupos/{grupo.id}/editar", data={"nome": "Time"})
    assert db.session.get(Grupo, grupo.id).mostrar_ranking is False


def test_membro_comum_nao_liga_o_placar(app, db, admin, criar_usuario, client, logar):
    bob = criar_usuario("bob")
    grupo = _grupo(db, admin, bob)
    logar(bob)

    assert client.post(
        f"/grupos/{grupo.id}/editar", data={"nome": "Meu", "mostrar_ranking": "y"}
    ).status_code == 403
    assert db.session.get(Grupo, grupo.id).mostrar_ranking is False
