Você vai ler o ranking de um SIMULADO aplicado pelo colégio (print de planilha,
PDF ou foto) e convertê-lo em JSON para importar no ITA-IME Analytics.

Atenção: este prompt é para RANKING DE SIMULADO DO COLÉGIO e extrai APENAS a
1ª FASE (prova objetiva), onde os números são QUANTIDADES DE QUESTÕES CERTAS
(inteiros). Não confunda com o listão oficial de concurso (notas decimais 0–10),
que usa o outro prompt.

REGRAS

1. Responda APENAS com o JSON. Sem texto antes, sem texto depois, sem ```.
2. UM JSON por lista. Se houver turma novata e veterana (ou dois arquivos), gere
   dois JSONs separados, um de cada vez.
3. Não invente, não arredonde e não complete dados. Copie os números exatamente
   como aparecem. Se um valor estiver ilegível, pare e me diga qual é, em vez de
   chutar.
4. Não calcule nada. Só copie o que está escrito.

=============================================================================
LEIA SÓ O BLOCO DA OBJETIVA
=============================================================================

Muitas planilhas do colégio ("Simulado S5 ITA - 1ª e 2ª fase") trazem DOIS
blocos de colunas lado a lado, sob dois títulos que se estendem por várias
colunas:

- **DISCURSIVO** (2ª fase) — notas decimais 0–10, com vírgula: 8,40 · 6,35 · 7,33.
  Costuma incluir POR e RED. **IGNORE ESSE BLOCO INTEIRO.**
- **OBJETIVA** (1ª fase) — acertos inteiros: 8 · 5 · 7 · 11. Inclui ING.
  **É SÓ DAQUI QUE VOCÊ EXTRAI.**

Como distinguir na hora, se o cabeçalho estiver cortado ou ilegível: o bloco
discursivo tem números com vírgula e casas decimais; o objetivo tem inteiros
puros. Se você extraiu algo como 8,40 para dentro de "acertos", pegou o bloco
errado — recomece.

A mesma matéria aparece nos dois blocos com valores diferentes (MAT 8,40 no
discursivo e MAT 8 no objetivo). Sempre o do bloco OBJETIVA.

Ignore também a coluna **MÉDIA FINAL** (a última, azul). Ela mistura as duas
fases e não entra neste JSON.

=============================================================================
A ORDEM DAS COLUNAS MUDA DE UMA PLANILHA PARA OUTRA — NÃO ASSUMA NADA
=============================================================================

**COPIE A ORDEM DAS MATÉRIAS EXATAMENTE COMO ELA APARECE NO CABEÇALHO DA
PLANILHA QUE VOCÊ ESTÁ LENDO, COLUNA POR COLUNA, DA ESQUERDA PARA A DIREITA.**

A ordem NÃO é padronizada. Já apareceram planilhas do mesmo simulado com
`MAT · FÍS · QUÍ · ING` numa turma e `MAT · QUÍ · FÍS · ING` na outra. Física e
Química trocam de lugar.

Por que isso é grave: os dois valores são baixos e válidos (≤ 12), então nenhuma
trava de limite pega o erro, e a conferência da MÉDIA (que é uma soma) também
não pega, porque somar na ordem trocada dá o mesmo resultado. Um QUÍ lido como
FÍS passa por todas as verificações e só aparece meses depois, no gráfico de
evolução da pessoa errada.

Antes de escrever o JSON: releia o cabeçalho do bloco OBJETIVA e confirme a
ordem. Se o cabeçalho estiver ilegível, PARE e me pergunte — não deduza pela
ordem de outra planilha.

=============================================================================
FORMATO
=============================================================================

{
  "tipo": "simulado",
  "fase": "objetiva",
  "banca": "ITA",
  "rotulo": "S5",
  "data": "2026-04-11",
  "turma": "novata",
  "fonte": "GGE",
  "materias": ["MAT", "QUIM", "FIS", "ING"],
  "materias_media": ["MAT", "QUIM", "FIS"],
  "questoes": null,
  "resultados": [
    {
      "nome": "PEDRO ARTHUR CAMPOS SOBRAL",
      "serie": "CURSO",
      "status": "presente",
      "acertos": { "MAT": 8, "QUIM": 5, "FIS": 7, "ING": 11 },
      "media_oficial": 5.56,
      "geral_oficial": null
    },
    {
      "nome": "VITOR RAFAEL ALVES DE FREITAS",
      "serie": "3º ANO",
      "status": "presente",
      "acertos": { "MAT": 6, "QUIM": 4, "FIS": 5, "ING": 10 },
      "media_oficial": 4.17,
      "geral_oficial": null
    },
    {
      "nome": "JOAO PEDRO FONSECA DAS NEVES BRAGA",
      "serie": "3º ANO",
      "status": "ausente"
    }
  ]
}

CAMPOS DO CABEÇALHO

- tipo            — sempre "simulado".
- fase            — sempre "objetiva" (este prompt só extrai a 1ª fase).
- banca           — a prova que o simulado imita, do título (ITA, IME, AFA...).
- rotulo          — o código do simulado, do título (S0, S1, S3, S5, S7...).
- data            — "AAAA-MM-DD". **MUITOS TÍTULOS NÃO TÊM DATA** (ex.:
                    "Simulado S5 ITA - 1ª e 2ª fase"). Se não houver data no
                    título nem na planilha, use null — ela será informada na
                    hora do import. NÃO invente e NÃO use a data de hoje.
                    Se houver, cuidado: costuma vir em DD-MM-AAAA
                    ("Simulado ITA S3 - 11-04-2026" vira "2026-04-11").
- turma           — "novata" ou "veterana". Vale para TODAS as pessoas desta
                    lista; o importador carimba essa turma em cada pessoa.
                    Atenção: "CURSO" NÃO é veterano — é uma SÉRIE dentro da
                    turma novata (quem já saiu do ensino médio). As duas listas
                    misturam séries, então a coluna SÉRIE NÃO diz a turma. Só o
                    fato de ser a lista da novata ou da veterana diz. Se o
                    arquivo não deixar claro qual é, PARE e pergunte — não
                    chute pelo tamanho da lista nem pelas notas.
- fonte           — cursinho/colégio que publicou (opcional, null se não houver).
- materias        — códigos das colunas de ACERTOS do bloco OBJETIVA, NA ORDEM
                    EM QUE APARECEM. Use apenas: MAT, FIS, QUIM, PORT, ING,
                    RED, GEO, HIST.
- materias_media  — as matérias que a coluna MÉDIA do bloco objetiva combina.
                    No ITA são as três primeiras, SEM Inglês: MAT, FIS, QUIM
                    (ver a conferência abaixo). Se não der para saber, use null.
- questoes        — SEMPRE null. O total de questões por matéria não aparece no
                    ranking; o app já sabe o padrão de cada banca.

CAMPOS DE CADA PESSOA

- nome           — nome completo, exatamente como na lista (máx. 120). Ver
                   "nomes cortados" abaixo.
- serie          — o conteúdo da coluna SÉRIE, copiado como está ("2º ANO",
                   "3º ANO", "CURSO"). null se a lista não tiver essa coluna.
- status         — "presente" ou "ausente". Use "ausente" SOMENTE quando a
                   pessoa estiver com ZERO em TODAS as matérias do bloco
                   OBJETIVA — nesse caso ela não fez a 1ª fase. Em "ausente",
                   omita "acertos", "media_oficial" e "geral_oficial".
                   IMPORTANTE: é comum alguém estar zerado na objetiva mas com
                   notas no discursivo (fez só a 2ª fase). Para este import ela
                   é "ausente" mesmo assim — mas MANTENHA a pessoa na lista, não
                   a remova.
- acertos        — objeto código→inteiro, só com as matérias listadas em
                   "materias". São QUANTIDADES DE QUESTÕES CERTAS, sempre
                   números inteiros (9, 5, 0), nunca decimais.
- media_oficial  — o valor da coluna MÉDIA **do bloco OBJETIVA**, como está.
                   NÃO é a MÉDIA do discursivo nem a MÉDIA FINAL.
- geral_oficial  — o valor da coluna de TOTAL DE ACERTOS da pessoa, se existir.
                   **Essa coluna nem sempre se chama "GERAL".** Já apareceu como
                   "ACERTOS" e como "TOTAL" — é a coluna, geralmente logo antes
                   da MÉDIA, cujo valor é a soma dos acertos daquela linha (26,
                   quando a pessoa fez 11+11+4). Qualquer que seja o título,
                   copie o valor para cá.
                   Só use null quando a planilha realmente não tiver essa coluna
                   — é o caso das planilhas de "1ª e 2ª fase", que têm só MÉDIA
                   por bloco e MÉDIA FINAL. Não substitua pela MÉDIA e não
                   calcule a soma você mesmo: o valor tem que ser copiado, senão
                   ele deixa de servir como conferência independente.

=============================================================================
LINHAS QUE NÃO SÃO PESSOAS
=============================================================================

Algumas planilhas trazem uma linha **GABARITO** logo abaixo do cabeçalho, com o
número de questões de cada matéria (15 · 15 · 10), o total (40) e a média máxima
(10,00). Ela é a referência da prova, não um aluno. **NÃO a inclua em
"resultados".**

Reconheça pelo padrão: é a linha em que os "acertos" são exatamente o total de
questões de cada matéria e a média é o valor máximo. O nome costuma ser
GABARITO, mas pode aparecer como TOTAL, MÁXIMO ou REFERÊNCIA.

De quebra, essa linha é útil: ela te diz quantas questões cada matéria tem
nessa prova. Use isso para conferir os limites e o cálculo da média — mas não a
transforme em pessoa.

Ignore igualmente qualquer linha de rodapé com média da turma, contagem de
alunos ou observações.

=============================================================================
CONFIRA SE A LISTA NÃO ESTÁ CORTADA
=============================================================================

Print de planilha frequentemente corta o fim da lista. Antes de fechar o JSON,
olhe a última linha: se ela estiver colada na borda inferior da imagem, sem
margem branca depois, provavelmente há mais gente abaixo que você não está
vendo.

Isso é o erro mais difícil de detectar depois, porque tudo que sobrou está
correto — não existe conferência que acuse alunos ausentes. Se desconfiar,
PARE e me avise, dizendo qual foi a última linha que você conseguiu ler, em vez
de entregar uma lista incompleta como se fosse completa.

=============================================================================
CÉLULA VAZIA NÃO É ZERO
=============================================================================

Célula em branco e célula com 0 são coisas diferentes. Em branco significa dado
ausente; 0 significa que a pessoa fez e errou tudo naquela matéria.

Se uma célula de acerto estiver visivelmente vazia (sem nenhum caractere), PARE
e me diga de quem é e qual matéria, em vez de escrever 0. Nunca preencha um
branco com zero por conta própria.

=============================================================================
NOMES CORTADOS
=============================================================================

A coluna NOME às vezes corta o nome na largura da célula — aparece algo como
"MARCUS VINICIUS BERNARDINO DE OLIVEIRA M", terminando no meio de uma palavra.

Isso é grave porque a mesma pessoa em outro simulado vira duas pessoas
diferentes no app, e o gráfico de evolução dela quebra.

Se um nome parecer truncado (termina numa letra solta, numa preposição, ou sem
sobrenome final), copie o que dá para ler E me avise no final, fora do JSON,
listando quais nomes você suspeita estarem cortados. Essa é a ÚNICA exceção à
regra de responder apenas com o JSON.

=============================================================================
O ERRO MAIS FÁCIL DE COMETER
=============================================================================

A tabela tem colunas CALCULADAS que NÃO são matérias e não podem entrar em
"acertos" nem em "materias":

- a coluna de soma (título tipo "MAT, FÍS, QUÍM", que vale 19 quando a pessoa
  fez 9+5+5) — ignore, é só um subtotal;
- a coluna MÉDIA do bloco objetiva — vai em "media_oficial";
- a coluna MÉDIA do bloco discursivo — ignore;
- a coluna MÉDIA FINAL — ignore;
- a coluna de total de acertos, seja qual for o título (GERAL, ACERTOS, TOTAL)
  — vai em "geral_oficial".

Se o seu JSON tiver 5 ou 6 matérias numa prova de 4, foi isso que aconteceu.

=============================================================================
CONFERÊNCIA DOS NÚMEROS (use para pegar erro de leitura)
=============================================================================

**Limite por matéria.** Os simulados do colégio têm quantidade fixa de questões:

- ITA — MAT 12, FÍS 12, QUÍM 12, ING 12  (48 no total)
- IME — MAT 15, FÍS 15, QUÍM 10          (40 no total, sem Inglês)

Nenhum acerto pode passar desses limites. Se você leu 13 em Física num simulado
do ITA, ou qualquer Inglês num simulado do IME, é erro de leitura: releia a
célula. Se mesmo relendo o número passar do limite, PARE e me avise em vez de
gerar o JSON.

**Conferência da MÉDIA.** A fórmula depende da banca, porque no ITA o Inglês
fica de fora da média e no IME não existe Inglês.

ITA — média sobre as três matérias, SEM Inglês:

    MEDIA = (MAT + FIS + QUIM) / 36 * 10

    Exemplos reais: 7 + 9 + 11 = 27 → 27/36*10 = 7,50 ✓
                    8 + 5 + 7  = 20 → 20/36*10 = 5,56 ✓
                    7 + 1 + 2  = 10 → 10/36*10 = 2,78 ✓

IME — média sobre o total de acertos das três matérias:

    MEDIA = (MAT + FIS + QUIM) / 40 * 10

    Exemplos reais: 11 + 11 + 4 = 26 → 26/40*10 = 6,50 ✓
                    6  + 8  + 5 = 19 → 19/40*10 = 4,75 ✓
                    5  + 2  + 2 = 9  →  9/40*10 = 2,25 ✓

Se a planilha tiver a coluna de total de acertos (GERAL / ACERTOS / TOTAL),
confira também que ela bate com a soma da linha.

Confira por amostragem (umas 5 linhas espalhadas, incluindo a primeira e a
última). Se não bater, você leu alguma célula errado — releia a linha inteira.

Se der uma diferença sistemática em todas as linhas num simulado do ITA, você
provavelmente incluiu o Inglês na conta: ele NÃO entra na MÉDIA.

Se a banca não for ITA nem IME, ou se o divisor não fechar, deduza o total de
questões pela linha GABARITO em vez de assumir 36 ou 40.

**O que essa conferência NÃO pega.** Ela é uma soma, então não detecta duas
matérias trocadas entre si. A única proteção contra isso é ter lido a ordem do
cabeçalho corretamente — releia a seção sobre ordem das colunas.

=============================================================================
OUTROS CUIDADOS
=============================================================================

- Cor de fundo da linha não significa nada. Quem diz a série é a coluna SÉRIE.
- Zero em algumas matérias (mas não em todas) é resultado real: status
  "presente", com os zeros copiados.
- Nome que quebra em duas linhas na tabela deve virar um nome só.
- Não pode haver nomes repetidos na mesma lista.
- Não reordene as pessoas: mantenha a ordem em que aparecem.
