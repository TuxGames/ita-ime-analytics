import enum
import json
import unicodedata
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin

from .extensions import bcrypt, db, login_manager


def normalizar_nome(texto) -> str:
    """MAIÚSCULAS, sem acento, espaços colapsados.

    É a chave usada para casar o nome que aparece no listão do concurso com o
    `nome_oficial` que o usuário declarou no perfil."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def utcnow():
    return datetime.now(timezone.utc)


def nota_proporcional(pares_acertos_total, escala: float = 100.0):
    """Nota PROPORCIONAL às questões, na escala pedida. None se não há questão.

    nota = (soma dos acertos) / (soma do total de questões) x escala

    É a mesma conta de `SimuladoTurma.nota_de`, que reproduz a fórmula do
    colégio. Antes o simulado PESSOAL usava média simples dos percentuais, e as
    duas divergiam quando as matérias tinham pesos diferentes (IME 15/15/10):
    a mesma prova aparecia como 48,9 numa tela e 5,00 na outra.

    A escala muda por tela, a conta não: o simulado pessoal usa 100 (mostrado
    como porcentagem) e o ranking da turma usa 10 (reproduz o mural do colégio
    na vírgula). Uma régua só, duas apresentações.
    """
    soma_acertos = soma_questoes = 0
    for acertos, total in pares_acertos_total:
        if acertos is None or not total:
            continue
        soma_acertos += acertos
        soma_questoes += total
    if not soma_questoes:
        return None
    return round(escala * soma_acertos / soma_questoes, 2)


def posicoes_por_nota(pares: list) -> list:
    """[(item, nota)] -> [(posicao, item, nota)], da maior nota para a menor.

    Empate fica na mesma posição. Renumera SEMPRE a partir de 1 dentro do que
    recebeu: é isso que faz um recorte (só veteranos, só os membros de um
    grupo) mostrar "1º" para o primeiro do recorte, em vez de arrastar a
    posição que a pessoa tinha na lista inteira.

    Vive solto aqui porque o ranking da turma e o placar do grupo usam a mesma
    regra — duplicar significaria os dois divergirem no primeiro empate."""
    pares = sorted(pares, key=lambda par: -par[1])
    saida, anterior, posicao = [], None, 0
    for indice, (item, nota) in enumerate(pares, start=1):
        if nota != anterior:
            posicao, anterior = indice, nota
        saida.append((posicao, item, nota))
    return saida


class Materia(enum.Enum):
    MATEMATICA = "Matemática"
    FISICA = "Física"
    QUIMICA = "Química"
    PORTUGUES = "Português"
    INGLES = "Inglês"
    REDACAO = "Redação"
    # Discretas: só caem em um concurso específico (ex.: EN). Ficam escondidas
    # por padrão nos formulários.
    GEOGRAFIA = "Geografia"
    HISTORIA = "História"
    # Usada só no cronograma de estudos (não é matéria de simulado/concurso).
    OUTROS = "Outros"


# Matérias "principais" que aparecem em destaque; as demais são as discretas.
MATERIAS_PRINCIPAIS = [
    Materia.MATEMATICA,
    Materia.FISICA,
    Materia.QUIMICA,
    Materia.PORTUGUES,
    Materia.INGLES,
    Materia.REDACAO,
]
MATERIAS_DISCRETAS = [Materia.GEOGRAFIA, Materia.HISTORIA]
# Matérias de simulado/concurso (as 8 acadêmicas — sem "Outros").
MATERIAS_SIMULADO = MATERIAS_PRINCIPAIS + MATERIAS_DISCRETAS
# Matérias do cronograma de estudos: principais + "Outros" (sem Geografia/História).
MATERIAS_ESTUDO = MATERIAS_PRINCIPAIS + [Materia.OUTROS]

# Quantidade de questões por matéria nos simulados que o colégio aplica. É fixa
# por banca, então o admin não precisa digitar a cada importação.
QUESTOES_PADRAO = {
    "ITA": {"MATEMATICA": 12, "FISICA": 12, "QUIMICA": 12, "INGLES": 12},
    "IME": {"MATEMATICA": 15, "FISICA": 15, "QUIMICA": 10},
}

# Turma é um recorte do colégio, não do concurso: a classificação é nacional e a
# prova é uma só. Por isso a turma vive em CADA PESSOA (nas linhas importadas), e
# não no cabeçalho do resultado — um concurso tem um registro só, com as duas
# turmas dentro dele.
TURMAS = ("novata", "veterana")
TURMA_LABEL = {"novata": "Turma novata", "veterana": "Turma veterana"}
TURMA_CURTO = {"novata": "Novatos", "veterana": "Veteranos"}

# Rótulo de exibição da fase do simulado (mesmos valores de SimuladoTurma.FASES
# e Simulado.fase). Usado no título curto do simulado pessoal.
FASE_LABEL = {"objetiva": "1ª fase", "discursiva": "2ª fase"}


def turma_valida(valor):
    """Devolve a turma se for uma das conhecidas, senão None (filtro inválido)."""
    return valor if valor in TURMAS else None


# Dias da semana indexados por date.weekday() (0 = segunda ... 6 = domingo)
DIAS_SEMANA = [
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    # Professor/coordenação: SÓ OLHA. Vê a ficha do aluno, o ranking da turma e
    # os listões — nunca estudo, treino ou registro de questões, que a pessoa
    # digitou aqui achando que era dela. Papel distinto de admin: não importa,
    # não edita, não apaga, não emite código, não mescla aluno.
    is_professor = db.Column(db.Boolean, nullable=False, default=False)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    # Resgatou um código de convite? Enquanto False a conta não acessa nada além
    # da tela do código e do logout. Default False: conta nova nasce trancada.
    # As contas que já existiam quando isto entrou foram marcadas True na
    # migration — senão o deploy trancaria todo mundo sem código para digitar.
    convite_ok = db.Column(db.Boolean, nullable=False, default=False)
    # Nome completo como aparece nos listões dos concursos. É o que liga este
    # usuário às linhas dos resultados oficiais importados pelo admin.
    nome_oficial = db.Column(db.String(120), nullable=True)
    # Matérias que o usuário quer acompanhar de perto (filtro "mostrar apenas"
    # do ranking, Fase D). Mesma convenção de Concurso.materias_csv: nomes do
    # enum Materia separados por vírgula. NULL/vazio = sem preferência
    # cadastrada (o ranking usa "todas" como default nesse caso).
    materias_csv = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    simulados = db.relationship("Simulado", back_populates="user", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def materias(self) -> list["Materia"]:
        """Lista de Materia do perfil, na ordem canônica do enum. Vazio = sem preferência."""
        nomes = {n for n in (self.materias_csv or "").split(",") if n in Materia.__members__}
        return [m for m in Materia if m.name in nomes]

    def set_materias(self, materias) -> None:
        """Grava a lista de Materia escolhida (ordena pelo enum, ignora duplicatas)."""
        escolhidas = {m.name for m in materias}
        self.materias_csv = ",".join(m.name for m in Materia if m.name in escolhidas) or None

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


class Aluno(db.Model):
    """Uma pessoa do colégio, estável ao longo das provas.

    Antes disso, quem aparecia em 8 simulados eram 8 linhas soltas com o mesmo
    nome — não havia onde pendurar "a turma dele" nem "a evolução dele".

    `turma` e `serie` aqui são o estado ATUAL (editável pelo admin). O que a
    pessoa era em CADA prova continua na linha importada: é registro histórico e
    é o que sustenta a conferência de série que regride."""

    __tablename__ = "alunos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    nome_norm = db.Column(db.String(120), nullable=False, unique=True, index=True)
    turma = db.Column(db.String(20), nullable=True)
    serie = db.Column(db.String(20), nullable=True)
    # O vínculo "sou eu" mora aqui agora; as linhas herdam daqui.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    # True = vínculo AUTORITATIVO, decidido por gente, e não deduzido do nome.
    # Hoje vem de duas origens: resgate de código e vínculo feito à mão pelo
    # admin. O nome do campo ficou estreito (nem todo caso "veio de código"),
    # mas o significado é esse — se um dia aparecer um terceiro caso que precise
    # ser distinguido, aí vale trocar por um campo de ORIGEM.
    # `vinculo.revincular()` refaz os vínculos por nome depois de
    # cada import, e sem isto desfaria o que o código estabeleceu. Vive no Aluno
    # (e não derivada da tabela de convites) porque descreve o vínculo ATUAL:
    # quando o admin desvincula para corrigir um erro, volta a False e o
    # casamento por nome pode agir de novo, sem depender de interpretar o que
    # significa um convite usado cujo vínculo foi desfeito.
    vinculo_por_codigo = db.Column(db.Boolean, nullable=False, default=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")
    apelidos = db.relationship(
        "AlunoApelido", back_populates="aluno", cascade="all, delete-orphan"
    )

    @property
    def turma_label(self) -> str:
        return TURMA_LABEL.get(self.turma, self.turma or "—")

    @property
    def turma_curto(self) -> str:
        return TURMA_CURTO.get(self.turma, self.turma or "—")

    def __repr__(self):
        return f"<Aluno {self.nome}>"


class ConviteAluno(db.Model):
    """Código de convite de USO ÚNICO, emitido pelo admin para UM aluno.

    O cadastro é aberto, mas a conta nasce trancada: sem resgatar um código não
    se acessa nada. Como o código é específico do aluno, resgatar já cria o
    vínculo conta ↔ aluno — o admin não precisa casar nome depois.

    Não guarda hash: o código não é segredo de longo prazo, é de uso único e
    circula por WhatsApp. O que protege é ser único, curto e descartável."""

    __tablename__ = "convites_aluno"

    # Sem O/0 e sem I/1/L: o código é ditado no WhatsApp e digitado no celular.
    ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    TAMANHO = 8

    # "aluno": pertence a um aluno e o resgate cria o vínculo.
    # "coringa": libera a conta e NÃO vincula a ninguém — coordenador, professor,
    # conta de teste. O tipo é explícito em vez de deduzido de `aluno_id IS NULL`
    # porque a diferença é de intenção, não de preenchimento: um convite de aluno
    # com aluno apagado também ficaria nulo, e os dois casos não são a mesma
    # coisa. Explícito também deixa a consulta e a tela lerem direto.
    TIPOS = ("aluno", "coringa")

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, default="aluno")
    # NULL quando tipo == "coringa".
    aluno_id = db.Column(
        db.Integer, db.ForeignKey("alunos.id"), nullable=True, index=True
    )
    # Para que serve o coringa ("coordenador", "professor de física"). Sem isso,
    # daqui a um mês ninguém sabe para quem foi cada um. Obrigatório no coringa,
    # ignorado no convite de aluno, que já se identifica pelo nome do aluno.
    rotulo = db.Column(db.String(60), nullable=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    usado_por_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    usado_em = db.Column(db.DateTime, nullable=True)

    aluno = db.relationship("Aluno", foreign_keys=[aluno_id])
    criador = db.relationship("User", foreign_keys=[created_by])
    usuario = db.relationship("User", foreign_keys=[usado_por_user_id])

    @property
    def usado(self) -> bool:
        return self.usado_por_user_id is not None

    @property
    def eh_coringa(self) -> bool:
        return self.tipo == "coringa"

    @property
    def destino(self) -> str:
        """Para quem é este convite, em uma linha — o que a tela do admin mostra."""
        if self.eh_coringa:
            return self.rotulo or "sem rótulo"
        return self.aluno.nome if self.aluno else "aluno removido"

    @property
    def formatado(self) -> str:
        """"ABCD-2345" — dois blocos, mais fácil de ditar e conferir."""
        meio = len(self.codigo) // 2
        return f"{self.codigo[:meio]}-{self.codigo[meio:]}"

    def __repr__(self):
        return f"<ConviteAluno {self.codigo} aluno={self.aluno_id}>"


class AlunoApelido(db.Model):
    """Grafia alternativa que resolve para o mesmo aluno.

    Nasce de um merge (guardando o nome do absorvido) ou de cadastro manual. O
    unique global impede que a mesma grafia aponte para dois alunos — se pudesse,
    a resolução de nome deixaria de ser determinística."""

    __tablename__ = "aluno_apelidos"

    ORIGENS = ("merge", "manual")

    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(
        db.Integer, db.ForeignKey("alunos.id"), nullable=False, index=True
    )
    nome_norm = db.Column(db.String(120), nullable=False, unique=True, index=True)
    origem = db.Column(db.String(20), nullable=True)

    aluno = db.relationship("Aluno", back_populates="apelidos")


class Concurso(db.Model):
    __tablename__ = "concursos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)
    data_prova = db.Column(db.Date, nullable=False)
    # Fim do intervalo, quando a fase dura vários dias (ex.: ITA 2ª Fase 20→23).
    # NULL = prova de um dia só (usa só data_prova).
    data_fim = db.Column(db.Date, nullable=True)
    # Matérias que caem neste concurso, como nomes do enum separados por vírgula
    # (ex.: "MATEMATICA,FISICA,REDACAO"). Vazio/NULL = todas as principais (default
    # retrocompatível para concursos criados antes deste campo existir).
    materias_csv = db.Column(db.String(200), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    simulados = db.relationship("Simulado", back_populates="concurso", lazy="dynamic")

    SEP = " - "

    @staticmethod
    def compor_nome(banca: str, etapa: str | None) -> str:
        banca = (banca or "").strip()
        etapa = (etapa or "").strip()
        return f"{banca}{Concurso.SEP}{etapa}" if etapa else banca

    @property
    def dias_prova(self) -> list:
        """Todos os dias de prova (início ao fim). Um só dia se data_fim vazio."""
        fim = self.data_fim if self.data_fim and self.data_fim >= self.data_prova else self.data_prova
        n = (fim - self.data_prova).days
        return [self.data_prova + timedelta(days=i) for i in range(n + 1)]

    @property
    def banca(self) -> str:
        return self.nome.split(self.SEP, 1)[0].strip()

    @property
    def etapa(self) -> str:
        partes = self.nome.split(self.SEP, 1)
        return partes[1].strip() if len(partes) == 2 else ""

    @property
    def materias(self) -> list["Materia"]:
        """Lista de Materia deste concurso, na ordem canônica do enum."""
        if not self.materias_csv:
            return list(MATERIAS_PRINCIPAIS)
        nomes = {n for n in self.materias_csv.split(",") if n in Materia.__members__}
        return [m for m in Materia if m.name in nomes]

    def set_materias(self, materias) -> None:
        """Grava a lista de Materia (ordena pelo enum, ignora duplicatas)."""
        escolhidas = {m.name for m in materias}
        self.materias_csv = ",".join(m.name for m in Materia if m.name in escolhidas)

    def __repr__(self):
        return f"<Concurso {self.nome}>"


class Simulado(db.Model):
    __tablename__ = "simulados"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    concurso_id = db.Column(db.Integer, db.ForeignKey("concursos.id"), nullable=False, index=True)
    # Rótulo que o colégio dá à prova (S0, S1, S3...). Serve para identificar o
    # mesmo simulado entre pessoas diferentes.
    rotulo = db.Column(db.String(20), nullable=True)
    # Mesmos valores de SimuladoTurma.FASES ("objetiva"/"discursiva"). Opcional:
    # quem digita à mão pode não saber ou não se importar; quem vem do ranking
    # da turma sempre traz junto (Bloco 1 — sem isso a fase se perdia no sync).
    fase = db.Column(db.String(20), nullable=True)
    data_simulado = db.Column(db.Date, nullable=False)
    nota_geral = db.Column(db.Float, nullable=False)
    # True = nota_geral foi calculada (média dos % das matérias); False = digitada.
    nota_automatica = db.Column(db.Boolean, nullable=False, default=False)
    posicao_estimada = db.Column(db.Integer, nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    # NULL/"manual" = digitado pelo dono; "import" = trazido do ranking da turma.
    # Registro manual nunca é sobrescrito por importação.
    origem = db.Column(db.String(10), nullable=True)
    # Linha do ranking da turma que gerou este simulado, quando trazido pela
    # Sincronização em lote (Fase C). É o que garante idempotência: sincronizar
    # duas vezes não duplica, porque a segunda vez encontra o par já gravado
    # aqui e pula a linha. NULL para simulados digitados à mão.
    turma_linha_id = db.Column(
        db.Integer, db.ForeignKey("simulado_turma_linhas.id"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "turma_linha_id", name="uq_simulados_user_turma_linha"),
    )

    @property
    def veio_de_import(self) -> bool:
        return self.origem == "import"

    @property
    def titulo_curto(self) -> str:
        """"ITA S5 · 1ª fase" — banca (sem ano) + rótulo + fase, quando existirem.

        Hoje `rotulo` e `concurso.nome` aparecem soltos nas telas; isto junta os
        pedaços num título só, sem criar Concurso nenhum novo para isso."""
        from .grouping import compor_titulo

        return compor_titulo(self.concurso.nome, self.rotulo, self.fase)

    user = db.relationship("User", back_populates="simulados")
    concurso = db.relationship("Concurso", back_populates="simulados")
    materias = db.relationship(
        "SimuladoMateria",
        back_populates="simulado",
        cascade="all, delete-orphan",
        order_by="SimuladoMateria.materia",
    )

    def __repr__(self):
        return f"<Simulado {self.id} user={self.user_id}>"


class SimuladoMateria(db.Model):
    __tablename__ = "simulado_materias"
    __table_args__ = (db.UniqueConstraint("simulado_id", "materia"),)

    id = db.Column(db.Integer, primary_key=True)
    simulado_id = db.Column(
        db.Integer, db.ForeignKey("simulados.id"), nullable=False, index=True
    )
    materia = db.Column(db.Enum(Materia, native_enum=False, length=20), nullable=False)
    acertos = db.Column(db.Integer, nullable=False)
    total_questoes = db.Column(db.Integer, nullable=False)

    simulado = db.relationship("Simulado", back_populates="materias")

    @property
    def percentual(self) -> float:
        if not self.total_questoes:
            return 0.0
        return round(100.0 * self.acertos / self.total_questoes, 1)


class PlanoEstudoDia(db.Model):
    """Uma matéria planejada para um dia da semana (o plano é editável a qualquer hora)."""

    __tablename__ = "plano_estudo_dias"
    __table_args__ = (db.UniqueConstraint("user_id", "dia_semana", "materia"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=segunda ... 6=domingo
    materia = db.Column(db.Enum(Materia, native_enum=False, length=20), nullable=False)


class RegistroEstudo(db.Model):
    """Quantas questões o usuário fez (e acertou) de uma matéria num dia."""

    __tablename__ = "registros_estudo"
    __table_args__ = (db.UniqueConstraint("user_id", "data", "materia"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    data = db.Column(db.Date, nullable=False, index=True)
    materia = db.Column(db.Enum(Materia, native_enum=False, length=20), nullable=False)
    questoes = db.Column(db.Integer, nullable=False)
    acertos = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def percentual(self) -> float:
        if not self.questoes:
            return 0.0
        return round(100.0 * self.acertos / self.questoes, 1)


class SimuladoTurma(db.Model):
    """O ranking de um simulado do colégio (uma turma), importado pelo admin.

    Diferente de Simulado (o registro privado de cada um), aqui está a turma
    inteira na mesma prova — o que permite comparar e ranquear."""

    __tablename__ = "simulados_turma"
    # A data entra na chave porque "S5" repete todo ano: sem ela, dois simulados
    # de anos diferentes com o mesmo rótulo colidiriam.
    __table_args__ = (
        db.UniqueConstraint("banca", "rotulo", "data", name="uq_simulados_turma_prova"),
    )

    FASES = ("objetiva", "discursiva")

    id = db.Column(db.Integer, primary_key=True)
    banca = db.Column(db.String(40), nullable=False)  # ITA, IME...
    rotulo = db.Column(db.String(20), nullable=False)  # S0, S3...
    data = db.Column(db.Date, nullable=False)
    # Só a objetiva é importável hoje; o campo existe para a discursiva entrar
    # depois sem outra migration de schema.
    fase = db.Column(db.String(20), nullable=False, default="objetiva")
    fonte = db.Column(db.String(40), nullable=True)
    materias_csv = db.Column(db.String(200), nullable=False, default="")
    # Matérias que compõem a MÉDIA oficial do colégio (para o atalho "Oficial").
    materias_media_csv = db.Column(db.String(200), nullable=True)
    # {"MATEMATICA": 12, ...} — total de questões de cada matéria nesta prova.
    questoes_json = db.Column(db.Text, nullable=False, default="{}")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    linhas = db.relationship(
        "SimuladoTurmaLinha", back_populates="turma_obj", cascade="all, delete-orphan"
    )

    @staticmethod
    def _do_csv(csv_texto) -> list:
        nomes = {n for n in (csv_texto or "").split(",") if n in Materia.__members__}
        return [m for m in Materia if m.name in nomes]

    @property
    def materias(self) -> list["Materia"]:
        return self._do_csv(self.materias_csv)

    @property
    def materias_media(self) -> list["Materia"]:
        return self._do_csv(self.materias_media_csv)

    def set_materias(self, materias, campo="materias_csv") -> None:
        escolhidas = {m.name for m in materias}
        setattr(
            self, campo, ",".join(m.name for m in Materia if m.name in escolhidas)
        )

    @property
    def questoes(self) -> dict:
        try:
            return json.loads(self.questoes_json or "{}")
        except ValueError:
            return {}

    def set_questoes(self, questoes: dict) -> None:
        self.questoes_json = json.dumps(questoes)

    @property
    def nome(self) -> str:
        return f"{self.banca} {self.rotulo}"

    # Recortes com filtro de turma opcional (por isso métodos, não properties).
    def presentes(self, turma=None) -> list["SimuladoTurmaLinha"]:
        return [
            ln
            for ln in self.linhas
            if ln.status == "presente" and (turma is None or ln.turma == turma)
        ]

    def ausentes(self, turma=None) -> list["SimuladoTurmaLinha"]:
        return [
            ln
            for ln in self.linhas
            if ln.status == "ausente" and (turma is None or ln.turma == turma)
        ]

    def total_de(self, turma) -> int:
        return sum(1 for ln in self.linhas if ln.turma == turma)

    @property
    def turmas_presentes(self) -> list[str]:
        existentes = {ln.turma for ln in self.linhas}
        return [t for t in TURMAS if t in existentes]

    def nota_de(self, linha, materias) -> float | None:
        """Nota nas `materias` escolhidas, escala 0–10, PROPORCIONAL às questões.

        nota = (soma dos acertos das matérias consideradas) /
               (soma do total de questões dessas matérias) * 10

        É a mesma conta que o colégio faz (bate com `media_oficial` guardado no
        import — ex.: IME MAT 15/FIS 15/QUIM 10, acertos 11+11+4 -> 26/40*10 =
        6,50). No ITA (12 questões em todas as matérias) essa fórmula coincide
        com a média simples dos percentuais, então não muda nada relativo ao
        ITA — a diferença só aparece quando as matérias têm pesos diferentes,
        como no IME."""
        acertos, questoes = linha.acertos, self.questoes
        soma_acertos, soma_questoes = 0, 0
        for materia in materias:
            total = questoes.get(materia.name)
            valor = acertos.get(materia.name)
            if total and valor is not None:
                soma_acertos += valor
                soma_questoes += total
        if not soma_questoes:
            return None
        return round(10.0 * soma_acertos / soma_questoes, 2)

    def ranking(self, materias, turma=None) -> list:
        """[(posicao, linha, nota)] ordenado por nota. Empate = mesma posição.

        Com filtro de turma, as posições são RENUMERADAS a partir de 1 dentro do
        recorte: numa lista só de veteranos, o primeiro é 1º — não faz sentido
        mostrar "7º" porque havia novatos na frente numa lista que não está ali."""
        pares = []
        for linha in self.presentes(turma):
            nota = self.nota_de(linha, materias)
            if nota is not None:
                pares.append((linha, nota))
        return posicoes_por_nota(pares)

    def __repr__(self):
        return f"<SimuladoTurma {self.nome} {self.data}>"


class SimuladoTurmaLinha(db.Model):
    """Uma pessoa dentro do ranking de um simulado da turma."""

    __tablename__ = "simulado_turma_linhas"

    STATUS = ("presente", "ausente")

    id = db.Column(db.Integer, primary_key=True)
    turma_id = db.Column(
        db.Integer, db.ForeignKey("simulados_turma.id"), nullable=False, index=True
    )
    nome = db.Column(db.String(120), nullable=False)
    nome_norm = db.Column(db.String(120), nullable=False, index=True)
    # Série dentro da turma: "2º ANO", "3º ANO", "CURSO". Não confundir com turma:
    # "CURSO" é uma série DA turma novata, e turma vem do cabeçalho do JSON.
    serie = db.Column(db.String(20), nullable=True)
    turma = db.Column(db.String(20), nullable=False, index=True)
    # Identidade canônica. `serie`/`turma` acima seguem sendo o histórico daquela
    # prova — é o que permite detectar série que regride entre simulados.
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False)
    # {"MATEMATICA": 9, ...} — questões CERTAS, não percentual.
    acertos_json = db.Column(db.Text, nullable=True)
    media_oficial = db.Column(db.Float, nullable=True)
    geral_oficial = db.Column(db.Float, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    # Marca edição manual do admin. Um reimport da turma NÃO apaga uma linha
    # editada silenciosamente — ele só avisa no preview (ver B.1 do plano).
    editado_em = db.Column(db.DateTime, nullable=True)
    editado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    turma_obj = db.relationship("SimuladoTurma", back_populates="linhas")
    user = db.relationship("User", foreign_keys=[user_id])
    editor = db.relationship("User", foreign_keys=[editado_por])

    @property
    def acertos(self) -> dict:
        if not self.acertos_json:
            return {}
        try:
            return json.loads(self.acertos_json)
        except ValueError:
            return {}

    def set_acertos(self, acertos: dict) -> None:
        self.acertos_json = json.dumps(acertos) if acertos else None

    @property
    def turma_label(self) -> str:
        return TURMA_LABEL.get(self.turma, self.turma)

    @property
    def turma_curto(self) -> str:
        return TURMA_CURTO.get(self.turma, self.turma)


class ResultadoOficial(db.Model):
    """Um listão oficial de concurso, importado pelo admin.

    Um registro por concurso: a classificação é nacional, então novatos e
    veteranos convivem no mesmo resultado e a turma fica em cada ResultadoLinha.
    Diferente de Simulado (treino, individual), aqui o dado é o resultado real
    divulgado pela banca — já público."""

    __tablename__ = "resultados_oficiais"
    __table_args__ = (
        db.UniqueConstraint("concurso_nome", name="uq_resultados_oficiais_concurso_nome"),
    )

    TURMAS = TURMAS

    id = db.Column(db.Integer, primary_key=True)
    concurso_nome = db.Column(db.String(80), nullable=False)
    fonte = db.Column(db.String(40), nullable=True)
    data = db.Column(db.Date, nullable=True)
    # Nota máxima da escala das notas por matéria (ex.: 10 na AFA).
    escala = db.Column(db.Float, nullable=False, default=10.0)
    # Matérias medidas neste listão, nomes do enum separados por vírgula.
    materias_csv = db.Column(db.String(200), nullable=False, default="")
    # Nome da métrica que ordena o ranking oficial (ex.: "MP").
    metrica = db.Column(db.String(20), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    linhas = db.relationship(
        "ResultadoLinha",
        back_populates="resultado",
        cascade="all, delete-orphan",
    )

    @property
    def materias(self) -> list["Materia"]:
        nomes = {n for n in (self.materias_csv or "").split(",") if n in Materia.__members__}
        return [m for m in Materia if m.name in nomes]

    def set_materias(self, materias) -> None:
        escolhidas = {m.name for m in materias}
        self.materias_csv = ",".join(m.name for m in Materia if m.name in escolhidas)

    # Os recortes abaixo são MÉTODOS (e não properties) porque todos aceitam um
    # filtro de turma opcional. Sem argumento devolvem o concurso inteiro.
    def _por_status(self, status, turma=None) -> list["ResultadoLinha"]:
        return [
            ln
            for ln in self.linhas
            if ln.status == status and (turma is None or ln.turma == turma)
        ]

    def classificados(self, turma=None) -> list["ResultadoLinha"]:
        return sorted(
            self._por_status("classificado", turma),
            key=lambda ln: ln.classificacao or 10**9,
        )

    def sem_aproveitamento(self, turma=None) -> list["ResultadoLinha"]:
        return sorted(
            self._por_status("sem_aproveitamento", turma),
            key=lambda ln: ln.metrica_valor or 0.0,
            reverse=True,
        )

    def nao_encontrados(self, turma=None) -> list["ResultadoLinha"]:
        return sorted(self._por_status("nao_encontrado", turma), key=lambda ln: ln.nome)

    def melhor_classificacao(self, turma=None) -> int | None:
        posicoes = [
            ln.classificacao
            for ln in self.linhas
            if ln.classificacao and (turma is None or ln.turma == turma)
        ]
        return min(posicoes) if posicoes else None

    def total_de(self, turma) -> int:
        return sum(1 for ln in self.linhas if ln.turma == turma)

    @property
    def turmas_presentes(self) -> list[str]:
        """Turmas que de fato têm linhas — a UI não mostra chip de turma vazia."""
        existentes = {ln.turma for ln in self.linhas}
        return [t for t in TURMAS if t in existentes]

    def __repr__(self):
        return f"<ResultadoOficial {self.concurso_nome}>"


class ResultadoLinha(db.Model):
    """Uma pessoa dentro de um resultado oficial."""

    __tablename__ = "resultado_linhas"

    STATUS = ("classificado", "sem_aproveitamento", "nao_encontrado")

    id = db.Column(db.Integer, primary_key=True)
    resultado_id = db.Column(
        db.Integer, db.ForeignKey("resultados_oficiais.id"), nullable=False, index=True
    )
    nome = db.Column(db.String(120), nullable=False)
    # Forma normalizada do nome, usada para casar com User.nome_oficial.
    nome_norm = db.Column(db.String(120), nullable=False, index=True)
    # Recorte do colégio ("novata"/"veterana"). Vem do cabeçalho do JSON, que é
    # sempre de uma turma só; NÃO é derivável da série da pessoa.
    turma = db.Column(db.String(20), nullable=False, index=True)
    # Identidade canônica da pessoa. `nome`/`turma` acima continuam sendo o que a
    # planilha dizia NAQUELE listão — histórico, não estado atual.
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False)
    classificacao = db.Column(db.Integer, nullable=True)
    metrica_valor = db.Column(db.Float, nullable=True)
    # {"MATEMATICA": 6.25, ...} — chaves são nomes do enum Materia.
    notas_json = db.Column(db.Text, nullable=True)
    # Preenchido automaticamente quando o nome casa com o nome_oficial de alguém.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    # Marca edição manual do admin. Um reimport da turma NÃO apaga uma linha
    # editada silenciosamente — ele só avisa no preview (ver B.1 do plano).
    editado_em = db.Column(db.DateTime, nullable=True)
    editado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    resultado = db.relationship("ResultadoOficial", back_populates="linhas")
    user = db.relationship("User", foreign_keys=[user_id])
    editor = db.relationship("User", foreign_keys=[editado_por])

    @property
    def notas(self) -> dict:
        if not self.notas_json:
            return {}
        try:
            return json.loads(self.notas_json)
        except ValueError:
            return {}

    def set_notas(self, notas: dict) -> None:
        self.notas_json = json.dumps(notas) if notas else None

    def nota_de(self, materia: "Materia"):
        return self.notas.get(materia.name)

    @property
    def status_label(self) -> str:
        return {
            "classificado": "Classificado",
            "sem_aproveitamento": "Sem aproveitamento",
            "nao_encontrado": "Não encontrado",
        }.get(self.status, self.status)

    @property
    def turma_label(self) -> str:
        return TURMA_LABEL.get(self.turma, self.turma)

    @property
    def turma_curto(self) -> str:
        return TURMA_CURTO.get(self.turma, self.turma)


class SessaoTreino(db.Model):
    """Uma sessão do cronômetro de questões que o usuário optou por salvar.

    O treino em si roda no navegador; só o resumo (quantas questões, tempo total)
    é gravado aqui, com matéria e observações opcionais."""

    __tablename__ = "sessoes_treino"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    data = db.Column(db.Date, nullable=False, index=True)
    # Matéria é opcional: a pessoa pode treinar sem especificar.
    materia = db.Column(db.Enum(Materia, native_enum=False, length=20), nullable=True)
    questoes = db.Column(db.Integer, nullable=False)
    tempo_total_seg = db.Column(db.Integer, nullable=False)
    # Tempo padrão por questão configurado na sessão (referência), pode ser nulo.
    tempo_padrao_seg = db.Column(db.Integer, nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")

    @property
    def tempo_medio_seg(self) -> float:
        return self.tempo_total_seg / self.questoes if self.questoes else 0.0


class HistoricoImport(db.Model):
    """Um registro por import APLICADO (Fase F.3) — oficial ou de simulado.

    Guarda o JSON cru submetido: se um import saiu errado, o admin ainda tem
    o que foi colado originalmente para comparar/reprocessar manualmente. Não
    existe rollback automático a partir daqui — é só o registro do que
    aconteceu, para auditoria e depuração."""

    __tablename__ = "historico_imports"

    TIPOS = ("oficial", "simulado")

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)
    # Identificação do alvo, só para leitura humana na lista (ex.: "AFA 2027 -
    # novata" ou "ITA S3 - 2026-04-11 - veterana"). Não é FK de propósito: o
    # concurso/prova pode ser excluído depois e o histórico continua legível.
    alvo = db.Column(db.String(160), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    payload_json = db.Column(db.Text, nullable=False)

    criador = db.relationship("User")

    def __repr__(self):
        return f"<HistoricoImport {self.tipo} {self.alvo}>"


class Grupo(db.Model):
    """Um punhado de usuários que compartilham o quanto andaram estudando (Bloco 2).

    Membro é USUÁRIO COM CONTA, nunca Aluno — grupo é sobre hábito de estudo
    (RegistroEstudo/Simulado), que só existe para quem tem login. Apagar o
    grupo apaga só a lista de membros; RegistroEstudo, Simulado e SessaoTreino
    de ninguém são tocados (não há FK de volta deles para cá)."""

    __tablename__ = "grupos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Placar de notas entre os membros. Default False de propósito: comparar
    # nota é mais exposto que comparar volume de questões, então quem já tem
    # grupo não passa a ver placar sem o dono pedir.
    mostrar_ranking = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    dono = db.relationship("User", foreign_keys=[criado_por])
    membros = db.relationship(
        "GrupoMembro", back_populates="grupo", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Grupo {self.nome}>"


class GrupoMembro(db.Model):
    """O vínculo de UM usuário com UM grupo — com convite/aceite no meio.

    Enquanto `status == "convidado"`, nada do usuário aparece nas agregações
    do grupo (ver grupo_evolucao.membros_ativos): dado de hábito de estudo é
    mais sensível que o ranking de simulado, que o colégio já publica. Sair
    (`"saiu"`) tem o mesmo efeito de sumir das agregações, sem apagar o
    histórico de ter sido convidado/participado."""

    __tablename__ = "grupo_membros"
    __table_args__ = (db.UniqueConstraint("grupo_id", "user_id"),)

    STATUS = ("convidado", "ativo", "saiu")

    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(
        db.Integer, db.ForeignKey("grupos.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="convidado")
    convidado_em = db.Column(db.DateTime, nullable=False, default=utcnow)
    respondido_em = db.Column(db.DateTime, nullable=True)

    grupo = db.relationship("Grupo", back_populates="membros")
    user = db.relationship("User")

    def __repr__(self):
        return f"<GrupoMembro grupo={self.grupo_id} user={self.user_id} {self.status}>"
