# ITA-IME Analytics

Tracker de simulados para ITA/IME — uso pessoal e de um grupo pequeno de amigos.
Registre notas por simulado e por matéria, acompanhe a evolução em gráficos e
veja a contagem regressiva até a prova. **Mobile-first** (bottom nav, cards,
teclado numérico), desktop como layout secundário (tabela + top nav).

- **Stack:** Flask + SQLAlchemy (SQLite) · Flask-Login · Flask-WTF (CSRF) ·
  Flask-Limiter · Flask-Bcrypt · Flask-Migrate
- **Front:** CSS próprio com a paleta branco/vermelho/azul, Chart.js servido
  localmente (sem CDN, para uma CSP restrita a `'self'`)
- **Deploy alvo:** PythonAnywhere

---

## Estrutura de pastas

```
ITA-IME Analytics/
├── wsgi.py                 # entrypoint WSGI (carrega .env e cria o app)
├── config.py              # config central — tudo sensível vem de env var
├── requirements.txt
├── .env.example           # modelo do .env (o .env real NÃO é versionado)
├── .gitignore
├── migrations/            # Alembic (Flask-Migrate)
├── instance/              # itaime.db (SQLite) — fora do controle de versão
└── app/
    ├── __init__.py        # create_app(): registra extensões, blueprints, handlers
    ├── extensions.py      # instâncias db, login_manager, bcrypt, csrf, limiter…
    ├── models.py          # User, Concurso, Simulado, SimuladoMateria, Materia(enum)
    ├── forms.py           # WTForms (validação server-side)
    ├── security.py        # headers de segurança (CSP, X-Frame-Options…)
    ├── decorators.py      # @admin_required
    ├── cli.py             # flask create-user / reset-password
    ├── auth/routes.py     # login, logout, troca de senha
    ├── main/routes.py     # dashboard (gráficos) e perfil
    ├── simulados/routes.py# CRUD de simulados (isolamento por usuário)
    ├── concursos/routes.py# concursos (leitura p/ todos, escrita só admin)
    ├── templates/         # Jinja2 (base + telas + páginas de erro)
    └── static/
        ├── css/app.css    # mobile-first + media queries (768px, 1024px)
        └── js/
            ├── app.js         # confirmações e auto-submit (sem inline)
            ├── dashboard.js   # monta os 3 gráficos
            └── vendor/chart.umd.js  # Chart.js local (CSP)
```

Blueprints foram usados porque o app tem quatro áreas com responsabilidades
distintas (auth, dashboard, simulados, concursos); mantém cada arquivo de rotas
pequeno e o `create_app()` legível.

---

## Setup local

Pré-requisito: Python 3.11+ (desenvolvido e testado com 3.13).

```bash
# 1. Ambiente virtual + dependências
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
pip install -r requirements.txt

# 2. Arquivo .env (copie o modelo e gere o SECRET_KEY)
cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
# cole o valor no .env. Em DEV local (http), ajuste também:
#   SESSION_COOKIE_SECURE=false     (senão o cookie não é enviado sobre http)
#   BEHIND_PROXY=false

# 3. Banco de dados (migrations)
export FLASK_APP=wsgi.py            # Windows PowerShell: $env:FLASK_APP="wsgi.py"
flask db upgrade                    # cria instance/itaime.db a partir das migrations

# 4. Primeiro admin (só admin sai pela CLI; usuários comuns se cadastram na web)
flask create-user seu_usuario --admin
# imprime uma senha temporária; o app força a troca no primeiro login.

# 5. Rodar
flask run
# abra http://127.0.0.1:5000
```

> Se você mudar os modelos, gere uma nova migration com
> `flask db migrate -m "descrição"` e aplique com `flask db upgrade`.

### Contas de usuário

O cadastro é **aberto**: qualquer pessoa cria a própria conta em `/registrar`
(link na tela de login). O novo usuário entra como comum (nunca admin) e define
a própria senha. Defesas contra abuso: rate limit de 5 cadastros/hora por IP,
username validado e senha de no mínimo 10 caracteres.

Contas **admin** só saem pela CLI (não há como se promover a admin pela web):

```bash
flask create-user alice            # cria usuário comum com senha temporária
flask create-user bruno --admin    # cria/《promove》um admin
flask reset-password alice         # nova senha temporária p/ quem esqueceu
flask delete-user bruno            # exclui usuário (e simulados dele)
flask list-users                   # lista contas
```

Os comandos que geram senha temporária a imprimem **uma vez** — repasse por um
canal privado; o dono é obrigado a trocá-la no primeiro login.

---

## Deploy no PythonAnywhere

> **Atalho:** depois de extrair o zip na sua home, rode
> `bash setup_pythonanywhere.sh` (ajuste a versão de Python no topo do script se
> o seu web app não for 3.10). Ele cria o venv, instala as dependências, gera o
> `.env` com `SECRET_KEY`, e aplica as migrations. Depois é só apontar o
> Virtualenv na aba Web e ajustar o WSGI (modelo em `deploy/pythonanywhere_wsgi.py`).
> O passo a passo manual completo está abaixo.

1. **Suba o código** (git clone ou upload) para, por exemplo,
   `/home/SEU_USER/ita-ime-analytics`.

2. **Virtualenv** (console Bash do PythonAnywhere):
   ```bash
   cd ~/ita-ime-analytics
   python3.10 -m venv .venv       # use a versão de Python do seu plano
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **`.env` de produção** (na raiz do projeto):
   ```
   SECRET_KEY=<saída de: python -c "import secrets; print(secrets.token_hex(32))">
   SESSION_COOKIE_SECURE=true
   BEHIND_PROXY=true
   SESSION_HOURS=12
   ```
   `SESSION_COOKIE_SECURE=true` garante o cookie só sobre HTTPS;
   `BEHIND_PROXY=true` ativa o `ProxyFix` para o rate limiting enxergar o IP
   real do cliente (e não o do proxy do PythonAnywhere).

4. **Banco:**
   ```bash
   export FLASK_APP=wsgi.py
   flask db upgrade
   flask create-user seu_usuario --admin
   ```

5. **Aba Web → Add a new web app → Manual configuration** (mesma versão de
   Python do venv). Depois:
   - **Virtualenv:** `/home/SEU_USER/ita-ime-analytics/.venv`
   - **Source code:** `/home/SEU_USER/ita-ime-analytics`
   - **WSGI configuration file** (link na própria aba Web): substitua o conteúdo por:
     ```python
     import sys
     path = "/home/SEU_USER/ita-ime-analytics"
     if path not in sys.path:
         sys.path.insert(0, path)
     from wsgi import app as application   # wsgi.py já carrega o .env
     ```

6. **Force HTTPS** na aba Web (PythonAnywhere oferece o toggle) e clique
   **Reload**. O PythonAnywhere serve `app/static/` automaticamente; se quiser,
   mapeie `/static/` → `/home/SEU_USER/ita-ime-analytics/app/static` na seção
   *Static files* para servir os assets sem passar pelo worker.

> O rate limiting usa storage em memória (`memory://`), adequado ao modelo de
> 1 worker do PythonAnywhere. Se um dia escalar para múltiplos workers, troque
> `RATELIMIT_STORAGE_URI` por um backend Redis.

---

## Modelo de dados

- **User** — `username` único, `password_hash` (bcrypt), `is_admin`,
  `must_change_password`, `nome_oficial` (opcional — nome nos listões), `created_at`.
- **Concurso** — `nome` único, `data_prova`, `created_by`. Compartilhado: todos
  leem, só admin cria/edita.
- **Simulado** — `user_id`, `concurso_id`, `rotulo` (opcional: S1, S3…),
  `data_simulado`, `nota_geral`, `posicao_estimada` (opcional),
  `observacao` (opcional), `origem` (NULL/`manual` ou `import`).
  **Privado do dono.**
- **SimuladoMateria** — `simulado_id`, `materia` (enum), `acertos`,
  `total_questoes`. Unique `(simulado_id, materia)`.
- **PlanoEstudoDia** — `user_id`, `dia_semana` (0=seg…6=dom), `materia`. Plano
  semanal editável do usuário. Unique `(user_id, dia_semana, materia)`.
- **RegistroEstudo** — `user_id`, `data`, `materia`, `questoes`, `acertos`.
  Registro diário de estudo. **Privado do dono.** Unique `(user_id, data, materia)`.
- **SessaoTreino** — `user_id`, `data`, `materia` (opcional), `questoes`,
  `tempo_total_seg`, `observacao`. **Privado do dono.**
- **SimuladoTurma** — `banca`, `rotulo`, `data`, `turma` (novata/veterana),
  `materias_csv`, `materias_media_csv`, `questoes_json`. O ranking de um simulado
  do colégio. Compartilhado: todos leem, só admin importa. Unique
  `(banca, rotulo, turma)`.
- **SimuladoTurmaLinha** — `turma_id`, `nome`, `nome_norm`, `serie`
  (2º ANO / 3º ANO / CURSO), `status` (`presente`/`ausente`), `acertos_json`,
  `media_oficial`, `geral_oficial`, `user_id` (vínculo automático por nome).
- **ResultadoOficial** — `concurso_nome`, `turma` (novata/veterana), `fonte`,
  `data`, `escala`, `materias_csv`, `metrica`. Um listão oficial importado.
  Compartilhado: todos leem, só admin importa/exclui. Unique `(concurso_nome, turma)`.
- **ResultadoLinha** — `resultado_id`, `nome`, `nome_norm`, `status`
  (`classificado` / `sem_aproveitamento` / `nao_encontrado`), `classificacao`,
  `metrica_valor`, `notas_json`, `user_id` (vínculo automático por nome).

---

## Ranking da turma (Simulados → "Ranking da turma")

O ranking que o colégio divulga de cada simulado, com a turma inteira na mesma
prova. É o que permite responder "qual a minha posição de verdade".

**Nota e recorte.** A nota é a **média dos percentuais de acerto** das matérias
escolhidas, em escala 0–10 — peso igual entre matérias, que é a regra da 1ª fase
do IME. No ITA, como todas as matérias têm 12 questões, essa conta dá exatamente
a MÉDIA que o colégio publica (`(MAT+FÍS+QUÍM)/36×10`), então o app reproduz o
mural na vírgula.

O usuário marca as matérias que quer contar e o ranking inteiro se refaz no
navegador (a lista renderizada pelo servidor é reordenada, não recriada, então os
botões "sou eu" continuam válidos). Há atalhos para o recorte **Oficial**, para
**Tudo** e para as matérias de cada concurso cadastrado — este último depende de
o admin ter configurado as matérias do concurso; sem isso, o concurso cai no
default (todas as principais) e o atalho fica largo demais. Empates recebem a
mesma posição. A escolha fica salva no aparelho, por banca.

**Questões por matéria** vêm de `models.QUESTOES_PADRAO` (ITA 12/12/12/12,
IME 15/15/10), então o admin não digita nada. Bancas fora dessa tabela exigem o
campo `questoes` no JSON.

**Importação (só admin):** `/simulados/turma/importar`, mesmo fluxo dos Oficiais
(prompt → cola → prévia → confirma), com `docs/PROMPT-EXTRACAO-SIMULADO.md`.
O validador (`app/simulado_turma_import.py`) recusa: acerto acima do total da
prova, matéria fora do cabeçalho (o erro clássico de capturar a coluna de soma /
MÉDIA / GERAL como se fosse matéria), GERAL que não bate com a soma dos acertos,
acerto decimal, data em DD-MM-AAAA, linha "presente" zerada em tudo, matéria
faltando, nome repetido e banca desconhecida sem `questoes`.

**Trazer para os meus simulados.** Quem está vinculado pode copiar a própria
linha para o seu Simulado privado, escolhendo o concurso — a nota e a posição
saem sob as matérias desse concurso. É **opt-in do usuário**, nunca do admin.
Um registro digitado à mão **nunca** é sobrescrito (bloqueado na tela e no
servidor), e a `observacao` não é tocada em nenhum caso.

---

## Resultados oficiais (aba "Oficiais")

Guarda o listão real divulgado pela banca (dado já público), separado por turma.
Diferente de Simulado, aqui a posição é a **oficial**, não uma estimativa.

**Importação (só admin):** `/oficiais/importar`. O admin gera o JSON a partir do
PDF/print do listão usando o prompt de `docs/PROMPT-EXTRACAO.md` (a própria página
mostra o prompt com botão de copiar), cola, vê uma **prévia** com todas as linhas e
só então confirma. Nada é gravado antes da confirmação. Reimportar o mesmo
`(concurso, turma)` **substitui** o anterior — e os vínculos com perfis são
refeitos automaticamente depois.

O validador (`app/oficiais_import.py`) recusa, com mensagem apontando a linha:
nota fora da escala declarada, matéria que não está no cabeçalho, `classificado`
sem posição, status inválido, turma ausente, posição ou nome duplicados, e
`tipo` diferente de `oficial`. O objetivo é pegar erro de extração antes de gravar.

**Vínculo com o perfil:** cada pessoa informa em `/perfil` o nome como ele aparece
nos listões (ou clica em "sou eu" numa linha). O casamento é por nome normalizado
(maiúsculas, sem acento, espaços colapsados), e um mesmo nome não pode ser
reivindicado por duas contas.

---

## Auditoria de Segurança

Cada item do checklist, como foi implementado e onde (`arquivo:linha`).
Todos os itens foram exercitados por testes automatizados contra o servidor
rodando (ver "Como foi testado" no fim).

| # | Item | Status | Onde |
|---|------|--------|------|
| 1 | **Hash bcrypt, cost ≥ 12** | ✅ cost **13** | Config em [config.py:28](config.py); hashing em [app/models.py:34-38](app/models.py) (`generate_password_hash`/`check_password_hash`) |
| 2 | **CSRF em todo form** | ✅ | `CSRFProtect` global em [app/extensions.py](app/extensions.py) + init em [app/__init__.py](app/__init__.py). Forms WTForms herdam `FlaskForm` ([app/forms.py](app/forms.py)); forms "crus" (logout/excluir) incluem `csrf_token()` manualmente nos templates. Testado: POST sem token e com token forjado → **400** |
| 3 | **Queries só via ORM** | ✅ | Todas as rotas usam `db.select(...)` / `db.session.get(...)`. Zero SQL raw, zero string-format em query, nenhum `text()`. O único `db.session.execute(...)` ([app/concursos/routes.py:22](app/concursos/routes.py)) recebe um `db.select()` do ORM |
| 4 | **Autorização em cada rota de Simulado** | ✅ | `_get_simulado_do_usuario()` valida `simulado.user_id == current_user.id OU is_admin` e chama `abort(404)` caso contrário — [app/simulados/routes.py:15-22](app/simulados/routes.py). Usado em detalhe/editar/deletar. Listagem e dashboard filtram por `user_id=current_user.id` ([app/simulados/routes.py:55](app/simulados/routes.py), [app/main/routes.py:38](app/main/routes.py)). Admin de concursos via `@admin_required` ([app/decorators.py:14](app/decorators.py)). Testado: IDOR por URL direta (GET/POST editar/deletar de outro usuário) → **404** |
| 5 | **Rate limit no login** | ✅ **5 / 15 min por IP** | [app/auth/routes.py:55-59](app/auth/routes.py) (`@limiter.limit("5 per 15 minutes", methods=["POST"])`). Troca de senha limitada a 10/h. Testado: 6ª tentativa → **429**; GET /login não é bloqueado |
| 6 | **Cookie Secure + HttpOnly + SameSite; timeout** | ✅ | [config.py:22-25](config.py): `HTTPONLY=True`, `SAMESITE="Lax"`, `SECURE` (env, default True), `PERMANENT_SESSION_LIFETIME=12h`. `session.permanent=True` no login. Testado via socket cru: cookie de sessão sai com `HttpOnly; SameSite=Lax` |
| 7 | **Headers de segurança (CSP, X-Frame-Options, X-Content-Type-Options)** | ✅ | [app/security.py](app/security.py) via `after_request`. CSP restrita a `'self'` (sem `unsafe-inline`; por isso Chart.js é local e não há script inline). Também `Referrer-Policy` e `Permissions-Policy`. Testado: headers presentes, CSP sem `unsafe-inline` |
| 8 | **Validação server-side em todos os forms** | ✅ | WTForms validators em [app/forms.py](app/forms.py): `DataRequired`, `NumberRange`, `Length`, `EqualTo`; validações custom (data não-futura, acertos ≤ total, acertos+total juntos, nova senha ≠ atual). Nenhuma rota confia em validação client-side |
| 9 | **Autoescape / sem `\|safe` indevido** | ✅ | Autoescape do Jinja2 ativo (templates `.html`); **nenhum** `\|safe` no projeto. Dados do gráfico vão num `<script type="application/json">` via `\|tojson` (escape seguro) e são lidos com `JSON.parse`. Testado: `<script>` em observação é renderizado escapado (`&lt;script&gt;`) |
| 10 | **Sem segredo hardcoded** | ✅ | `SECRET_KEY` e flags vêm de env ([config.py:15](config.py)); `.env` no [.gitignore](.gitignore); modelo em [.env.example](.env.example). Nenhuma senha/credencial no código |
| 11 | **SECRET_KEY via `secrets.token_hex(32)`** | ✅ | Gerado fora do código e lido do `.env`; instrução no [.env.example](.env.example) e no README. `create_app()` **aborta** se `SECRET_KEY` não estiver definido ([app/__init__.py](app/__init__.py)) |
| 12 | **Log de login falho (sem senha)** | ✅ | [app/auth/routes.py:82-84](app/auth/routes.py): `logger.warning("Login FALHOU: usuario=%r ip=%s", ...)` — registra usuário e IP, **nunca** a senha. Sucesso e troca de senha também logados |
| 13 | **Anti-enumeração de usuário** | ✅ | Mensagem única "Usuário ou senha inválidos" para usuário inexistente **e** senha errada ([app/auth/routes.py:85](app/auth/routes.py)). Contra timing: quando o usuário não existe, roda um bcrypt "queimando" tempo equivalente ([app/auth/routes.py:27-33,80](app/auth/routes.py)). Testado: as duas respostas são idênticas |

### Defesas extras (além do checklist)

- **Anti session fixation:** `session.clear()` antes do `login_user()` e no logout
  ([app/auth/routes.py:69](app/auth/routes.py)); `login_manager.session_protection = "strong"`.
- **Anti open-redirect:** `?next=` só aceita caminho relativo interno
  ([app/auth/routes.py:36-44](app/auth/routes.py)). Testado com `next=https://evil.com`.
- **Troca de senha forçada:** usuário com senha temporária fica preso na tela de
  troca até definir uma nova ([app/auth/routes.py:47-52](app/auth/routes.py)).
- **404 em vez de 403 no IDOR de simulado:** não confirma a existência do recurso
  de outro usuário, reduzindo sinal para varredura de IDs.
- **Integridade referencial:** concurso com simulados não pode ser excluído
  ([app/concursos/routes.py](app/concursos/routes.py)).

### Como foi testado

Suíte adversarial executada contra o servidor rodando (cliente HTTP com cookies,
simulando os "amigos potencialmente adversariais"):

- **Autorização/IDOR:** bruno tentando GET/POST em simulado da alice por URL
  direta → 404; não-admin em rotas de admin → 403; admin conseguindo ver
  simulado alheio (bypass `is_admin`) → 200.
- **CSRF:** POST sem token e com token forjado → 400.
- **Rate limit:** 6ª tentativa de login no mesmo IP → 429.
- **Enumeração:** respostas idênticas p/ usuário inexistente e senha errada.
- **Headers/cookie:** CSP sem `unsafe-inline`, X-Frame-Options DENY, nosniff;
  cookie de sessão HttpOnly + SameSite=Lax.
- **XSS:** payload `<script>` em observação renderizado escapado.
- **Senha temporária:** login → preso em /trocar-senha → liberado após trocar.

---

## Nota sobre responsividade (mobile 375px / desktop 1280px)

Testado nos três breakpoints (375px, 768px, 1280px) com o app rodando. O que
muda entre mobile e desktop:

- **Navegação:** em ≤767px, **bottom nav fixa** (Dashboard/Simulados/Concursos/
  Perfil) + **FAB** vermelho para "novo simulado"; em ≥768px a bottom nav e o FAB
  somem e aparece a **top nav** no header azul, com um botão "+ Novo simulado" no
  cabeçalho da página.
- **Listagem de simulados:** em mobile são **cards** (data, concurso, nota grande,
  chips por matéria); em ≥768px vira **tabela** densa com coluna de ações. A troca
  é via media query (`.hide-desktop` / `.show-desktop`), confirmada por
  `getComputedStyle` (cards `display:none` no desktop, tabela `display:block`).
- **Grid de stats:** 2 colunas no celular, 4 colunas no tablet/desktop.
- **Gráficos:** 1 coluna empilhada no mobile, 2 colunas a partir de 1024px.
  No mobile os eixos usam menos ticks (`maxTicksLimit` menor) e tooltip
  touch-friendly (`interaction.mode = "nearest"`, sem exigir toque exato no ponto).
- **Toque:** todos os inputs e botões têm altura mínima de **44px**; inputs
  numéricos usam `inputmode="numeric"`/`"decimal"` para abrir o teclado numérico;
  inputs a 16px de fonte para o iOS não dar zoom ao focar.
- **Acessibilidade:** foco de teclado visível (`:focus-visible` com contorno
  azul), `aria-current` na navegação, contraste AA do vermelho `#B91C30` e do
  azul `#1D3557` sobre branco. Vermelho e azul nunca competem no mesmo elemento
  — vermelho é ação (salvar/CTA/FAB), azul é identidade/navegação/dados.
```
