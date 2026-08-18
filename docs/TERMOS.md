# Termos de uso e aviso de privacidade

**ITA-IME Analytics** · versão de 15 de agosto de 2026

Este texto explica o que o site é, que dados existem aqui, quem consegue ver
cada coisa e o que você pode exigir. Está em português comum de propósito: se
alguma parte não estiver clara, é falha do texto e eu quero saber.

---

## 1. O que é este site, e o que ele não é

O ITA-IME Analytics é um **projeto pessoal**, feito e mantido por um aluno, sem
fins lucrativos e **sem vínculo oficial com o colégio**, com o ITA, com o IME ou
com qualquer banca. Não é sistema do colégio, não substitui nenhum sistema do
colégio e nada aqui tem valor oficial.

Ele existe para uma coisa: transformar os rankings de simulado, que hoje saem em
planilha e somem, em histórico que dá para acompanhar ao longo do tempo.

Não há cobrança, não há anúncio, e seus dados não são vendidos nem cedidos a
ninguém. Não existe rastreamento de publicidade no site.

---

## 2. Sua conta

Para usar, você cria uma conta com nome de usuário e senha.

- A senha é guardada **criptografada** (bcrypt). Nem eu consigo lê-la. Se
  esquecer, ela é redefinida, nunca recuperada.
- Não é pedido e-mail, telefone, CPF, endereço, data de nascimento nem nenhum
  documento. O site não tem esses dados porque nunca os pediu.
- Use uma senha que você não use em outro lugar. Este é um projeto pequeno,
  hospedado num plano gratuito, e você deve tratá-lo como tal.

Você é responsável pelo que faz logado na sua conta. Não empreste, e não tente
acessar a conta de outra pessoa.

---

## 3. Que dados existem aqui

São três origens diferentes, com regras diferentes. A distinção importa e é o
centro deste documento.

### a) O que você digita

Simulados que você registra, plano de estudos, registro de questões, sessões de
treino cronometrado, matérias que você escolheu acompanhar.

**Isto é seu.** Ninguém além de você vê, com uma única exceção: se você entrar
num grupo, os membros daquele grupo veem o volume de questões e simulados do
período. Você escolhe entrar, e pode sair quando quiser.

### b) O que o colégio divulga

Os rankings de simulado e os listões de resultado que o colégio distribui para a
turma. Contêm nome e desempenho dos alunos, e são importados aqui como chegam.

**Esse dado não nasce no site.** Ele já é distribuído pelo colégio a todos os
alunos. O que o site faz é organizá-lo ao longo do tempo.

### c) O que o site calcula

Médias, posições, percentis, evolução. Derivam das duas origens acima.

---

## 4. Quem vê o quê

| Você é | Vê os rankings da turma e listões | Vê estudo e treino de outros |
|---|---|---|
| conta nova, sem código | não | não |
| conta com código de acesso | sim | não |
| professor ou coordenação | sim | **não** |
| membro de um grupo | — | só o volume, só de quem aceitou entrar |
| administrador | sim | tem acesso técnico ao banco |

Três pontos que merecem destaque:

**O código de acesso.** Ver nome e nota da turma exige um código que eu entrego
pessoalmente. Sem ele, a conta funciona normalmente para uso próprio — treino,
estudos, simulados seus — mas NÃO enxerga dado de outras pessoas. Isso é
proposital: quem chega de fora não deveria ver a turma.

**Professores e coordenação.** Veem desempenho em simulados e listões, que é o
dado que o colégio já tem. **NÃO veem** seu tempo de estudo, suas sessões de
treino nem seu registro de questões. Isso é regra escrita no código, não
promessa: o que você registra sobre seus hábitos não é mostrado a professor.

**O administrador.** Sou eu, e seria desonesto escrever que não tenho acesso.
Quem administra um banco de dados vê o que está nele. O que eu me comprometo a
fazer: não usar esse acesso para bisbilhotar hábito de estudo de ninguém, não
mostrar isso a terceiros, e não tirar dado do site para outro lugar. Se isso não
for suficiente para você — e é uma posição legítima —, use o site só para o que
não te incomoda registrar.

---

## 5. Se você aparece nos rankings mas nunca criou conta

Esta seção é para quem não é usuário do site.

Os rankings importados trazem os nomes como o colégio os divulgou, inclusive de
alunos que nunca criaram conta aqui e nunca concordaram com nada. Isso merece
ser dito com todas as letras, em vez de ficar implícito.

O que vale para essas pessoas:

- Aparece o **nome e o desempenho como já constam na lista divulgada pelo
  colégio**. Nada além disso: não há e-mail, telefone, foto, endereço ou
  qualquer dado de contato.
- Essa lista **não é pública na internet**. É preciso ter conta e código para
  ver.
- **Qualquer pessoa pode pedir para ser removida**, sem justificar o motivo, e
  eu removo. É só falar comigo. Se preferir, dá para substituir o nome por
  iniciais em vez de apagar o histórico.

Se você é responsável por um aluno e quer que o nome dele saia, o pedido vale do
mesmo jeito e não precisa de explicação.

---

## 6. Seus direitos

Independente de formalidade jurídica, e inspirado no que a LGPD garante:

- **Ver** tudo que o site tem sobre você.
- **Exportar** seus dados (a função existe no site).
- **Corrigir** o que estiver errado.
- **Apagar** sua conta e o que você registrou.
- **Sair dos rankings**, como descrito acima.

Para qualquer um deles, é só pedir. Não há formulário, prazo burocrático nem
necessidade de justificar.

---

## 7. Menores de idade

A turma é majoritariamente formada por adolescentes, então: se você tem menos de
18 anos, use este site com o conhecimento dos seus responsáveis, e mostre esta
página a eles se eles quiserem entender o que é. Qualquer pedido de remoção
feito por um responsável é atendido.

---

## 8. Limites honestos

Isto é um projeto de estudante rodando em hospedagem gratuita. Portanto:

- **Pode sair do ar**, sem aviso, temporária ou definitivamente.
- **Pode ter erro.** Número errado na tela é possível; se você vir um, me avise.
- **Backup existe, mas não é garantia.** Não use este site como único registro
  de nada que você não possa perder.
- Não há suporte, prazo de resposta nem compromisso de disponibilidade.

O site é oferecido como está. Você o usa por conta própria.

---

## 9. O que não fazer

- Tentar acessar conta ou dado de outra pessoa.
- Copiar os rankings para fora daqui e espalhar. O dado circula na turma; isso
  não faz dele material de divulgação.
- Usar o desempenho de alguém para constranger, expor ou humilhar. É o único
  item desta lista que me faria fechar o site.

---

## 10. Mudanças

Este texto pode mudar conforme o site muda. Alteração relevante é avisada dentro
do site, com a data acima atualizada.

---

## 11. Contato

Fale comigo diretamente — pessoalmente, ou pelos canais que a turma já usa.
Pedido de remoção, correção ou dúvida sobre este texto não precisa de formato
nenhum.
