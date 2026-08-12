"""Ressincronizar simulado quando o ranking de origem é corrigido.

O "Sincronizar" só adiciona. Quando o admin conserta um ranking já importado,
quem tinha trazido aquela prova ficava com o número velho para sempre. Aqui o
registro é atualizado — mas só o que veio de import, só o que de fato divergiu,
e nunca a observação, que é do usuário.
"""

import json

from app.models import Concurso, Simulado, SimuladoTurma, SimuladoTurmaLinha
from app.simulado_sync import (
    diferencas_do_simulado,
    ressincronizar_simulado,
    simulados_desatualizados,
    sincronizar_linha,
)
from app.simulado_turma_import import aplicar, parse

from .conftest import payload_simulado

SENHA = "senha-de-teste-123"


def _importar(db, admin, **ajustes):
    dados = payload_simulado("novata", **ajustes)
    aplicar(db, parse(json.dumps(dados)), admin.id)
    db.session.commit()
    return db.session.scalar(db.select(SimuladoTurma))


def _concurso(db, admin, nome="ITA - 1ª Fase"):
    from datetime import date, timedelta

    c = Concurso(
        nome=nome,
        data_prova=date.today() + timedelta(days=100),
        created_by=admin.id,
        materias_csv="MATEMATICA,FISICA,QUIMICA",
    )
    db.session.add(c)
    db.session.commit()
    return c


def _trazer(db, turma, concurso, usuario):
    """Vincula o usuário à primeira linha e traz a prova para o perfil dele."""
    linha = db.session.scalar(
        db.select(SimuladoTurmaLinha).filter_by(turma_id=turma.id).order_by(SimuladoTurmaLinha.id)
    )
    linha.user_id = usuario.id
    db.session.commit()
    simulado = sincronizar_linha(linha, concurso, usuario.id)
    db.session.commit()
    return linha, simulado


def _corrigir_acertos(db, linha, materia, valor):
    """Simula o admin consertando o ranking: muda um acerto da linha.

    `acertos` é propriedade de leitura sobre `acertos_json`; a edição real
    (rota turma_linha_editar) também grava no JSON.
    """
    acertos = dict(linha.acertos)
    acertos[materia] = valor
    linha.acertos_json = json.dumps(acertos)
    db.session.commit()


# --------------------------------------------------------------------------
# Detecção da divergência
# --------------------------------------------------------------------------


def test_sem_mudanca_no_ranking_nao_ha_o_que_ressincronizar(app, db, admin):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    _trazer(db, turma, concurso, admin)

    assert simulados_desatualizados(admin.id) == []


def test_correcao_no_ranking_vira_divergencia(app, db, admin):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    nota_antes = simulado.nota_geral

    _corrigir_acertos(db, linha, "MATEMATICA", 12)

    pendentes = simulados_desatualizados(admin.id)
    assert len(pendentes) == 1
    campos = {m["campo"] for m in pendentes[0]["mudancas"]}
    assert "Nota" in campos
    assert "Matemática" in campos
    # O preview mostra valor a valor, nunca só "mudou".
    nota = next(m for m in pendentes[0]["mudancas"] if m["campo"] == "Nota")
    assert nota["de"] == nota_antes and nota["para"] != nota_antes
    mat = next(m for m in pendentes[0]["mudancas"] if m["campo"] == "Matemática")
    assert mat["de"] == "9/12" and mat["para"] == "12/12"


def test_registro_manual_nunca_entra(app, db, admin):
    """Digitado à mão não é candidato, nem se apontar para uma linha."""
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    _corrigir_acertos(db, linha, "MATEMATICA", 12)

    simulado.origem = "manual"
    db.session.commit()

    assert simulados_desatualizados(admin.id) == []
    assert ressincronizar_simulado(simulado) is False


def test_simulado_sem_linha_de_origem_nao_entra(app, db, admin):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    _corrigir_acertos(db, linha, "MATEMATICA", 12)

    simulado.turma_linha_id = None
    db.session.commit()

    assert simulados_desatualizados(admin.id) == []
    assert ressincronizar_simulado(simulado) is False


# --------------------------------------------------------------------------
# A gravação
# --------------------------------------------------------------------------


def test_ressincronizar_atualiza_nota_e_materias(app, db, admin):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    _corrigir_acertos(db, linha, "MATEMATICA", 12)

    assert ressincronizar_simulado(simulado) is True
    db.session.commit()

    acertos = {m.materia.name: m.acertos for m in simulado.materias}
    assert acertos["MATEMATICA"] == 12
    assert simulados_desatualizados(admin.id) == [], "depois de gravar, nada pendente"


def test_observacao_do_usuario_sobrevive(app, db, admin):
    """A regra que mais importa: a observação é dele, não do import."""
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    simulado.observacao = "Errei por falta de tempo na última questão."
    db.session.commit()

    _corrigir_acertos(db, linha, "MATEMATICA", 12)
    ressincronizar_simulado(simulado)
    db.session.commit()

    assert simulado.observacao == "Errei por falta de tempo na última questão."


def test_ressincronizar_nao_duplica_simulado(app, db, admin):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    _corrigir_acertos(db, linha, "MATEMATICA", 12)

    antes = db.session.scalar(db.select(db.func.count(Simulado.id)))
    ressincronizar_simulado(simulado)
    db.session.commit()

    assert db.session.scalar(db.select(db.func.count(Simulado.id))) == antes


def test_so_mexe_no_simulado_de_quem_pediu(app, db, admin, criar_usuario):
    """Duas pessoas na mesma prova: ressincronizar uma não toca na outra."""
    bob = criar_usuario("bob")
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)

    linhas = db.session.scalars(
        db.select(SimuladoTurmaLinha).filter_by(turma_id=turma.id).order_by(SimuladoTurmaLinha.id)
    ).all()
    linhas[0].user_id = admin.id
    linhas[1].user_id = bob.id
    db.session.commit()
    sim_admin = sincronizar_linha(linhas[0], concurso, admin.id)
    sim_bob = sincronizar_linha(linhas[1], concurso, bob.id)
    db.session.commit()
    nota_bob = sim_bob.nota_geral

    _corrigir_acertos(db, linhas[0], "MATEMATICA", 12)
    ressincronizar_simulado(sim_admin)
    db.session.commit()

    assert sim_bob.nota_geral == nota_bob
    assert simulados_desatualizados(bob.id) == []


# --------------------------------------------------------------------------
# A tela
# --------------------------------------------------------------------------


def test_tela_lista_o_que_mudou(client, db, admin, logar):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    _corrigir_acertos(db, linha, "MATEMATICA", 12)
    logar(admin)

    corpo = client.get("/simulados/ressincronizar").get_data(as_text=True)

    assert "9/12" in corpo and "12/12" in corpo, "mostra de -> para"
    # Deixa explícito que mexe em registro que já está no perfil.
    assert "já est" in corpo.lower()


def test_tela_vazia_quando_nada_divergiu(client, db, admin, logar):
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    _trazer(db, turma, concurso, admin)
    logar(admin)

    corpo = client.get("/simulados/ressincronizar").get_data(as_text=True)

    assert "em dia" in corpo.lower()


def test_post_so_atualiza_o_que_foi_marcado(client, db, admin, logar):
    """Preview obrigatório: sem marcar, nada muda."""
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    nota_antes = simulado.nota_geral
    _corrigir_acertos(db, linha, "MATEMATICA", 12)
    logar(admin)

    client.post("/simulados/ressincronizar", data={})
    assert db.session.get(Simulado, simulado.id).nota_geral == nota_antes

    client.post("/simulados/ressincronizar", data={f"sim_{simulado.id}": "y"})
    assert db.session.get(Simulado, simulado.id).nota_geral != nota_antes


def test_nao_ressincroniza_simulado_de_outro_usuario(client, db, admin, criar_usuario, logar):
    bob = criar_usuario("bob")
    turma = _importar(db, admin)
    concurso = _concurso(db, admin)
    linha, simulado = _trazer(db, turma, concurso, admin)
    nota_antes = simulado.nota_geral
    _corrigir_acertos(db, linha, "MATEMATICA", 12)

    logar(bob)
    client.post("/simulados/ressincronizar", data={f"sim_{simulado.id}": "y"})

    assert db.session.get(Simulado, simulado.id).nota_geral == nota_antes
