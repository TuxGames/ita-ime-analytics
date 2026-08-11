# Padrão visual — modelo "Placar"

O redesign de agosto (commit `cb6447b`) cobriu 7 telas e trouxe o
`app/static/css/placar.css`, carregado **depois** do `app.css`. Este documento
descreve o vocabulário que saiu dele, para as demais telas seguirem o mesmo
padrão em vez de cada uma inventar o seu.

Regra geral: **reaproveite classe existente**. Só crie classe nova quando não
houver equivalente — e nesse caso ela vai para o `placar.css`, nunca para o
`app.css`.

---

## Tokens

O `placar.css` redefine tokens globais no `:root`. Não use cor literal em
template; use o token.

| Token | Uso |
|---|---|
| `--board` `#0C1B2E` | superfície escura do cabeçalho |
| `--board-2` | célula dentro da superfície escura |
| `--board-muted` / `--board-dim` | texto secundário/terciário sobre escuro |
| `--live` `#F04155` | vermelho legível sobre escuro |
| `--up` `#4FC98A` | variação positiva sobre escuro |
| `--bg` `#F2F3F5` | fundo da página |
| `--border` `#E3E5E9` | traço de separação |
| `--text` `#12171E` / `--muted` / `--faint` | texto sobre claro |
| `--radius` `18px` | raio do card |
| `--red` / `--blue` / `--green` | herdados do `app.css` |

---

## Dois níveis de tela

**Nível 1 — destino de navegação** (Início, Simulados, Estudos, Perfil, e as
sub-abas Turma/Oficiais). Abre com a superfície escura `.board`, que sangra até
a borda:

```html
<section class="board" aria-label="Simulados">
  <div class="board-top">
    <div>
      <h1 class="board-title">Simulados</h1>
      <p class="board-sub">Uma linha explicando o recorte.</p>
    </div>
    {{ monograma(current_user.nome_oficial or current_user.username, "md") }}
  </div>
</section>
```

**Nível 2 — formulário, detalhe, confirmação, erro.** Não usa `.board`: abre com
`.page-head`, mais leve, e o conteúdo vive em cards.

```html
<div class="page-head">
  <h1>Novo simulado</h1>
  <a class="btn btn-ghost btn-sm" href="...">Voltar</a>
</div>
```

Misturar os dois na mesma tela é o erro mais fácil de cometer. Se a tela é um
passo dentro de um fluxo, ela é nível 2.

---

## Peças do `.board`

- `.board-top` — linha do título com o avatar/monograma à direita.
- `.board-title` (27px, 800) e `.board-sub` (13px, `--board-muted`).
- `.board-cells` — grade de até **3** `.board-cell`, cada uma com
  `.board-value` (número grande) e `.board-label` (rótulo em caixa alta), com
  `.board-scope` para a qualificação em letra menor.
- `.board-delta-up` / `-down` / `-flat` — variação.
- `.seg` — navegação entre irmãs (Meus · Turma · Oficiais), com
  `aria-current="page"` na ativa, e `.seg-explica` para a linha de explicação.
- `select.input-board` — seletor dentro da superfície escura.

Números grandes usam `font-variant-numeric: tabular-nums` para não dançarem ao
atualizar. Já está nas classes; não repita.

---

## Card

Unidade básica de conteúdo sobre fundo claro.

```html
<section class="card">
  <h2 class="card-title">Título do card</h2>
  <p class="card-sub">Uma linha de contexto, opcional.</p>
  ...
</section>
```

- `.card-title` — 15px, `--blue`. É o `<h2>` da tela.
- `.card-sub` — 13px, `--muted`. Explica; não repete o título.
- `.card-head-row` — título à esquerda e ação à direita na mesma linha
  (com `.card-sub-inline` ou um `.btn.btn-sm`).
- `.card-flush` — card sem padding, para lista que encosta na borda
  (ver `.link-list`).
- Cards empilhados já recebem espaçamento por `.card + .card`; **não**
  acrescente margem à mão.

---

## Listas

| Classe | Quando |
|---|---|
| `.cards-list` | lista de cards clicáveis (um `<li>` por card) |
| `.link-list` dentro de `.card.card-flush` | lista de links de navegação, com `<span class="chev">›</span>` |
| `.of-linhas` / `.of-linha` | linha de pessoa com posição, nome e número |
| `.of-simples` | lista simples nome + ação (é `space-between`) |
| `.chips` / `.chip` | conjunto de rótulos curtos |

Em lista `space-between` (`.of-simples`, `.aluno-link`), monograma e nome
precisam ficar juntos dentro de um `<span class="pessoa">`, senão o nome é
jogado para a outra ponta da linha.

---

## Pessoa

Sempre que aparecer nome de gente, vem o monograma junto
(`app/monograma.py`, macro em `_macros.html`):

```html
{% from "_macros.html" import monograma %}
{{ monograma(ln.nome, "sm") }}
```

Tamanhos: `sm` (28px, linha de lista), `md` (36px, padrão), `lg` (64px, perfil).
A cor sai do nome e é sempre a mesma para a mesma pessoa — é isso que faz
reconhecer alguém de uma tela para outra.

---

## Botões

Um botão primário por tela. Se houver dois, um deles não é primário.

| Classe | Papel |
|---|---|
| `.btn.btn-primary` | ação principal (vermelho) |
| `.btn.btn-outline` | ação secundária (contorno azul) |
| `.btn.btn-ghost` | ação terciária, dentro de card ou linha |
| `.btn.btn-danger` | destrutiva (contorno vermelho, fundo branco) |
| `.btn.btn-ghost.btn-ghost-danger` | destrutiva discreta, dentro de lista |
| `.btn-live` | ação sobre superfície escura |

Modificadores: `.btn-block` (largura total), `.btn-sm` (dentro de card ou
cabeçalho).

Ações no rodapé da tela vão dentro de `.form-actions`, que já é uma grade com
espaçamento — não empilhe botões soltos.

---

## Formulário

```html
<form method="post" novalidate>
  {{ form.hidden_tag() }}
  <div class="form-group">
    {{ form.campo.label(class="form-label") }}
    {{ form.campo(class="input" + (" input-error" if form.campo.errors else "")) }}
    {% for e in form.campo.errors %}<p class="field-error">{{ e }}</p>{% endfor %}
  </div>
  <button type="submit" class="btn btn-primary btn-block">Salvar</button>
</form>
```

- `.form-group` por campo; `.form-label`; `.input`.
- Erro: `.input-error` no campo **e** `.field-error` abaixo.
- Checkbox solto: `.check-linha`. Vários: `.check-group` + `.check-list`.
- `novalidate` é proposital — a validação que vale é a do servidor.
- `{{ form.hidden_tag() }}` (ou o `csrf_token()` à mão em form sem WTForms)
  **nunca** sai.

---

## Estado vazio

```html
<section class="card empty-state">
  <svg ...>...</svg>
  <h2>Nada aqui ainda</h2>
  <p>Uma frase dizendo o que aparece aqui e como fazer aparecer.</p>
  <a class="btn btn-primary" href="...">Ação que resolve</a>
</section>
```

O texto diz o que a tela mostra quando tiver conteúdo — não só "vazio".

---

## Mobile e desktop

Mobile-first. O mesmo dado em duas formas quando faz sentido:

```html
<ul class="cards-list hide-desktop">...</ul>
<div class="card table-wrap show-desktop"><table class="table">...</table></div>
```

Breakpoints: 768px (tablet, some a bottom nav) e 1024px (desktop).
Conteúdo largo (tabela, gráfico) rola dentro do próprio container
(`.table-wrap` já faz isso); a página nunca rola na horizontal.

---

## Restrições que não podem quebrar

A CSP é `'self'`, sem `unsafe-inline`:

- **zero** `style="..."` em template — cor ou medida variável vira classe
  pronta, no padrão das `.bar-0`…`.bar-100` e `.mono-c0`…`.mono-c11`;
- **zero** `<script>` executável inline — só `<script src=...>` e
  `<script type="application/json">` para passar dado ao JS;
- nada de CDN: fonte, CSS e JS são servidos localmente.

Alvo de toque: 44px de altura mínima em qualquer elemento clicável.
