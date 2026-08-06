from datetime import date

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    FormField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.form import Form
from wtforms.validators import (
    DataRequired,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)
from wtforms.widgets import CheckboxInput, ListWidget

from .models import (
    MATERIAS_DISCRETAS,
    MATERIAS_ESTUDO,
    MATERIAS_PRINCIPAIS,
    MATERIAS_SIMULADO,
    Materia,
)


class MultiCheckboxField(SelectMultipleField):
    """Grupo de checkboxes (não um <select multiple>, ruim no toque)."""

    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class LoginForm(FlaskForm):
    username = StringField(
        "Usuário", validators=[DataRequired("Informe o usuário."), Length(max=32)]
    )
    password = PasswordField(
        "Senha", validators=[DataRequired("Informe a senha."), Length(max=128)]
    )


class RegisterForm(FlaskForm):
    username = StringField(
        "Usuário",
        validators=[
            DataRequired("Informe o usuário."),
            Length(min=3, max=32, message="O usuário deve ter entre 3 e 32 caracteres."),
            Regexp(
                r"^[a-zA-Z0-9_.-]+$",
                message="Use apenas letras, números e _ . - (sem espaços).",
            ),
        ],
    )
    password = PasswordField(
        "Senha",
        validators=[
            DataRequired("Escolha uma senha."),
            Length(min=10, max=128, message="A senha deve ter entre 10 e 128 caracteres."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired("Confirme a senha."),
            EqualTo("password", message="As senhas não coincidem."),
        ],
    )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Senha atual", validators=[DataRequired("Informe a senha atual."), Length(max=128)]
    )
    new_password = PasswordField(
        "Nova senha",
        validators=[
            DataRequired("Informe a nova senha."),
            Length(min=10, max=128, message="A senha deve ter entre 10 e 128 caracteres."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmar nova senha",
        validators=[
            DataRequired("Confirme a nova senha."),
            EqualTo("new_password", message="As senhas não coincidem."),
        ],
    )

    def validate_new_password(self, field):
        if self.current_password.data and field.data == self.current_password.data:
            raise ValidationError("A nova senha deve ser diferente da atual.")


class MateriaScoreForm(Form):
    """Par acertos/total de uma matéria. Sem CSRF próprio: é subform de SimuladoForm."""

    acertos = IntegerField(
        "Acertos", validators=[Optional(), NumberRange(min=0, max=500)]
    )
    total_questoes = IntegerField(
        "Total", validators=[Optional(), NumberRange(min=1, max=500)]
    )

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        acertos, total = self.acertos.data, self.total_questoes.data
        if (acertos is None) != (total is None):
            target = self.acertos if acertos is None else self.total_questoes
            target.errors.append("Preencha acertos e total juntos (ou deixe ambos vazios).")
            return False
        if acertos is not None and acertos > total:
            self.acertos.errors.append("Acertos não pode ser maior que o total.")
            return False
        return True

    @property
    def preenchido(self) -> bool:
        return self.acertos.data is not None and self.total_questoes.data is not None


class SimuladoForm(FlaskForm):
    concurso_id = SelectField(
        "Concurso", coerce=int, validators=[InputRequired("Escolha o concurso.")]
    )
    rotulo = StringField(
        "Nome do simulado",
        validators=[Optional(), Length(max=20, message="Use no máximo 20 caracteres.")],
    )
    data_simulado = DateField(
        "Data do simulado", validators=[DataRequired("Informe a data.")]
    )
    modo_nota = RadioField(
        "Nota geral",
        choices=[
            ("auto", "Automática (média dos % das matérias)"),
            ("manual", "Manual"),
        ],
        default="manual",
    )
    nota_geral = DecimalField(
        "Nota geral",
        places=2,
        validators=[
            Optional(),
            NumberRange(min=0, max=1000, message="Nota deve estar entre 0 e 1000."),
        ],
    )
    posicao_estimada = IntegerField(
        "Posição estimada",
        validators=[Optional(), NumberRange(min=1, max=100000)],
    )
    observacao = TextAreaField(
        "Observações", validators=[Optional(), Length(max=2000)]
    )

    matematica = FormField(MateriaScoreForm, label="Matemática")
    fisica = FormField(MateriaScoreForm, label="Física")
    quimica = FormField(MateriaScoreForm, label="Química")
    portugues = FormField(MateriaScoreForm, label="Português")
    ingles = FormField(MateriaScoreForm, label="Inglês")
    redacao = FormField(MateriaScoreForm, label="Redação")
    geografia = FormField(MateriaScoreForm, label="Geografia")
    historia = FormField(MateriaScoreForm, label="História")

    def validate_data_simulado(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("A data do simulado não pode estar no futuro.")

    def validate_nota_geral(self, field):
        if self.modo_nota.data == "manual" and field.data is None:
            raise ValidationError("Informe a nota geral (ou use a média automática).")

    def validate_modo_nota(self, field):
        if field.data == "auto" and not any(
            sub.preenchido for _, sub in self.materia_fields()
        ):
            raise ValidationError(
                "Para a média automática, preencha ao menos uma matéria."
            )

    def materia_fields(self):
        """Pares (nome_do_enum, subform) das 8 matérias acadêmicas (sem 'Outros')."""
        return [(m.name, getattr(self, m.name.lower())) for m in MATERIAS_SIMULADO]

    def media_automatica(self, permitidas=None):
        """Média simples dos % de acertos das matérias preenchidas (ignora vazias).

        `permitidas`: conjunto de nomes de enum que contam (as do concurso). Se
        None, considera todas as preenchidas. Retorna None se nenhuma conta."""
        percs = []
        for enum_name, sub in self.materia_fields():
            if sub.preenchido and (permitidas is None or enum_name in permitidas):
                percs.append(100.0 * sub.acertos.data / sub.total_questoes.data)
        return round(sum(percs) / len(percs), 2) if percs else None


class EstudoScoreForm(Form):
    """Questões feitas / acertos de uma matéria num dia. Subform (sem CSRF próprio)."""

    questoes = IntegerField("Questões", validators=[Optional(), NumberRange(min=0, max=2000)])
    acertos = IntegerField("Acertos", validators=[Optional(), NumberRange(min=0, max=2000)])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        q, a = self.questoes.data, self.acertos.data
        if (q is None) != (a is None):
            alvo = self.questoes if q is None else self.acertos
            alvo.errors.append("Preencha questões e acertos juntos (ou deixe ambos vazios).")
            return False
        if q is not None and a > q:
            self.acertos.errors.append("Acertos não pode ser maior que as questões.")
            return False
        return True

    @property
    def preenchido(self) -> bool:
        return self.questoes.data is not None and self.acertos.data is not None


class RegistroEstudoForm(FlaskForm):
    data = DateField("Dia", validators=[DataRequired("Informe o dia.")])
    matematica = FormField(EstudoScoreForm, label="Matemática")
    fisica = FormField(EstudoScoreForm, label="Física")
    quimica = FormField(EstudoScoreForm, label="Química")
    portugues = FormField(EstudoScoreForm, label="Português")
    ingles = FormField(EstudoScoreForm, label="Inglês")
    redacao = FormField(EstudoScoreForm, label="Redação")
    outros = FormField(EstudoScoreForm, label="Outros")

    def validate_data(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("O dia não pode estar no futuro.")

    def materia_fields(self):
        return [(m.name, getattr(self, m.name.lower())) for m in MATERIAS_ESTUDO]


class SessaoTreinoForm(FlaskForm):
    """Salvar o resumo de uma sessão de treino de questões (matéria/obs. opcionais)."""

    materia = SelectField("Matéria (opcional)", validators=[Optional()])
    observacao = TextAreaField(
        "Observações", validators=[Optional(), Length(max=2000)]
    )
    # Preenchidos pelo cronômetro (JS) ao finalizar a sessão.
    questoes = IntegerField(
        validators=[DataRequired(), NumberRange(min=1, max=10000)]
    )
    tempo_total_seg = IntegerField(
        validators=[InputRequired(), NumberRange(min=0, max=1000000)]
    )
    tempo_padrao_seg = IntegerField(
        validators=[Optional(), NumberRange(min=0, max=100000)]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.materia.choices = [("", "— não especificar —")] + [
            (m.name, m.value) for m in MATERIAS_ESTUDO
        ]

    def materia_enum(self):
        return Materia[self.materia.data] if self.materia.data else None


class PlanoEstudoForm(FlaskForm):
    """Plano semanal editável: para cada dia, as matérias planejadas."""

    _CHOICES = [(m.name, m.value) for m in MATERIAS_ESTUDO]

    seg = MultiCheckboxField("Segunda", choices=_CHOICES)
    ter = MultiCheckboxField("Terça", choices=_CHOICES)
    qua = MultiCheckboxField("Quarta", choices=_CHOICES)
    qui = MultiCheckboxField("Quinta", choices=_CHOICES)
    sex = MultiCheckboxField("Sexta", choices=_CHOICES)
    sab = MultiCheckboxField("Sábado", choices=_CHOICES)
    dom = MultiCheckboxField("Domingo", choices=_CHOICES)

    def dia_fields(self):
        """Pares (indice_weekday, campo) na ordem Seg..Dom."""
        return list(enumerate([self.seg, self.ter, self.qua, self.qui, self.sex, self.sab, self.dom]))


class ImportOficialForm(FlaskForm):
    """Colagem do JSON de um listão oficial (só admin)."""

    payload = TextAreaField(
        "JSON do resultado",
        validators=[DataRequired("Cole o JSON gerado a partir do listão.")],
    )


class ImportSimuladoTurmaForm(FlaskForm):
    """Colagem do JSON do ranking de um simulado da turma (só admin)."""

    payload = TextAreaField(
        "JSON do ranking",
        validators=[DataRequired("Cole o JSON gerado a partir do ranking.")],
    )
    # Muitas planilhas não trazem data no título; o extrator devolve null e o
    # admin informa aqui. A data faz parte da chave da prova, então é obrigatória
    # em algum dos dois lugares.
    data = DateField(
        "Data da prova (se o JSON vier sem)", validators=[Optional()]
    )


class AlunoForm(FlaskForm):
    """Dados canônicos do aluno (estado atual, não o histórico das provas)."""

    nome = StringField(
        "Nome canônico",
        validators=[DataRequired("Informe o nome."), Length(min=2, max=120)],
    )
    turma = SelectField(
        "Turma",
        validators=[Optional()],
        choices=[("", "— sem turma —"), ("novata", "Novata"), ("veterana", "Veterana")],
    )
    serie = StringField("Série", validators=[Optional(), Length(max=20)])
    ativo = BooleanField("Ativo", default=True)


class NomeOficialForm(FlaskForm):
    """Nome com que a pessoa aparece nos listões — liga o perfil aos resultados."""

    nome_oficial = StringField(
        "Seu nome nos listões",
        validators=[Optional(), Length(max=120)],
    )


class MateriasPerfilForm(FlaskForm):
    """Matérias que o usuário quer acompanhar de perto (default do filtro do
    ranking, Fase D). Usa MATERIAS_SIMULADO — as 8 acadêmicas, sem "Outros"."""

    materias = MultiCheckboxField(
        "Matérias que você quer acompanhar",
        choices=[(m.name, m.value) for m in MATERIAS_SIMULADO],
        validators=[Optional()],
    )


class ConcursoForm(FlaskForm):
    banca = StringField(
        "Banca / concurso",
        validators=[
            DataRequired("Informe a banca (ex.: ITA 2027)."),
            Length(min=2, max=60, message="Use entre 2 e 60 caracteres."),
        ],
    )
    etapa = StringField(
        "Fase / dia",
        validators=[Optional(), Length(max=60)],
    )
    data_prova = DateField("Primeiro dia de prova", validators=[DataRequired("Informe a data da prova.")])
    data_fim = DateField("Último dia (se durar vários dias)", validators=[Optional()])

    def validate_data_fim(self, field):
        if field.data and self.data_prova.data and field.data < self.data_prova.data:
            raise ValidationError("O último dia não pode ser antes do primeiro.")

    def nome_composto(self) -> str:
        from .models import Concurso

        return Concurso.compor_nome(self.banca.data, self.etapa.data)

    def validate_etapa(self, field):
        if len(self.nome_composto()) > 80:
            raise ValidationError("Banca + fase muito longas (máx. 80 caracteres somadas).")
    materias = MultiCheckboxField(
        "Matérias que caem neste concurso",
        choices=[(m.name, m.value) for m in MATERIAS_PRINCIPAIS],
    )
    materias_extras = MultiCheckboxField(
        "Matérias específicas",
        choices=[(m.name, m.value) for m in MATERIAS_DISCRETAS],
    )

    def selected_materias(self) -> list:
        """União das matérias marcadas (principais + discretas), como Materia."""
        nomes = set(self.materias.data or []) | set(self.materias_extras.data or [])
        return [m for m in Materia if m.name in nomes]

    def validate_materias(self, field):
        if not self.selected_materias():
            raise ValidationError("Selecione pelo menos uma matéria.")

    def load_materias(self, materias) -> None:
        """Popula os dois campos a partir de uma lista de Materia (para edição)."""
        nomes = {m.name for m in materias}
        self.materias.data = [m.name for m in MATERIAS_PRINCIPAIS if m.name in nomes]
        self.materias_extras.data = [m.name for m in MATERIAS_DISCRETAS if m.name in nomes]
