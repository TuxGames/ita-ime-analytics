Você vai ler o resultado da **2ª FASE (DISCURSIVA)** de um simulado do colégio
(print de planilha, PDF ou foto) e convertê-lo em JSON para importar no
ITA-IME Analytics.

Atenção: este prompt é para a **2ª fase**, onde os valores são **NOTAS DECIMAIS
de 0 a 10** com vírgula (5,70 · 0,00 · 8,50). A 1ª fase (objetiva), onde os
valores são quantidades inteiras de questões certas, usa o outro prompt
(`PROMPT-EXTRACAO-SIMULADO.md`). O listão oficial de concurso usa um terceiro.

REGRAS

1. Responda APENAS com o JSON. Sem texto antes, sem texto depois, sem ```.
2. UM JSON por lista. Se houver turma novata e veterana (ou dois arquivos), gere
   dois JSONs separados, um de cada vez.
3. Não invente, não arredonde e não complete dados. Copie os números exatamente
   como aparecem. Se um valor estiver ilegível, PARE e me diga qual é.
4. **Não calcule nada.** Só copie o que está escrito. Isto vale principalmente
   para a coluna de média — ver a seção própria abaixo.

=============================================================================
COMO SABER QUE VOCÊ ESTÁ NO BLOCO CERTO
=============================================================================

A planilha pode vir de dois jeitos:

- **Só a discursiva**, como uma tabela única (NOME · SÉRIE · matérias · Média).
- **Dois blocos lado a lado** ("Simulado S5 ITA - 1ª e 2ª fase"), sob os títulos
  DISCURSIVO e OBJETIVA. Neste caso, **extraia SÓ o bloco DISCURSIVO.**

**O único discriminador confiável é o formato do número:**

- decimal com vírgula (5,70 · 0,00 · 8,40) → **DISCURSIVO**, é daqui que você extrai
- inteiro puro (8 · 5 · 11) → objetiva, ignore

**NÃO use a presença de Inglês para decidir.** Existe uma crença, registrada no
prompt da 1ª fase, de que ING só aparece na objetiva. **É falso.** A planilha do
IME S6 traz ING no bloco discursivo, com nota decimal. Se você decidir pelo nome
da coluna em vez do formato do número, vai pegar o bloco errado.

A mesma matéria aparece nos dois blocos com valores diferentes (MAT 8,40 no
discursivo e MAT 8 no objetivo). Sempre o do bloco DISCURSIVO.

=============================================================================
A ORDEM DAS COLUNAS MUDA DE UMA PLANILHA PARA OUTRA — NÃO ASSUMA NADA
=============================================================================

**COPIE A ORDEM DAS MATÉRIAS EXATAMENTE COMO ELA APARECE NO CABEÇALHO DA
PLANILHA QUE VOCÊ ESTÁ LENDO, COLUNA POR COLUNA, DA ESQUERDA PARA A DIREITA.**

Já apareceram planilhas do mesmo simulado com `MAT · FÍS · QUÍ` numa turma e
`MAT · QUÍ · FÍS` na outra. Física e Química trocam de lugar.

Por que isso é grave: as duas notas são baixas e válidas (≤ 10), então nenhuma
trava de limite pega o erro, e conferir a média também não pega, porque a soma
na ordem trocada dá o mesmo resultado. Um QUÍ lido como FÍS passa por todas as
verificações e só aparece meses depois, no gráfico de evolução da pessoa errada.

Se o cabeçalho estiver ilegível, PARE e pergunte — não deduza pela ordem de
outra planilha.

=============================================================================
A COLUNA DE MÉDIA: COPIE, NUNCA CALCULE
=============================================================================

Esta é a regra mais importante deste prompt.

A fórmula da média da 2ª fase **não é conhecida** e **não é publicada pelo
colégio**. Ela foi testada contra as linhas reais do IME S6 com várias hipóteses
(média simples, média sem Inglês, média ponderada com pesos plausíveis,
combinação com a 1ª fase) e **nenhuma reproduz os valores da planilha**.

Portanto: **copie o número da coluna de média como ele está escrito.** Não tente
deduzir a fórmula, não recalcule para "conferir", não corrija um valor que
pareça estranho. O número da planilha é a verdade; qualquer conta sua é palpite.

Se a planilha **não tiver** coluna de média, use `null`. Não preencha.

=============================================================================
FORMATO
=============================================================================

{
  "tipo": "simulado",
  "fase": "discursiva",
  "banca": "IME",
  "rotulo": "S6",
  "data": "2026-07-11",
  "data_secundaria": "2026-04-14",
  "turma": "veterana",
  "fonte": null,
  "materias": ["MAT", "FIS", "QUIM", "PORT", "ING", "RED"],
  "materias_media": null,
  "resultados": [
    {
      "nome": "PEDRO GABRIEL VERAS DE OLIVEIRA",
      "serie": "3º ANO",
      "status": "presente",
      "notas": { "MAT": 5.70, "FIS": 3.50, "QUIM": 5.70,
                 "PORT": 7.00, "ING": 8.50, "RED": 6.10 },
      "media_oficial": 5.56,
      "media_final_oficial": null
    },
    {
      "nome": "EDUARDO HENRIQUE SILVA CAVALCANTI",
      "serie": "CURSO",
      "status": "presente",
      "notas": { "MAT": 4.40, "FIS": 5.10, "QUIM": 3.80,
                 "PORT": 8.00, "ING": 7.50, "RED": 4.10 },
      "media_oficial": 5.10,
      "media_final_oficial": null
    },
    {
      "nome": "FULANO QUE NAO FEZ A DISCURSIVA",
      "serie": "2º ANO",
      "status": "ausente"
    }
  ]
}

CAMPOS DO CABEÇALHO

- tipo            — sempre "simulado".
- fase            — sempre "discursiva" (este prompt só extrai a 2ª fase).
- banca           — a prova que o simulado imita, do título (ITA, IME, AFA...).
- rotulo          — o código do simulado, do título (S0, S1, S3, S5, S6...).
- data            — "AAAA-MM-DD". Cuidado: costuma vir em DD/MM/AAAA.
                    **Alguns títulos trazem DUAS datas** (ex.: "Simulado IME S6
                    - 11/07/2026 - 14/04/2026"). Nesse caso ponha a PRIMEIRA em
                    "data", a SEGUNDA em "data_secundaria", e **me avise no
                    final, fora do JSON**, que havia duas — não decida sozinho
                    qual é a da 2ª fase. Se não houver data nenhuma, use null.
- data_secundaria — a segunda data do título, se houver. null caso contrário.
- turma           — "novata" ou "veterana". Vale para TODAS as pessoas desta
                    lista. Atenção: "CURSO" NÃO é veterano — é uma SÉRIE dentro
                    da turma novata. A coluna SÉRIE NÃO diz a turma; só o fato
                    de ser a lista da novata ou da veterana diz. Se o arquivo
                    não deixar claro, PARE e pergunte.
- fonte           — cursinho/colégio que publicou (opcional, null).
- materias        — códigos das colunas de NOTA, NA ORDEM EM QUE APARECEM.
                    Use apenas: MAT, FIS, QUIM, PORT, ING, RED, GEO, HIST.
                    Mapeamento das abreviações mais comuns:
                    MAT→MAT · FÍS→FIS · QUÍ/QUÍM→QUIM · PORT/POR→PORT ·
                    ING→ING · RED→RED
- materias_media  — quais matérias a coluna de média combina, SE a planilha
                    disser explicitamente. Como a fórmula é desconhecida, o
                    normal é **null**. Não deduza.

CAMPOS DE CADA PESSOA

- nome           — nome completo, exatamente como na lista (máx. 120). Ver
                   "nomes cortados" abaixo.
- serie          — o conteúdo da coluna SÉRIE, copiado como está ("2º ANO",
                   "3º ANO", "CURSO"). null se não houver a coluna.
- status         — "presente" ou "ausente". Use "ausente" SOMENTE quando a
                   pessoa estiver com as células de nota TODAS vazias — aí ela
                   não fez a discursiva. Em "ausente", omita "notas" e
                   "media_oficial".
                   **Zero NÃO é ausência.** É comum alguém tirar 0,00 em três
                   matérias e ter nota nas outras: isso é "presente", com os
                   zeros copiados. Quem tirou 0,00 em tudo e mesmo assim tem
                   média, também é "presente".
- notas          — objeto código→número decimal, só com as matérias listadas em
                   "materias". Escreva com PONTO no JSON (5.70), mesmo que a
                   planilha use vírgula (5,70). Sempre 0 a 10.
- media_oficial  — o valor da coluna de média **do bloco DISCURSIVO**, copiado.
                   Ver a seção acima. Nas planilhas de bloco único, é a única
                   coluna de média que existe.
- media_final_oficial
                 — o valor da coluna **MÉDIA FINAL**, quando ela existir. Ela só
                   aparece nas planilhas de dois blocos, é sempre a última, e
                   costuma vir em azul. Copie como está.
                   Use `null` quando a planilha não tiver essa coluna — que é o
                   caso das planilhas de bloco único.
                   **Não confunda com a MÉDIA do bloco discursivo.** Numa
                   planilha de dois blocos existem TRÊS colunas de média: a do
                   discursivo (vai em `media_oficial`), a da objetiva (ignore,
                   ela é do outro prompt) e a MÉDIA FINAL (vai aqui).

=============================================================================
CÉLULA VAZIA NÃO É ZERO
=============================================================================

Célula em branco e célula com 0,00 são coisas diferentes. Em branco significa
dado ausente; 0,00 significa que a pessoa fez e zerou aquela matéria.

Essa distinção é mais importante aqui do que na 1ª fase, porque na discursiva
zerar uma questão é comum e legítimo — várias linhas reais têm 0,00 em Física ou
Química com nota alta em Português.

Se uma célula estiver visivelmente vazia (sem nenhum caractere, às vezes com
fundo cinza), PARE e me diga de quem é e qual matéria, em vez de escrever 0.
Nunca preencha um branco com zero por conta própria.

=============================================================================
LINHAS QUE NÃO SÃO PESSOAS
=============================================================================

Ignore linhas de GABARITO, TOTAL, MÁXIMO, REFERÊNCIA, média da turma, contagem
de alunos e qualquer rodapé. Na discursiva a linha de gabarito, quando existe,
costuma ter 10,00 em tudo.

=============================================================================
CONFIRA SE A LISTA NÃO ESTÁ CORTADA
=============================================================================

Print de planilha frequentemente corta o fim da lista. Antes de fechar o JSON,
olhe a última linha: se ela estiver colada na borda inferior da imagem, sem
margem branca depois, provavelmente há mais gente abaixo.

Esse é o erro mais difícil de detectar depois, porque tudo que sobrou está
correto. Se desconfiar, PARE e me avise dizendo qual foi a última linha que você
conseguiu ler.

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
regra de responder apenas com o JSON — junto com o aviso das duas datas.

=============================================================================
CONFERÊNCIA DOS NÚMEROS
=============================================================================

**Limites.** Nenhuma nota passa de 10,00 nem fica abaixo de 0,00. Se você leu
57,0, provavelmente perdeu a vírgula de 5,70.

**A média fica entre a menor e a maior nota da linha.** Média fora desse
intervalo é erro de leitura em algum lugar — releia a linha inteira.

**A lista costuma vir ordenada da maior média para a menor** (pela MÉDIA FINAL,
quando ela existe). Se uma linha quebrar a ordem, releia a média dela. Mas não
reordene nada e não "corrija" — só confira e, se persistir, me avise.

**A média do DISCURSIVO no ITA** — conferida contra a planilha do S5, linha por
linha, incluindo casos extremos:

    MEDIA = (2·MAT + 2·QUÍ + 2·FIS + POR + RED) / 8

Ou seja, cada matéria de exatas pesa o dobro de Português e de Redação.

    Exemplos reais: 6,00 6,35 3,40 · 6,67 7,20 → 45,37/8 = 5,67 ✓
                    3,80 4,35 4,30 · 6,00 5,00 → 35,90/8 = 4,49 ✓
                    0,00 0,00 0,20 · 0,00 0,00 →  0,40/8 = 0,05 ✓

**A MÉDIA FINAL, quando a planilha traz os dois blocos** — também conferida no
S5, inclusive em quem faltou a uma das fases:

    MEDIA FINAL = 0,8 × MÉDIA(discursivo) + 0,2 × MÉDIA(objetiva)

    Exemplos reais: 5,67 e 5,56 → 5,65 ✓
                    4,28 e 3,61 → 4,15 ✓
                    3,14 e 0,00 → 2,51 ✓   (faltou a objetiva)
                    0,00 e 3,61 → 0,72 ✓   (faltou a discursiva)

**Use essas fórmulas SÓ para conferir a sua leitura, nunca para preencher.** Se
a conta não fechar, o erro é seu: releia a linha. Se a planilha traz o número, é
o número dela que vai no JSON, mesmo que a conta discorde — o colégio pode mudar
o peso sem avisar, e aí o copiado continua certo e o calculado não.

**A média do IME não segue essas fórmulas.** A planilha do IME S6 traz seis
matérias (MAT, FÍS, QUÍ, PORT, ING, RED) e uma coluna "Média" que **não é
reproduzível** como média ponderada das próprias seis colunas — o que indica que
ela já é uma média final, envolvendo a 1ª fase. Enquanto isso não for confirmado
com a planilha da 1ª fase do IME, **copie e não interprete**.

=============================================================================
OUTROS CUIDADOS
=============================================================================

- Cor de fundo da linha não significa nada. Quem diz a série é a coluna SÉRIE.
- Nome que quebra em duas linhas na tabela deve virar um nome só.
- Não pode haver nomes repetidos na mesma lista.
- Não reordene as pessoas: mantenha a ordem em que aparecem.
