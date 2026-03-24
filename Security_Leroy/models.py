# Security_Leroy/models.py
from datetime import datetime, date
from enum import Enum

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SAEnum

from Security_Leroy import database as db, login_manager


# ---------- Login loader ----------
@login_manager.user_loader
def load_usuario(id_usuario):
    return Usuarios.query.get(int(id_usuario))


# ---------- Usuários e Post ----------
class Usuarios(db.Model, UserMixin):
    __tablename__ = "usuarios"

    solicitacoes_imagem = relationship(
        "SolicitacaoImagem",
        backref="operador",
        lazy=True,
        cascade="all, delete-orphan",
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    senha = db.Column(db.String(255), nullable=False)
    # usado nos templates: 'foto_perfil'
    foto_perfil = db.Column(db.String(255), nullable=False, default="default.png")
    cursos = db.Column(db.String(255), nullable=False, default="Não Informado")

    # 1:N com Post
    posts = relationship(
        "Post",
        backref=db.backref("autor", lazy=True),
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Usuarios {self.id} {self.email}>"


class Post(db.Model):
    __tablename__ = "post"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(255), nullable=False)
    corpo = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # chave estrangeira para Usuarios
    autor_id = db.Column(
        db.Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self):
        return f"<Post {self.id} por usuario {self.autor_id}>"


# ---------- Enums ----------
class GravidadeEnum(Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"


class LocalEnum(Enum):
    inbound = "inbound"
    expedicao = "expedicao"
    esteiras = "esteiras"
    label_b = "label_b"
    sorter1 = "sorter1"
    sorter2 = "sorter2"
    sorter3 = "sorter3"
    sorter4 = "sorter4"
    sorter5 = "sorter5"
    sorter6 = "sorter6"
    sorter7 = "sorter7"
    sorter8 = "sorter8"
    sorter9 = "sorter9"
    sorter10 = "sorter10"


class NaturezaEnum(Enum):
    desvio_conduta = "desvio_conduta"
    embalagem_vazia = "embalagem_vazia"
    colisao = "colisao"
    desinteligencia = "desinteligencia"
    assedio_moral = "assedio_moral"
    assedio_sexual = "assedio_sexual"
    danos_patrimonio = "danos_patrimonio"
    furto = "furto"
    roubo = "roubo"
    comercio_ilegal = "comercio_ilegal"
    porte_ilicitas = "porte_ilicitas"


# ---------- Tabela ANC ----------
class ANC(db.Model):
    __tablename__ = "anc"

    id = db.Column(db.Integer, primary_key=True)
    nome_solicitante = db.Column(db.String(120), nullable=False)
    data_atual = db.Column(db.Date, nullable=False)
    data_ocorrencia = db.Column(db.Date, nullable=True)
    descricao = db.Column(db.Text, nullable=False)
    envolvido_gc = db.Column(db.String(120), nullable=True)
    responsavel = db.Column(db.String(120), nullable=True)

    turno = db.Column(db.Integer, nullable=True)  # 1..4
    gravidade = db.Column(SAEnum(GravidadeEnum, name="gravidade_enum"), nullable=True)
    local = db.Column(SAEnum(LocalEnum, name="local_enum"), nullable=True)
    natureza = db.Column(SAEnum(NaturezaEnum, name="natureza_enum"), nullable=True)

    status = db.Column(db.String(255), nullable=False, default="Pendente")
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    assinatura_filename = db.Column(db.String(255), nullable=True)  # ex: uploads/anc/assinaturas/1_20260101.png
    assinatura_created_at = db.Column(db.DateTime, server_default=func.now(), nullable=True)

    fotos = relationship(
        "ANCFoto",
        back_populates="anc",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    __table_args__ = (
        CheckConstraint("turno IS NULL OR (turno BETWEEN 1 AND 4)", name="ck_anc_turno_1_4"),
    )

    def __repr__(self):
        return f"<ANC id={self.id} nome={self.nome_solicitante!r} data={self.data_atual}>"


class ANCFoto(db.Model):
    __tablename__ = "anc_foto"

    id = db.Column(db.Integer, primary_key=True)
    anc_id = db.Column(
        db.Integer,
        ForeignKey("anc.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename = db.Column(db.String(255), nullable=False)  # ex: uploads/anc/abc.jpg
    mime_type = db.Column(db.String(50), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=True)
    storage_path = db.Column(db.String(255), nullable=True)

    uploaded_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    anc = relationship("ANC", back_populates="fotos")

    def __repr__(self):
        return f"<ANCFoto id={self.id} anc_id={self.anc_id} file={self.filename!r}>"


# ---------- Ocorrências ----------
class Ocorrencia(db.Model):
    __tablename__ = "ocorrencia"

    id = db.Column(db.Integer, primary_key=True)

    nome_solicitante = db.Column(db.String(120), nullable=False)
    data_ocorrencia = db.Column(db.Date, nullable=True)
    descricao = db.Column(db.Text, nullable=False)
    envolvido_gc = db.Column(db.String(120), nullable=True)

    turno = db.Column(db.SmallInteger, nullable=True)

    foto_filename = db.Column(db.String(255), nullable=True)
    foto_mime = db.Column(db.String(50), nullable=True)
    foto_size_bytes = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(
        db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("turno IS NULL OR (turno BETWEEN 1 AND 4)", name="ck_ocorrencia_turno_1_4"),
    )

    def __repr__(self):
        return f"<Ocorrencia id={self.id} nome={self.nome_solicitante!r} data={self.data_ocorrencia}>"


# ---------- Armários ----------
class ArmarioRegistro(db.Model):
    __tablename__ = "armario_registro"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), nullable=False, index=True)
    armario = db.Column(db.String(32), nullable=False, index=True)
    chave = db.Column(db.String(32), nullable=True)
    turno = db.Column(db.SmallInteger, nullable=True)
    coordenador = db.Column(db.String(120), nullable=True)

    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("turno IS NULL OR (turno BETWEEN 1 AND 4)", name="ck_armario_turno_1_4"),
        Index("ix_armario_registro_nome", "nome"),
    )

    def __repr__(self):
        return f"<ArmarioRegistro id={self.id} nome={self.nome!r} cpf={self.cpf!r}>"


# ---------- Solicitação de Imagem ----------

class SolicitacaoImagem(db.Model):
    __tablename__ = "solicitacao_imagem"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao_ocorrencia = db.Column(db.Text, nullable=False)
    data_hora_info = db.Column(db.String(50), nullable=False)
    envolvidos = db.Column(db.Text)
    turno = db.Column(db.String(20))
    coordenador = db.Column(db.String(100))
    operador_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    # NOVO CAMPO
    status = db.Column(db.String(20), nullable=False, default="Pendente")



# ---------- Achados e Perdidos ----------
class AchadoPerdido(db.Model):
    __tablename__ = "achado_perdido"

    id = db.Column(db.Integer, primary_key=True)
    identificacao = db.Column(db.String(120), nullable=True)
    descricao_objeto = db.Column(db.String(255), nullable=False)
    data_hora_info = db.Column(db.String(80), nullable=True)
    local_encontrado = db.Column(db.String(120), nullable=True)
    turno = db.Column(db.SmallInteger, nullable=True)
    foto_filename = db.Column(db.String(255), nullable=True)
    foto_mime = db.Column(db.String(50), nullable=True)
    foto_size_bytes = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)


    __table_args__ = (
        CheckConstraint("turno IS NULL OR (turno BETWEEN 1 AND 4)", name="ck_achado_turno_1_4"),
    )
    status_destino = db.Column(db.String(20), nullable=False, default="Pendente")

    nome_retirante = db.Column(db.String(120), nullable=True)
    def __repr__(self):
        return f"<AchadoPerdido id={self.id} desc={self.descricao_objeto!r}>"


class ArmarioRotativo(db.Model):
    __tablename__ = "armario_rotativo"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    empresa = db.Column(db.String(120), nullable=True)
    cpf = db.Column(db.String(14), nullable=False)
    armario = db.Column(db.String(50), nullable=False)
    chave = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="Ocupado")
    turno = db.Column(db.SmallInteger, nullable=True)
    qr_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class PessoaAtivo(db.Model):
    __tablename__ = "pessoas_ativos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(20), unique=True, nullable=False)
    data = db.Column(db.String(20))  # pode ser Date se quiser
    cargo = db.Column(db.String(80))
    empresa = db.Column(db.String(80))
    turno = db.Column(db.String(40))
    foto_dono = db.Column(db.String(255))  # caminho da foto no /static

    # relação 1:n com Ativos
    ativos = db.relationship("Ativo", backref="pessoa", lazy=True)


class Ativo(db.Model):
    __tablename__ = "ativos"

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey("pessoas_ativos.id"), nullable=False)

    tipo = db.Column(db.String(60))
    imei_ou_numero = db.Column(db.String(100), index=True)
    data = db.Column(db.String(20))
    status = db.Column(db.String(30), default="Em uso")
    observacoes = db.Column(db.Text)

    # relação 1:n com fotos
    fotos = db.relationship(
        "FotoAtivo",
        backref="ativo",
        lazy=True,
        cascade="all, delete-orphan"
    )

class FotoAtivo(db.Model):
    __tablename__ = "fotos_ativos"

    id = db.Column(db.Integer, primary_key=True)
    ativo_id = db.Column(db.Integer, db.ForeignKey("ativos.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # ex: 'uploads/ativos/arquivo.jpg'

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
# ---------- Controle de Acessos ----------
class AcessoRegistro(db.Model):
    __tablename__ = "acessos_registros"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    data_registro = db.Column(db.Date, nullable=True)

    empresa = db.Column(db.String(60), nullable=True)
    cpf = db.Column(db.String(14), nullable=True)

    responsavel = db.Column(db.String(120), nullable=True)
    turno = db.Column(db.Integer, nullable=True)  # 1..4

    # Foto única (caminho relativo a /static)
    foto_filename = db.Column(db.String(260), nullable=True)
    foto_mime = db.Column(db.String(80), nullable=True)
    foto_size_bytes = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def data_registro_fmt(self) -> str:
        if isinstance(self.data_registro, date):
            return self.data_registro.strftime("%d/%m/%Y")
        return "—"



class PassagemTurno(db.Model):
    __tablename__ = "passagem_turno"

    id            = db.Column(db.Integer, primary_key=True)
    nome          = db.Column(db.String(120), nullable=False)
    auditorias    = db.Column(db.String(120), nullable=True)
    data_hora     = db.Column(db.String(120), nullable=True)
    lancamento    = db.Column(db.String(120), nullable=True)
    turno         = db.Column(db.Integer, nullable=True)    # 1..4
    operador      = db.Column(db.String(120), nullable=True)
    monitoramento = db.Column(db.Text, nullable=True)
    liberacao     = db.Column(db.Text, nullable=True)

    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<PassagemTurno id={self.id} nome={self.nome!r}>"

class Mural(db.Model):
    __tablename__ = "mural"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=True)
    corpo = db.Column(db.Text, nullable=True)

    # Nome do arquivo da imagem salva em static/mural/
    imagem_filename = db.Column(db.String(255), nullable=True)

    data_criacao = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    # Relacionamento com usuário
    autor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    autor = db.relationship("Usuarios", backref="mural_posts")

    def __repr__(self):
        return f"<Mural id={self.id} titulo={self.titulo!r}>"