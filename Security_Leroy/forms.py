from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField, IntegerField, SelectField, TextAreaField, DateField
)
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from flask_wtf.file import FileField, FileAllowed
from .models import Usuarios  # necessário só se usar a validação de e-mail
from flask_login import current_user




class FormCriarConta(FlaskForm):
    username = StringField("Digite o Usuario", validators=[DataRequired()])
    email = StringField("Digite o E-mail", validators=[DataRequired(), Email()])
    senha = PasswordField("Digite a senha ", validators=[DataRequired(), Length(min=6, max=20)])
    confirmacao = PasswordField("Confirme a senha", validators=[DataRequired(), EqualTo('senha')])
    botao_submit_criarconta = SubmitField("Criar Conta")

    # Validação opcional (descomentando, mantenha o import de Usuarios acima)
    # def validate_email(self, email):
    #     usuario = Usuarios.query.filter_by(email=email.data).first()
    #     if usuario:
    #         raise ValidationError("Email já cadastrado! Cadastre outro email.")

class FormLogin(FlaskForm):
    email = StringField("Digite o E-mail", validators=[DataRequired(), Email()])
    senha = PasswordField("Digite a senha ", validators=[DataRequired(), Length(min=6, max=20)])
    lembrar_dados = BooleanField("Relembre seus dados")
    botao_submit_login = SubmitField("Fazer Login")

class FormAnc(FlaskForm):
    id = IntegerField('ID', validators=[Optional()])

    nome_solicitante = StringField('Nome do Solicitante', validators=[DataRequired(), Length(max=120)])

    data = DateField('Data', format='%Y-%m-%d', validators=[DataRequired()])

    data_ocorrencia = DateField('Data da Ocorrência', format='%Y-%m-%d', validators=[Optional()])

    descricao = TextAreaField('Descrição', validators=[DataRequired(), Length(max=1000)])

    envolvido_pacote = StringField('Envolvido ou Nº do Pacote', validators=[Optional(), Length(max=120)])

    responsavel = StringField('Responsável', validators=[Optional(), Length(max=120)])

    turno = SelectField(
        'Turno',
        choices=[('1', '1° Turno'), ('2', '2° Turno'), ('3', '3° Turno'), ('4', '4º Turno')],
        validators=[Optional()]
    )

    gravidade = SelectField(
        'Gravidade',
        choices=[('baixa', 'Baixa'), ('media', 'Média'), ('alta', 'Alta')],
        validators=[Optional()]
    )

    local = StringField('Local', validators=[Optional(), Length(max=120)])

    imagem = FileField('Imagem', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Apenas imagens.')])

    botao_submit = SubmitField('Enviar')

class FormEditarPerfil(FlaskForm):
    username = StringField("Digite o Usuario", validators=[DataRequired()])
    email = StringField("Digite o E-mail", validators=[DataRequired(), Email()])
    foto_perfil = FileField('Atualizaro Foto de Perfil', validators=[FileAllowed(['jpg','png'])])
    botao_submit_editarperfil = SubmitField("Confirmar edição")

    # Validação opcional (descomentando, mantenha o import de Usuarios acima)
    def validate_email(self, email):
        if current_user.email != email.data:
            usuario = Usuarios.query.filter_by(email=email.data).first()
            if usuario:
                raise ValidationError("Ja existe um usuario com esse e-mail, Cadastre outro e-mail")


class FormCriarPost(FlaskForm):
    titulo = StringField("Titulo do Post", validators=[DataRequired(), Length(5, 140)])
    corpo = TextAreaField('Escreva seu post Aqui', validators=[DataRequired()])
    botao_submit = SubmitField("Salvar")

class FormArmarioRotativo(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    empresa = StringField("Empresa", validators=[Length(max=120)])
    cpf = StringField("CPF", validators=[DataRequired(), Length(max=14)])
    armario = StringField("Armário", validators=[DataRequired(), Length(max=32)])
    chave = StringField("Chave", validators=[Length(max=32)])
    status = SelectField(
        "Status",
        choices=[("Ocupado", "Ocupado"),
                 ("Livre", "Livre"),
                 ("Manutenção", "Manutenção")],
        default="Ocupado"
    )
    turno = SelectField(
        "Turno",
        choices=[
            ("", "Inserir o Turno"),
            ("1", "1º Turno"),
            ("2", "2º Turno"),
            ("3", "3º Turno"),
            ("4", "4º Turno"),
        ]
    )
    botao_submit = SubmitField("Salvar e gerar QR")


class FormSolicitacaoImagem(FlaskForm):
    nome = StringField(
        "Nome",
        validators=[
            DataRequired(message="Informe o nome."),
            Length(max=120, message="Máximo de 120 caracteres.")
        ]
    )

    descricao_ocorrencia = StringField(
        "Descrição da Ocorrência",
        validators=[
            DataRequired(message="Descreva a ocorrência."),
            Length(max=255, message="Máximo de 255 caracteres.")
        ]
    )

    data_hora_info = StringField(
        "Data / Hora",
        validators=[
            DataRequired(message="Informe data e horário aproximados."),
            Length(max=80, message="Máximo de 80 caracteres.")
        ]
    )

    envolvidos = StringField(
        "Envolvidos",
        validators=[
            Length(max=255, message="Máximo de 255 caracteres.")
        ]
    )

    turno = SelectField(
        "Turno",
        choices=[
            ("", "Inserir o Turno"),
            ("1", "1º Turno"),
            ("2", "2º Turno"),
            ("3", "3º Turno"),
            ("4", "4º Turno"),
        ],
        validators=[DataRequired(message="Selecione o turno.")]
    )

    coordenador = StringField(
        "Coordenador",
        validators=[
            Length(max=120, message="Máximo de 120 caracteres.")
        ]
    )

    botao_submit = SubmitField("Enviar")

    class FormSolicitacaoImagem(FlaskForm):
        # Nome
        nome = StringField(
            "Nome",
            validators=[
                DataRequired(message="Informe o nome."),
                Length(max=100, message="O nome deve ter no máximo 100 caracteres.")
            ],
        )

        # Descrição da ocorrência
        descricao_ocorrencia = TextAreaField(
            "Descrição da ocorrência",
            validators=[
                DataRequired(message="Descreva a ocorrência."),
                Length(max=2000, message="A descrição deve ter no máximo 2000 caracteres.")
            ],
        )

        # Data / Hora da informação (deixando como texto livre para seguir o placeholder)
        data_hora_info = StringField(
            "Data / Horário aproximado",
            validators=[
                DataRequired(message="Informe a data e horário aproximado.")
            ],
        )

        # Envolvidos
        envolvidos = TextAreaField(
            "Envolvidos",
            validators=[
                Optional(),
                Length(max=1000, message="Este campo aceita no máximo 1000 caracteres.")
            ],
        )

        # Turno
        turno = SelectField(
            "Turno",
            choices=[
                ("", "Selecione..."),
                ("Manhã", "Manhã"),
                ("Tarde", "Tarde"),
                ("Noite", "Noite"),
                ("Madrugada", "Madrugada"),
            ],
            validators=[DataRequired(message="Selecione o turno.")],
        )

        # Coordenador
        coordenador = StringField(
            "Coordenador",
            validators=[
                Optional(),
                Length(max=100, message="O nome do coordenador deve ter no máximo 100 caracteres.")
            ],
        )

        # Botão de envio
        submit = SubmitField("Enviar")


class MuralForm(FlaskForm):
    titulo = StringField(
        "Título",
        validators=[Optional(), Length(max=200)]
    )

    corpo = TextAreaField(
        "Mensagem",
        validators=[Optional(), Length(max=5000)]
    )

    imagem = FileField(
        "Imagem do mural",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "gif"], "Apenas imagens (JPG, PNG, GIF).")
        ]
    )

    submit = SubmitField("Publicar")