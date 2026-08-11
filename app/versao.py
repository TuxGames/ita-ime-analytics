"""Versão visível do app.

Formato: `x.y.NN`. Como numerar (para a próxima pessoa não ter que adivinhar):

- **Primeiro número**: mudança grande de identidade do app. O `2` começou no
  redesign do placar.
- **Segundo número**: sobe a cada LOTE de funcionalidade. Ao subir, o terceiro
  volta para `00`.
- **Terceiro número**: sobe a cada correção solta, SEMPRE com dois dígitos
  (`01`, `02`, ... `99`).

O zero à esquerda não é enfeite: é o que faz a versão ordenar certo como texto.
Sem ele, `2.3.2` viria DEPOIS de `2.3.18` em qualquer ordenação alfabética —
que é como versão acaba sendo comparada em nome de arquivo, log e listagem.

Foi assim que se chegou no 2.3.00: depois do redesign entraram o casamento de
banca com fase (2.1), os grupos de estudo (2.2), e agora o lote de monograma,
renomear grupo e placar de notas — lote novo, então o terceiro nasce em `00`.

Um único lugar: quem precisar da versão importa daqui. No Jinja ela chega como
o global `VERSAO`, registrado em app/__init__.py.
"""

VERSAO = "2.3.00"
