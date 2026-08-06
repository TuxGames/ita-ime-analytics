Você vai ler um listão de resultado de concurso militar (PDF, print ou foto) e
convertê-lo em JSON para importar no ITA-IME Analytics.

REGRAS

1. Responda APENAS com o JSON. Sem texto antes, sem texto depois, sem ```.
2. UM JSON por turma. Se o arquivo tiver "novata" e "veterana" (ou dois arquivos),
   gere dois JSONs separados, um de cada vez.
3. Não invente, não arredonde e não complete dados. Copie os números exatamente
   como aparecem. Se um valor estiver ilegível, pare e me diga qual é, em vez de
   chutar.
4. Se o listão separar as pessoas em seções (classificados / sem aproveitamento /
   não encontrados), respeite essa separação no campo "status".

FORMATO

{
  "tipo": "oficial",
  "concurso": "AFA/EPCAR 2027",
  "turma": "novata",
  "fonte": "GGE",
  "data": "2026-04-11",
  "escala": 10,
  "materias": ["PORT", "FIS", "MAT", "ING"],
  "metrica": "MP",
  "resultados": [
    {
      "nome": "ARTHUR TELES VILA NOVA",
      "status": "classificado",
      "classificacao": 339,
      "metrica": 6.7188,
      "notas": { "PORT": 6.25, "FIS": 6.875, "MAT": 6.25, "ING": 7.5 }
    },
    {
      "nome": "RODRIGO SOARES NEGREIROS",
      "status": "sem_aproveitamento",
      "classificacao": null,
      "metrica": 5.625,
      "notas": { "PORT": 3.75, "FIS": 5.625, "MAT": 6.875, "ING": 6.25 }
    },
    { "nome": "CAIO GOMES DE LIRA", "status": "nao_encontrado" }
  ]
}

CAMPOS DO CABEÇALHO

- tipo      — sempre "oficial".
- concurso  — nome da prova, com o ano (máx. 80 caracteres).
- turma     — "novata" ou "veterana". Atenção: "CURSO" NÃO é veterano; quem está
              marcado como CURSO pertence à turma novata (só não está mais no
              ensino médio). Turma veterana é sempre uma lista separada.
- fonte     — cursinho/colégio que publicou (opcional).
- data      — "AAAA-MM-DD". Se o listão não trouxer data, use null.
- escala    — nota máxima das notas por matéria (10 quando as notas são 0–10).
- materias  — códigos das colunas de nota, na ordem em que aparecem. Use apenas:
              MAT, FIS, QUI, PORT, ING, RED, GEO, HIST.
- metrica   — nome da coluna que ordena o ranking oficial (ex.: "MP"). Se não
              houver, use null.

CAMPOS DE CADA PESSOA

- nome           — nome completo, exatamente como no listão (máx. 120).
- status         — um destes três, exatamente:
                   "classificado"       tem posição oficial na lista;
                   "sem_aproveitamento" fez a prova mas ficou sem posição;
                   "nao_encontrado"     não apareceu no cadastro do concurso.
- classificacao  — a posição NACIONAL/oficial do concurso (não o número de ordem
                   da tabela do cursinho). Obrigatório para "classificado";
                   null nos outros dois.
- metrica        — o valor da métrica de ranking (MP, média etc.). null se não houver.
- notas          — objeto código→nota, só com as matérias listadas em "materias".
                   Toda nota tem de estar entre 0 e o valor de "escala".
                   Em "nao_encontrado", omita "notas".

CUIDADOS QUE JÁ DERAM PROBLEMA

- Linha 100% zerada no listão do concurso é resultado real (a pessoa fez e zerou),
  não ausência: mantenha com as notas 0.
- Nome que quebra em duas linhas na tabela deve virar um nome só.
- Não deduza a posição oficial pela ordem das linhas: copie a coluna de
  classificação. Se não existir coluna de posição oficial, o status não é
  "classificado".
- Não pode haver duas pessoas com a mesma classificação nem nomes repetidos.
