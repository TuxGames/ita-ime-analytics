"""O monograma chega mesmo nas telas de lista de gente.

Cobre o que o teste de unidade não pega: import do macro, nome do global no
Jinja e a classe de cor no HTML. Sem isso, um erro de template só apareceria
em produção.
"""

import json
import re

from app.models import Grupo, GrupoMembro, SimuladoTurma, utcnow
from app.monograma import indice_de_cor
from app.simulado_turma_import import aplicar, parse

from .conftest import payload_simulado


def _parse(payload):
    return parse(json.dumps(payload))


def _mono(corpo, nome):
    """O monograma daquele nome específico está no HTML?"""
    return f'mono-c{indice_de_cor(nome)}' in corpo


def test_ranking_da_turma_mostra_monograma(client, db, admin, logar):
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()
    prova = db.session.scalar(db.select(SimuladoTurma))
    logar(admin)

    corpo = client.get(f"/simulados/turma/{prova.id}").get_data(as_text=True)

    assert 'class="mono mono-sm' in corpo
    assert _mono(corpo, "ALUNO NOVATA UM")
    # Sem style inline: a CSP do projeto é 'self' e bloquearia.
    assert not re.search(r'class="mono[^"]*"[^>]*style=', corpo)


def test_perfil_mostra_monograma_grande(client, db, admin, logar):
    admin.nome_oficial = "MARCUS VINICIUS BERNARDINO DE OLIVEIRA MELO COELHO"
    db.session.commit()
    logar(admin)

    corpo = client.get("/perfil").get_data(as_text=True)

    assert 'class="mono mono-lg' in corpo
    assert _mono(corpo, admin.nome_oficial)
    assert ">MC<" in corpo, "iniciais do nome declarado, não do username"


def test_grupo_mostra_monograma_dos_membros(client, db, admin, criar_usuario, logar):
    bob = criar_usuario("bob", nome_oficial="ROBERTO DA SILVA CARVALHO")
    grupo = Grupo(nome="Time de Física", criado_por=admin.id)
    db.session.add(grupo)
    db.session.flush()
    for u in (admin, bob):
        db.session.add(
            GrupoMembro(
                grupo_id=grupo.id, user_id=u.id, status="ativo",
                convidado_em=utcnow(), respondido_em=utcnow(),
            )
        )
    db.session.commit()
    logar(admin)

    corpo = client.get(f"/grupos/{grupo.id}").get_data(as_text=True)

    assert 'class="mono mono-sm' in corpo
    assert _mono(corpo, bob.nome_oficial), "usa o nome real, não o username"
    assert ">RC<" in corpo


def test_mesma_pessoa_mesma_cor_em_telas_diferentes(client, db, admin, logar):
    """O ponto do recurso: reconhecer a pessoa de uma tela para a outra."""
    admin.nome_oficial = "ALUNO NOVATA UM"
    aplicar(db, _parse(payload_simulado("novata")), admin.id)
    db.session.commit()
    prova = db.session.scalar(db.select(SimuladoTurma))
    logar(admin)

    ranking = client.get(f"/simulados/turma/{prova.id}").get_data(as_text=True)
    perfil = client.get("/perfil").get_data(as_text=True)

    classe = f"mono-c{indice_de_cor('ALUNO NOVATA UM')}"
    assert classe in ranking and classe in perfil
