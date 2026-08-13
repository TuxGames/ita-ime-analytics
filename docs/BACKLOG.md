# Backlog — ITA-IME Analytics

Lista viva do que ficou para depois. Ordem dentro de cada seção é sugestão, não
compromisso. Atualizado em 10/08/2026.

---

## 1. Com prazo

- **Renovar o site no PythonAnywhere.** A aba Web avisa que ele será desativado
  em **5 de setembro de 2026**. Conta free precisa do clique em "Run until 1
  month from today". É o único item que derruba o app se ninguém fizer nada.

## 2. Em andamento

- **Login com sessão ativa.** Decisão tomada: exigir logout antes de trocar de
  conta, **mas sem redirecionar em silêncio**. `GET /login` passa a renderizar a
  página dizendo quem está logado, com botão de sair visível; `POST` não
  autentica e não derruba a sessão atual. Inclui reconciliar
  `tests/test_troca_de_usuario.py` (que fixava o redirect antigo como
  intencional) com `tests/test_troca_de_conta.py`.

## 3. Bugs conhecidos

- **`test_grupos.py::test_trocar_periodo_muda_numeros` falha só às
  segundas-feiras.** A janela "semana" é semana-calendário e o registro de
  "1 dia atrás" cai no domingo, que já é a semana anterior. Pré-existente, sem
  relação com sessão. É o tipo de teste que quebra sozinho e faz desconfiar da
  suíte inteira à toa.

- **`setup_pythonanywhere.sh` com quebra de linha CRLF.** Quebra se for
  executado no servidor (`$'\r': command not found`). Resolve com `dos2unix` ou
  normalizando o arquivo no repositório.

- **Botão Reload do PythonAnywhere não reinicia o worker.** Aconteceu em dois
  deploys seguidos: o código novo fica em disco e o processo segue o antigo.
  Contorno confiável: `touch /var/www/itaime_pythonanywhere_com_wsgi.py`.
  Regra que ficou: sempre verificar algo que **só existe na versão nova** antes
  de dar um deploy por concluído.

## 4. Dados

- **Mesclar alunos duplicados em produção.** A migration do Aluno criou 73
  registros a partir dos nomes crus, então variações conhecidas viraram pessoas
  diferentes: `MARCUS VINICIUS ... DE OLIVEIRA M` vs `... MELO COELHO`, e
  `DANIEL DOURADO OLIVEIRA XIMENES` vs `DANIEL DOURADO O. XIMENES`. A tela
  existe em `/admin/merge` e nunca foi usada em produção. Quanto mais import
  antes de limpar, mais espalha — é o que parte os gráficos de evolução.

- **Rodar `flask conferir-import` em produção** de vez em quando. O relatório já
  aponta série que regride, nome que aparece uma vez só, e pessoa em duas turmas.

## 5. Infraestrutura e higiene

- **Repositório privado no GitHub.** Hoje o código só existe nesta máquina. O
  git protege contra erro; não protege contra perder o disco.

- **Guardar a `SECRET_KEY` num gerenciador de senhas.** O `.env` está no
  `.gitignore` e fora de todos os backups, de propósito. Perder o disco é perder
  a chave, e com ela as sessões e o CSRF de produção.

- **`.gitattributes` com `* text=auto`.** Sem isso o `git status` mostra ~100
  arquivos modificados que diferem só em CRLF, e um `git add -A` distraído vira
  um commit de 14 mil linhas de ruído.

- **Limpeza da pasta:** `.ruff_cache/`, `tests/_dump_tmp.py`, `.venv.zip`
  (18 MB, de julho), `ita-ime-analytics-2.0.zip` (já aplicado), os zips de
  backup antigos na pasta pai, os `tmp_obj_*` em `.git/objects/`, e
  `.claude/worktrees/` (~63 MB de cópias de repositório deixadas por agentes).

- **Rotina de backup do banco de produção.** Hoje é manual, antes de cada
  deploy. O comando `flask backup` já existe — falta decidir se vira tarefa
  agendada no PythonAnywhere.

## 6. Funcionalidades futuras

- **Monograma no lugar de foto de perfil (primeiro passo).** Iniciais num
  círculo com cor derivada do nome. Custo zero de armazenamento e moderação, e
  funciona para **todos os 73 alunos**, inclusive quem nunca criou conta —
  diferente de foto, que só cobriria as 7 contas existentes.

- **Ícone escolhido pelo usuário (segundo passo, opcional).** Conjunto pronto de
  ícones, sem upload. Evita armazenamento, redimensionamento, validação de
  formato e moderação.

- **Upload de foto de verdade (provavelmente não).** Traz superfície de ataque
  clássica e consumo de disco no plano free. Só se houver motivo forte.

- **Dono do grupo poder renomear o grupo.** Hoje o nome é definido na criação e
  não muda mais.

- **Ranking de notas dentro do grupo**, com o **dono escolhendo se aparece ou
  não** — grupo que quer só acompanhar volume de questões continua podendo.
  Encaixa no mecanismo de recorte que já existe (`ranking()` renumera dentro de
  um subconjunto), então é mais UI que cálculo.

- **Versionamento visível do app.** Mostrar a versão no rodapé ou no perfil. O
  redesign marca a **2.0**; depois dele entraram o casamento de banca, a `fase`
  no simulado, os grupos e o campo de concurso por banca+fase — o que sugere
  **2.2** entregue. Regra proposta: segundo número sobe a cada lote de
  funcionalidade, terceiro a cada correção solta.

- **Import da 2ª fase (discursiva) dos simulados do colégio.** Decidido em
  12/08/2026 — desenho fechado, falta implementar:

  - **Reaproveitar a estrutura existente**, sem tabela nova. A linha do ranking
    ganha um campo de notas decimais ao lado do de acertos, e o `fase` (que já
    existe) diz qual dos dois vale.
  - **A chave única precisa passar a incluir `fase`.** Hoje é
    `(banca, rotulo, data)`, e as duas fases do mesmo simulado compartilham as
    três — colidiriam. Uma migration.
  - Reusar a validação de nota decimal que já existe em `oficiais_import.py`,
    em vez de escrever outra.
  - Ganho: import, ranking, merge de aluno e vínculo seguem funcionando sem
    alteração.
  - Falta o prompt de extração para o bloco DISCURSIVO, hoje explicitamente
    ignorado pelo `PROMPT-EXTRACAO-SIMULADO.md`.

- **Média final combinando as duas fases.** Decidido: o app calcula e mostra
  quando as duas fases do mesmo simulado estiverem importadas.

  A conta observada nos prints do S5 é `0,8 × discursivo + 0,2 × objetivo`.
  **Mas isso foi inferido de duas linhas de uma planilha, não é regra
  publicada.** Aplique aqui a mesma lição da média do IME: se a planilha trouxer
  a coluna MÉDIA FINAL, **guarde e exiba o número dela**; só calcule quando a
  coluna não existir, e deixe claro na tela quando o valor é calculado e não
  copiado. Se o colégio mudar o peso, o número copiado continua certo e o
  calculado não.

- **Ressincronização de simulados.** Hoje o "Sincronizar" só pula o que já
  existe. Falta atualizar um simulado pessoal quando o import de origem for
  corrigido — a FK `turma_linha_id` já deixa isso possível.

- **Rollback de import.** O JSON cru de cada import já é guardado em
  `historico_imports`; falta a tela para comparar e refazer.

- **Tela de listagem do histórico de import.** A tabela é só-gravação hoje.

- **Aplicar o redesign às 29 telas restantes.** Formulários, detalhes, admin,
  grupos, erros e autenticação seguem com o visual antigo sobre os tokens novos.

## 7. Decisões de produto em aberto (só se resolvem usando)

- O gráfico de **percentual por matéria** sumiu do dashboard no redesign. O dado
  continua sendo calculado no backend e vira payload morto. Volta como um quarto
  botão do seletor, ~20 linhas.

- **Concursos e Oficiais perderam aba própria** na navegação nova (viraram item
  do Perfil e segmento dentro de Simulados). Passou de um toque para dois.

- **Peso da média** — decidido: régua única, proporcional, igual à do colégio.
  Vale conferir na prática se algum número do IME ficou estranho para alguém.

## 8. Dívida estrutural

- `resultados_oficiais.concurso_nome` é **texto solto**, sem FK para a tabela
  `concursos`. É por isso que "AFA 2027" existe duas vezes no sistema em
  sentidos diferentes. Fora de escopo até hoje, de propósito — mas cada
  funcionalidade que cruzar os dois paga esse pedágio.

- **Duplicação entre os dois importadores.** `oficiais_import.py` e
  `simulado_turma_import.py` ainda repetem `_texto` e `_ALIAS_TURMA`. Parte já
  saiu para `app/validacao.py`; o resto ficou.

- **Rate limiting em memória** (`memory://`), adequado ao único worker do
  PythonAnywhere. Se um dia escalar, precisa de Redis.

## 9. Já resolvido (para não reabrir)

Turma como atributo de pessoa; Aluno como entidade com apelidos e merge; edição
manual pelo admin com aviso de sobrescrita; sincronização em lote; matérias do
perfil com filtro "mostrar apenas"; evolução ao longo do tempo; backup,
exportação e histórico de import; remoção do "Meu concurso"; média proporcional;
casamento de concurso por banca + fase; redesign das 7 telas principais; grupos
com convite e aceite; git inicializado; projeto movido para fora do OneDrive.
