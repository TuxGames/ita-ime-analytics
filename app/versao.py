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

Foi assim que se chegou no 2.4.00: depois do redesign entraram o casamento de
banca com fase (2.1), os grupos de estudo (2.2), o lote de monograma, renomear
grupo e placar de notas (2.3), e agora o redesign das 29 telas restantes —
lote novo, então o segundo sobe e o terceiro volta para `00`.

O `2.4.01` nunca chegou a existir: ficou reservado para a correção da nota do
simulado, que ficou parada esperando o levantamento de produção. Quando ela
saiu, o `2.4.02` (redundância em Oficiais) já estava publicado, e versão não
anda para trás — então a correção da nota saiu no `2.4.03`.

Um único lugar: quem precisar da versão importa daqui. No Jinja ela chega como
o global `VERSAO`, registrado em app/__init__.py.
"""

VERSAO = "2.4.03"
