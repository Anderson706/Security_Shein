# router.py
import os
from PIL import ImageOps

from datetime import date, datetime

from flask import (
    current_app,
    abort,
    session,
    jsonify,
)
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
import secrets
from PIL import Image
import qrcode
from sqlalchemy import func  # or_ está aqui caso você vá usar em buscas
from Security_Leroy import app, database as db, bcrypt
from Security_Leroy.forms import (
    FormLogin,
    FormCriarConta,
    FormEditarPerfil,
    FormCriarPost,
    FormArmarioRotativo,
    FormSolicitacaoImagem,
    MuralForm,
)
from Security_Leroy.models import (
    Usuarios,
    ANC,
    ANCFoto,
    GravidadeEnum,
    LocalEnum,
    NaturezaEnum,
    Ocorrencia,
    ArmarioRegistro,
    Post,
    AchadoPerdido,
    ArmarioRotativo,
    PessoaAtivo,
    Ativo,
    FotoAtivo,
    PassagemTurno,
    SolicitacaoImagem,
    Mural,
)



from flask_wtf.csrf import CSRFProtect, generate_csrf

# Diretórios para salvar fotos do dono e dos ativos
FOTOS_DONO_DIR = os.path.join(app.root_path, "static", "foto_dono")
FOTOS_ATIVOS_DIR = os.path.join(app.root_path, "static", "uploads", "ativos")

os.makedirs(FOTOS_DONO_DIR, exist_ok=True)
os.makedirs(FOTOS_ATIVOS_DIR, exist_ok=True)


csrf = CSRFProtect(app)

@app.context_processor
def inject_csrf_token():
    # disponibiliza a função csrf_token() no Jinja
    return dict(csrf_token=generate_csrf)

@app.context_processor
def ui_helpers():
    def turno_label(v):
        mapa = {1: "1° Turno", 2: "2° Turno", 3: "3° Turno", 4: "4° Turno"}
        try:
            return mapa.get(int(v), "—")
        except Exception:
            return "—"

    def foto_static_url(relpath):
        """
        Aceita caminho relativo a /static (ex.: 'uploads/acessos/123.jpg')
        ou já contendo 'static/...'; devolve URL segura para <img>.
        """
        if not relpath:
            return None
        p = relpath.lstrip("/").replace("\\", "/")
        if p.startswith("static/"):
            p = p[7:]
        return url_for("static", filename=p)

    return dict(turno_label=turno_label, foto_static_url=foto_static_url)




# ------------------------------------------------------
# Configs / Constantes
# ------------------------------------------------------
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
UPLOAD_SUBDIR_ANC = os.path.join("static", "uploads", "anc")


# ------------------------------------------------------
# Funções utilitárias
# ------------------------------------------------------
def _allowed_file(filename: str) -> bool:
    """Verifica se a extensão do arquivo é permitida."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _normaliza_cpf(cpf_raw: str) -> str:
    return "".join(ch for ch in (cpf_raw or "") if ch.isdigit())

def _turno_from_label(label: str):
    """
    Converte '1° Turno', '2° Turno', '3° Turno', '4º Turno' -> 1..4
    Aceita também '1', '2', etc.
    """
    if not label:
        return None
    s = label.strip().lower()
    # tentativas diretas
    for n in (1, 2, 3, 4):
        if s.startswith(str(n)):
            return n
    # variantes com símbolo
    mapa = {
        "1° turno": 1, "1º turno": 1,
        "2° turno": 2, "2º turno": 2,
        "3° turno": 3, "3º turno": 3,
        "4° turno": 4, "4º turno": 4,
    }
    return mapa.get(s, None)

def _save_acesso_foto(file_storage):
    """
    Salva a foto em /static/uploads/acessos, retornando
    (foto_rel, mime, size) – caminho relativo a /static.
    """
    if not file_storage or not file_storage.filename:
        return None, None, None
    if not _allowed_file(file_storage.filename):
        flash("Formato de imagem não permitido.", "warning")
        return None, None, None

    upload_root = os.path.join(current_app.root_path, "static", "uploads", "acessos")
    os.makedirs(upload_root, exist_ok=True)

    safe_name = secure_filename(file_storage.filename)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    final_name = f"{ts}_{safe_name}"
    abs_path = os.path.join(upload_root, final_name)

    file_storage.save(abs_path)

    foto_rel = os.path.relpath(
        abs_path, start=os.path.join(current_app.root_path, "static")
    ).replace("\\", "/")
    mime = getattr(file_storage, "mimetype", None)
    try:
        size_b = os.path.getsize(abs_path)
    except OSError:
        size_b = None
    return foto_rel, mime, size_b


def _normaliza_cpf(cpf_raw: str) -> str:
    """Mantém apenas dígitos do CPF."""
    return "".join(ch for ch in (cpf_raw or "") if ch.isdigit())


def _valida_turno(turno_str: str):
    """Converte turno para int 1..4 ou None."""
    if not turno_str:
        return None, None
    try:
        t = int(turno_str)
        if t not in (1, 2, 3, 4):
            return None, "Turno deve ser 1, 2, 3 ou 4."
        return t, None
    except ValueError:
        return None, "Turno inválido."


def _post_owner_id(post_obj):
    """
    Retorna o ID do usuário dono do post.
    - Tenta via relationship: post.autor.id
    - Tenta via FKs comuns: user_id ou autor_id
    """
    autor = getattr(post_obj, "autor", None)
    if autor and getattr(autor, "id", None) is not None:
        return autor.id
    for attr in ("user_id", "autor_id"):
        if hasattr(post_obj, attr):
            return getattr(post_obj, attr)
    return None


# ------------------------------------------------------
# Função: salvar OCORRÊNCIA
# ------------------------------------------------------
def save_ocorrencia_from_request():
    try:
        nome_solicitante = (request.form.get("nome_solicitante") or "").strip()
        data_str = (request.form.get("data_ocorrencia") or "").strip()
        descricao = (request.form.get("descricao") or "").strip()
        envolvido_gc = (request.form.get("envolvido_gc") or "").strip()
        turno_str = (request.form.get("turno") or "").strip()

        if not nome_solicitante:
            flash("Informe o Nome do Solicitante.", "warning")
            return redirect(request.url)
        if not descricao:
            flash("Informe a Descrição.", "warning")
            return redirect(request.url)

        data_ocorrencia = None
        if data_str:
            try:
                data_ocorrencia = datetime.strptime(data_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Data da Ocorrência inválida (use YYYY-MM-DD).", "warning")
                return redirect(request.url)

        turno = None
        if turno_str:
            try:
                turno = int(turno_str)
                if turno not in (1, 2, 3, 4):
                    flash("Turno deve ser 1, 2, 3 ou 4.", "warning")
                    return redirect(request.url)
            except ValueError:
                flash("Turno inválido.", "warning")
                return redirect(request.url)

        # foto opcional
        foto_file = request.files.get("foto")
        foto_filename = None
        foto_mime = None
        foto_size = None

        if foto_file and foto_file.filename:
            if not _allowed_file(foto_file.filename):
                flash("Formato de imagem não permitido.", "warning")
                return redirect(request.url)

            upload_folder = current_app.config.get(
                "UPLOAD_OCORRENCIAS",
                os.path.join(current_app.root_path, "static", "uploads", "ocorrencias"),
            )
            os.makedirs(upload_folder, exist_ok=True)

            safe_name = secure_filename(foto_file.filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_name = f"{ts}_{safe_name}"
            abs_dest = os.path.join(upload_folder, safe_name)
            foto_file.save(abs_dest)

            foto_filename = (
                os.path.relpath(abs_dest, start=current_app.root_path)
                .replace("\\", "/")
            )
            foto_mime = foto_file.mimetype
            try:
                foto_size = os.path.getsize(abs_dest)
            except OSError:
                foto_size = None

        ocorr = Ocorrencia(
            nome_solicitante=nome_solicitante,
            data_ocorrencia=data_ocorrencia,
            descricao=descricao,
            envolvido_gc=envolvido_gc,
            turno=turno,
            foto_filename=foto_filename,
            foto_mime=foto_mime,
            foto_size_bytes=foto_size,
        )

        db.session.add(ocorr)
        db.session.commit()
        flash("Ocorrência registrada com sucesso!", "success")
        return redirect(url_for("ocorrencias"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao salvar Ocorrencia")
        flash(f"Erro ao salvar: {e}", "danger")
        return redirect(request.url)


# ------------------------------------------------------
# Rotas principais
# ------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/contatos")
@login_required
def contatos():
    return render_template("contato.html")


@app.route("/auditorias")
@login_required
def auditorias():
    return render_template("passagem_turno.html")


@app.route("/investigacoes", methods=["GET", "POST"])
@login_required
def investigacoes():
    form = FormSolicitacaoImagem()

    if form.validate_on_submit():
        solicitacao = SolicitacaoImagem(
            nome=(form.nome.data or "").strip(),
            descricao_ocorrencia=(form.descricao_ocorrencia.data or "").strip(),
            data_hora_info=(form.data_hora_info.data or "").strip(),
            envolvidos=form.envolvidos.data.strip() if form.envolvidos.data else None,
            turno=form.turno.data or None,
            coordenador=form.coordenador.data.strip() if form.coordenador.data else None,
            operador_id=current_user.id,
        )
        db.session.add(solicitacao)
        db.session.commit()

        flash("Solicitação de imagem registrada com sucesso!", "success")
        return redirect(url_for("post_investigacoes"))

    return render_template("investigacoes.html", form=form)
# ------------------------------------------------------
# ARMÁRIOS
# ------------------------------------------------------
@app.route("/armarios", methods=["GET", "POST"])
@login_required
def armarios():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        cpf_raw = (request.form.get("cpf") or "").strip()
        armario = (request.form.get("armario") or "").strip()
        chave = (request.form.get("chave") or "").strip()
        coordenador = (request.form.get("coordenador") or "").strip()
        turno_str = (request.form.get("turno") or "").strip()

        # validações básicas
        if not nome:
            flash("Informe o Nome.", "warning")
            return redirect(request.url)
        if not cpf_raw:
            flash("Informe o CPF.", "warning")
            return redirect(request.url)
        if not armario:
            flash("Informe o número/identificação do Armário.", "warning")
            return redirect(request.url)

        cpf_normalizado = _normaliza_cpf(cpf_raw)

        turno_int, turno_err = _valida_turno(turno_str)
        if turno_err:
            flash(turno_err, "warning")
            return redirect(request.url)

        # --- IMPEDIR CPF IGUAL AO NÚMERO DO ARMÁRIO ---
        armario_digitos = "".join(ch for ch in armario if ch.isdigit())
        if cpf_normalizado and armario_digitos and cpf_normalizado == armario_digitos:
            flash("O número do armário não pode ser igual ao CPF.", "warning")
            return redirect(request.url)

        # --- IMPEDIR ARMÁRIO DUPLICADO / COMPARTILHADO ---
        # procura qualquer registro já usando esse armário
        existente = ArmarioRegistro.query.filter_by(armario=armario).first()
        if existente:
            if existente.cpf == cpf_normalizado:
                # mesmo CPF + mesmo armário => duplicado
                flash(
                    "Já existe um registro para este CPF utilizando este armário.",
                    "warning",
                )
            else:
                # armário em uso por outro CPF
                flash(
                    f"Este armário já está em uso por outro colaborador (CPF {existente.cpf}).",
                    "warning",
                )
            return redirect(request.url)

        try:
            reg = ArmarioRegistro(
                nome=nome,
                cpf=cpf_normalizado,
                armario=armario,
                chave=chave or None,
                turno=turno_int,
                coordenador=coordenador or None,
            )
            db.session.add(reg)
            db.session.commit()
            flash("Registro de armário salvo com sucesso!", "success")
            return redirect(url_for("armarios"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Erro ao salvar ArmarioRegistro")
            flash(f"Erro ao salvar: {e}", "danger")
            return redirect(request.url)

    # GET: só renderiza o formulário
    return render_template("armarios.html")


@app.route("/armarios/buscar", methods=["GET"])
@login_required
def buscar_armarios():
    nome_q = (request.args.get("nome") or "").strip()
    cpf_q_raw = (request.args.get("cpf") or "").strip()
    arm_q = (request.args.get("armario") or "").strip()

    cpf_q = _normaliza_cpf(cpf_q_raw)

    query = ArmarioRegistro.query
    if nome_q:
        query = query.filter(ArmarioRegistro.nome.ilike(f"%{nome_q}%"))
    if cpf_q:
        query = query.filter(ArmarioRegistro.cpf == cpf_q)
    if arm_q:
        query = query.filter(ArmarioRegistro.armario.ilike(f"%{arm_q}%"))

    resultados = query.order_by(ArmarioRegistro.created_at.desc()).all()

    if not resultados:
        flash("Nenhum registro encontrado para os filtros informados.", "info")

    return render_template(
        "armarios.html",
        resultados=resultados,
        filtro_nome=nome_q,
        filtro_cpf=cpf_q_raw,
        filtro_armario=arm_q,
    )


# ------------------------------------------------------
# OCORRÊNCIAS
# ------------------------------------------------------
@app.route("/ocorrencias", methods=["GET", "POST"])
@login_required
def ocorrencias():
    if request.method == "POST":
        return save_ocorrencia_from_request()
    return render_template("ocorrencias.html", hoje=date.today().isoformat())


# ------------------------------------------------------
# LOGIN / CONTA
# ------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login_conta():
    form_login = FormLogin()
    form_criarconta = FormCriarConta()

    # LOGIN
    if form_login.validate_on_submit() and form_login.botao_submit_login.data:
        email_norm = (form_login.email.data or "").strip().lower()
        senha_plana = (form_login.senha.data or "").strip()

        # só e-mails da DHL
        if not email_norm.endswith("@dhl.com"):
            flash("Apenas e-mails @dhl.com podem acessar.", "danger")
            return redirect(url_for("login_conta"))

        usuario = Usuarios.query.filter_by(email=email_norm).first()
        if usuario and bcrypt.check_password_hash(usuario.senha, senha_plana):
            login_user(usuario, remember=form_login.lembrar_dados.data)
            flash("Login realizado com sucesso!!", "success")
            par_next = request.args.get("next")
            return redirect(par_next or url_for("home"))
        else:
            flash("Falha ao fazer login. Verifique os dados.", "danger")

    # CRIAR CONTA
    if form_criarconta.validate_on_submit() and form_criarconta.botao_submit_criarconta.data:
        email_norm = (form_criarconta.email.data or "").strip().lower()
        username = (form_criarconta.username.data or "").strip()
        senha_plana = (form_criarconta.senha.data or "").strip()

        if not email_norm.endswith("@dhl.com"):
            flash("Use um e-mail @dhl.com para se cadastrar.", "warning")
            return redirect(url_for("login_conta"))

        if Usuarios.query.filter_by(email=email_norm).first():
            flash("E-mail já cadastrado.", "warning")
        else:
            senha_hash = bcrypt.generate_password_hash(senha_plana).decode("utf-8")
            usuario = Usuarios(username=username, email=email_norm, senha=senha_hash)
            db.session.add(usuario)
            try:
                db.session.commit()
                flash("Conta criada com sucesso!", "success")
                return redirect(url_for("home"))
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível criar a conta.", "danger")

    return render_template("login.html", form_login=form_login, form_criarconta=form_criarconta)


# ------------------------------------------------------
# OUTRAS PÁGINAS
# ------------------------------------------------------
@app.route("/usuarios")
def usuarios():
    todos = Usuarios.query.order_by(Usuarios.username.asc()).all()
    return render_template("usuarios.html", usuarios=todos)


@app.route("/anc", methods=["GET", "POST"])
@login_required
def anc():
    if request.method == "POST":
        try:
            nome_solicitante = request.form.get("nome_solicitante") or None
            data_atual_str = request.form.get("data_atual") or None
            data_ocor_str = request.form.get("data_ocorrencia") or None
            descricao = request.form.get("descricao") or None
            envolvido_gc = request.form.get("envolvido_gc") or None
            responsavel = request.form.get("responsavel") or None
            turno_str = request.form.get("turno") or None
            gravidade_str = request.form.get("gravidade") or None
            local_str = request.form.get("local") or None
            natureza_str = request.form.get("natureza") or None

            def parse_data(s):
                if not s:
                    return None
                return datetime.strptime(s, "%Y-%m-%d").date()

            data_atual = parse_data(data_atual_str) or date.today()
            data_ocorrencia = parse_data(data_ocor_str)
            turno = int(turno_str) if (turno_str and turno_str.isdigit()) else None

            gravidade = GravidadeEnum(gravidade_str) if gravidade_str else None
            local = LocalEnum(local_str) if local_str else None
            natureza = NaturezaEnum(natureza_str) if natureza_str else None

            registro = ANC(
                nome_solicitante=nome_solicitante,
                data_atual=data_atual,
                data_ocorrencia=data_ocorrencia,
                descricao=descricao,
                envolvido_gc=envolvido_gc,
                responsavel=responsavel,
                turno=turno,
                gravidade=gravidade,
                local=local,
                natureza=natureza,
            )
            db.session.add(registro)
            db.session.flush()

            files = request.files.getlist("fotos")
            if files:
                upload_root = os.path.join(current_app.root_path, UPLOAD_SUBDIR_ANC)
                os.makedirs(upload_root, exist_ok=True)

                for f in files:
                    if not f or f.filename.strip() == "":
                        continue
                    if not _allowed_file(f.filename):
                        flash("Formato de imagem não permitido nas fotos da ANC.", "warning")
                        continue

                    filename = secure_filename(f.filename)
                    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
                    final_name = f"{registro.id}_{ts}_{filename}"
                    abs_path = os.path.join(upload_root, final_name)

                    f.save(abs_path)

                    foto = ANCFoto(
                        anc_id=registro.id,
                        filename=os.path.join(UPLOAD_SUBDIR_ANC, final_name).replace("\\", "/"),
                        mime_type=f.mimetype,
                        size_bytes=os.path.getsize(abs_path),
                        storage_path=os.path.join(UPLOAD_SUBDIR_ANC, final_name).replace("\\", "/"),
                    )
                    db.session.add(foto)

            db.session.commit()
            flash("ANC registrada com sucesso!", "success")
            return redirect(url_for("anc"))
        except Exception as e:
            db.session.rollback()
            app.logger.exception("Erro ao salvar ANC")
            flash(f"Ocorreu um erro ao salvar: {e}", "danger")
            return redirect(url_for("anc"))

    return render_template("anc.html", hoje=date.today().isoformat())


ASSINATURA_SUBDIR = "static/uploads/anc/assinaturas"  # pasta física

def salvar_assinatura_png(anc_id: int, assinatura_base64: str) -> str:
    """
    Recebe um DataURL (data:image/png;base64,....) e salva como PNG.
    Retorna o path relativo ao /static (ex: uploads/anc/assinaturas/arquivo.png)
    """
    if not assinatura_base64:
        return ""

    assinatura_base64 = assinatura_base64.strip()

    # aceita apenas PNG vindo do canvas
    prefix = "data:image/png;base64,"
    if not assinatura_base64.startswith(prefix):
        raise ValueError("Assinatura inválida (formato esperado: PNG base64).")

    b64_data = assinatura_base64[len(prefix):]
    raw = base64.b64decode(b64_data)

    # pasta física dentro do projeto
    abs_dir = os.path.join(current_app.root_path, ASSINATURA_SUBDIR)
    os.makedirs(abs_dir, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    filename = secure_filename(f"anc_{anc_id}_assinatura_{ts}.png")
    abs_path = os.path.join(abs_dir, filename)

    with open(abs_path, "wb") as f:
        f.write(raw)

    # caminho relativo ao /static
    return f"uploads/anc/assinaturas/{filename}"


# ------------------------------------------------------
# ACHADOS E PERDIDOS
# ------------------------------------------------------
@app.route("/achados", methods=["GET", "POST"])
@login_required
def achados():
    if request.method == "POST":
        identificacao = (request.form.get("nome") or "").strip()
        descricao = (request.form.get("cpf") or "").strip()  # mantém seu campo de descrição
        data_hora_info = (request.form.get("armario") or "").strip()  # mantém seu campo de data/hora
        local_encontrado = (request.form.get("local") or request.form.get("local_encontrado") or request.form.get(
            "chave") or "").strip()
        turno_raw = (request.form.get("turno") or "").strip()
        if not descricao:
            flash("Informe a descrição do objeto.", "warning")
            return redirect(request.url)

        turno = None
        if turno_raw:
            try:
                turno = int(turno_raw)
                if turno not in (1, 2, 3, 4):
                    flash("Turno deve ser 1, 2, 3 ou 4.", "warning")
                    return redirect(request.url)
            except ValueError:
                flash("Turno inválido.", "warning")
                return redirect(request.url)

        foto_file = request.files.get("foto")
        foto_filename = foto_mime = None
        foto_size = None

        if foto_file and foto_file.filename:
            if not _allowed_file(foto_file.filename):
                flash("Formato de imagem não permitido.", "warning")
                return redirect(request.url)

            upload_folder = current_app.config.get(
                "UPLOAD_ACHADOS",
                os.path.join(current_app.root_path, "static", "uploads", "achados"),
            )
            os.makedirs(upload_folder, exist_ok=True)

            safe_name = secure_filename(foto_file.filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_name = f"{ts}_{safe_name}"
            abs_dest = os.path.join(upload_folder, safe_name)
            foto_file.save(abs_dest)

            # salvar relativo à pasta static
            foto_filename = os.path.relpath(
                abs_dest,
                start=os.path.join(current_app.root_path, "static"),
            ).replace("\\", "/")

            foto_mime = foto_file.mimetype
            try:
                foto_size = os.path.getsize(abs_dest)
            except OSError:
                foto_size = None

        registro = AchadoPerdido(
            identificacao=identificacao or None,
            descricao_objeto=descricao,
            data_hora_info=data_hora_info or None,
            local_encontrado=local_encontrado or None,
            turno=turno,
            foto_filename=foto_filename,
            foto_mime=foto_mime,
            foto_size_bytes=foto_size,
        )

        try:
            db.session.add(registro)
            db.session.commit()
            flash("Registro de achado/perdido salvo com sucesso!", "success")
            return redirect(url_for("post_achados"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Erro ao salvar achado/perdido")
            flash(f"Erro ao salvar: {e}", "danger")
            return redirect(request.url)

    return render_template("achados.html")



@app.route("/post_achados")
@login_required
def post_achados():
    itens = AchadoPerdido.query.order_by(AchadoPerdido.created_at.desc()).all()

    hoje = date.today()

    for item in itens:
        # Define a data de lançamento (prioridade: created_at)
        if item.created_at:
            lancado_em = item.created_at.date()
        elif hasattr(item, "data_encontro") and item.data_encontro:
            lancado_em = item.data_encontro
        else:
            lancado_em = None

        # Calcula dias em aberto
        if lancado_em:
            dias_em_aberto = (hoje - lancado_em).days
        else:
            dias_em_aberto = None

        # Campos virtuais para o template
        item.lancado_em = lancado_em
        item.dias_em_aberto = dias_em_aberto
        item.expirado_90 = True if dias_em_aberto is not None and dias_em_aberto >= 1 else False

    return render_template("post_achados.html", achados=itens)



@app.route('/achados/<int:item_id>/status', methods=['POST'])
@login_required
def atualizar_status_achado(item_id):
    item = AchadoPerdido.query.get_or_404(item_id)

    item.status_destino = request.form.get('status_destino')
    item.retirado_por   = request.form.get('retirado_por')

    db.session.commit()
    flash('Status atualizado com sucesso!', 'success')
    return redirect(url_for('achados'))
@app.route("/acessos", methods=["GET", "POST"])
@login_required
def acessos():
    return render_template("acessos.html")


@app.route("/fechamento_anc", methods=["GET", "POST"])
@login_required
def fechamento_anc():
    return render_template("fechamento_anc.html")




@app.route("/retirada", methods=["GET", "POST"])
@login_required
def retirada():
    return render_template("retirada.html")


@app.route("/fechar_ocorrencia", methods=["GET", "POST"])
@login_required
def fechar_ocorrencia():
    return render_template("fechar_ocorrencia.html")




# ------------------------------------------------------
# PERFIL
# ------------------------------------------------------
@app.route("/sair")
def sair():
    logout_user()
    flash("Usuario deslogado com sucesso!!", "alert-success")
    return redirect(url_for("home"))


@app.route("/perfil")
@login_required
def perfil():
    # foto do perfil
    foto_arquivo = getattr(current_user, "foto_perfil", None)
    if foto_arquivo:
        foto = url_for("static", filename=f"foto_perfil/{foto_arquivo}")
    else:
        foto = url_for("static", filename="foto_perfil/default.png")

    # total de posts do usuário (tenta relationship; senão FKs comuns)
    try:
        total_posts = len(current_user.posts)
    except Exception:
        if hasattr(Post, "user_id"):
            total_posts = Post.query.filter_by(user_id=current_user.id).count()
        elif hasattr(Post, "autor_id"):
            total_posts = Post.query.filter_by(autor_id=current_user.id).count()
        else:
            total_posts = 0

    return render_template("perfil.html", foto_perfil=foto, total_posts=total_posts)


def salvar_imagem(imagem):
    codigo = secrets.token_hex(8)
    _, extensao = os.path.splitext(imagem.filename)
    nome_arquivo = f"{codigo}{extensao}"

    pasta_destino = os.path.join(current_app.root_path, "static", "foto_perfil")
    os.makedirs(pasta_destino, exist_ok=True)

    caminho_completo = os.path.join(pasta_destino, nome_arquivo)

    tamanho = (200, 200)
    imagem_reduzida = Image.open(imagem)
    imagem_reduzida.thumbnail(tamanho)
    imagem_reduzida.save(caminho_completo)

    return nome_arquivo


@app.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def editar_perfil():
    form = FormEditarPerfil()
    if form.validate_on_submit():
        current_user.email = form.email.data
        current_user.username = form.username.data
        if form.foto_perfil.data:
            nome_imagem = salvar_imagem(form.foto_perfil.data)
            current_user.foto_perfil = nome_imagem
        db.session.commit()
        flash("Perfil atualizado com Sucesso!", "alert-success")
        return redirect(url_for("perfil"))
    elif request.method == "GET":
        form.email.data = current_user.email
        form.username.data = current_user.username

    foto_perfil = url_for("static", filename=f"foto_perfil/{current_user.foto_perfil}")
    return render_template("editarperfil.html", foto_perfil=foto_perfil, form=form)


# ------------------------------------------------------
# POSTS (rede social interna)
# ------------------------------------------------------
@app.route("/criar/post", methods=["GET", "POST"])
@login_required
def criar_post():
    form = FormCriarPost()
    if form.validate_on_submit():
        post = Post(
            titulo=form.titulo.data,
            corpo=form.corpo.data,
            autor=current_user,
        )
        db.session.add(post)
        db.session.commit()
        flash("Post criado com sucesso!", "success")
        return redirect(url_for("post"))  # redireciona para meus posts
    return render_template("criarpost.html", form=form)


@app.route("/post", methods=["GET", "POST"])
@login_required
def post():
    form = FormCriarPost()

    if form.validate_on_submit():
        novo_post = Post(
            titulo=form.titulo.data,
            corpo=form.corpo.data,
            autor=current_user,
        )
        db.session.add(novo_post)
        db.session.commit()
        flash("Post criado com sucesso!", "success")
        return redirect(url_for("post"))

    posts = Post.query.order_by(Post.data_criacao.desc()).all()
    return render_template("post.html", form=form, posts=posts)  # <-- removido ponto final


# Listagem dos posts do usuário logado (sem parâmetro, evita BuildError)
@app.route("/meus-posts")
@login_required
def listar_posts_usuario():
    if hasattr(Post, "user_id"):
        posts = (Post.query
                 .filter_by(user_id=current_user.id)
                 .order_by(Post.id.desc())
                 .all())
    elif hasattr(Post, "autor_id"):
        posts = (Post.query
                 .filter_by(autor_id=current_user.id)
                 .order_by(Post.id.desc())
                 .all())
    else:
        try:
            posts = sorted(list(current_user.posts), key=lambda p: p.id, reverse=True)
        except Exception:
            posts = []
    return render_template("meus_posts.html", posts=posts, total_posts=len(posts))


@app.route("/post/<int:post_id>/editar", methods=["GET", "POST"])
@login_required
def editar_post(post_id):
    post_obj = Post.query.get_or_404(post_id)

    if _post_owner_id(post_obj) != current_user.id:
        abort(403)

    form = FormCriarPost(obj=post_obj)
    if form.validate_on_submit():
        post_obj.titulo = form.titulo.data
        post_obj.corpo = form.corpo.data
        db.session.commit()
        flash("Post atualizado com sucesso!", "success")
        return redirect(url_for("post"))  # ou url_for("post")

    return render_template("editar_post.html", form=form, post=post_obj)


@app.route("/post/<int:post_id>/excluir", methods=["POST"])
@login_required
def excluir_post(post_id):
    post_obj = Post.query.get_or_404(post_id)

    if _post_owner_id(post_obj) != current_user.id:
        abort(403)

    db.session.delete(post_obj)
    db.session.commit()
    flash("Post excluído com sucesso!", "success")
    return redirect(url_for("post"))


# (Opcional) Visualização de um post específico
@app.route("/post/<int:post_id>")
@login_required
def ver_post(post_id):
    post_obj = Post.query.get_or_404(post_id)
    return render_template("post_detalhe.html", post=post_obj)


# ------------------------------------------------------
# ARMÁRIOS ROTATIVOS + QR
# ------------------------------------------------------
@app.route("/armarios_rotativos", methods=["GET", "POST"])
@login_required
def armarios_rotativos():
    form = FormArmarioRotativo()
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        empresa = (request.form.get("empresa") or "").strip()
        cpf_raw = (request.form.get("cpf") or "").strip()
        armario = (request.form.get("armario") or "").strip()
        chave = (request.form.get("chave") or "").strip()
        status = (request.form.get("status") or "").strip()
        turno_s = (request.form.get("turno") or "").strip()

        if not nome or not cpf_raw or not armario:
            flash("Preencha nome, CPF e armário.", "warning")
            return redirect(request.url)

        cpf = _normaliza_cpf(cpf_raw)

        turno = None
        if turno_s:
            try:
                turno = int(turno_s)
            except ValueError:
                turno = None

        # cria registro
        reg = ArmarioRotativo(
            nome=nome,
            empresa=empresa or None,
            cpf=cpf,
            armario=armario,
            chave=chave or None,
            status=status or "Ocupado",
            turno=turno,
        )
        db.session.add(reg)
        db.session.flush()  # já tem reg.id

        # texto do qr
        qr_texto = (
            f"Nome: {nome}\n"
            f"Empresa: {empresa}\n"
            f"CPF: {cpf}\n"
            f"Armário: {armario}\n"
            f"Chave: {chave}\n"
            f"Status: {status}\n"
            f"Turno: {turno if turno else ''}"
        )

        # pasta: Security_Leroy/static/qrcodes
        pasta_qr = os.path.join(current_app.root_path, "static", "qrcodes")
        os.makedirs(pasta_qr, exist_ok=True)

        nome_arquivo_qr = f"armario_{reg.id}.png"
        caminho_absoluto_qr = os.path.join(pasta_qr, nome_arquivo_qr)

        img = qrcode.make(qr_texto)
        img.save(caminho_absoluto_qr)

        reg.qr_filename = f"qrcodes/{nome_arquivo_qr}"

        db.session.commit()

        # guarda o último qr na sessão pra mostrar depois do redirect
        session["ultimo_qr"] = reg.qr_filename

        flash("Armário rotativo salvo e QR gerado!", "success")
        return redirect(url_for("armarios_rotativos"))

    # GET
    registros = (
        ArmarioRotativo.query.order_by(ArmarioRotativo.created_at.desc())
        .limit(10)
        .all()
    )
    ultimo_qr = session.pop("ultimo_qr", None)
    return render_template(
        "armarios_rotativos.html", registros=registros, form=form, ultimo_qr=ultimo_qr
    )


# ------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------
@app.route("/dash")
@login_required
def dash():
    # totais simples
    total_anc = ANC.query.count()
    total_ocorr = Ocorrencia.query.count()

    # ANC por dia (últimos 7 dias)
    anc_por_dia_raw = (
        db.session.query(func.date(ANC.created_at), func.count(ANC.id))
        .group_by(func.date(ANC.created_at))
        .order_by(func.date(ANC.created_at).desc())
        .limit(7)
        .all()
    )
    anc_por_dia_raw = anc_por_dia_raw[::-1]

    anc_labels = []
    anc_values = []
    for d, qtd in anc_por_dia_raw:
        # se vier string "2025-01-15"
        if isinstance(d, str):
            try:
                d_obj = datetime.strptime(d, "%Y-%m-%d").date()
                label = d_obj.strftime("%d/%m")
            except ValueError:
                # se não der pra converter, usa a própria string
                label = d
        else:
            # se já for date/datetime
            label = d.strftime("%d/%m")
        anc_labels.append(label)
        anc_values.append(qtd)

    # Ocorrências por dia (últimos 7 dias)
    ocorr_por_dia_raw = (
        db.session.query(func.date(Ocorrencia.created_at), func.count(Ocorrencia.id))
        .group_by(func.date(Ocorrencia.created_at))
        .order_by(func.date(Ocorrencia.created_at).desc())
        .limit(7)
        .all()
    )
    ocorr_por_dia_raw = ocorr_por_dia_raw[::-1]

    ocorr_labels = []
    ocorr_values = []
    for d, qtd in ocorr_por_dia_raw:
        if isinstance(d, str):
            try:
                d_obj = datetime.strptime(d, "%Y-%m-%d").date()
                label = d_obj.strftime("%d/%m")
            except ValueError:
                label = d
        else:
            label = d.strftime("%d/%m")
        ocorr_labels.append(label)
        ocorr_values.append(qtd)

    return render_template(
        "dash.html",
        total_anc=total_anc,
        total_ocorr=total_ocorr,
        anc_labels=anc_labels,
        anc_values=anc_values,
        ocorr_labels=ocorr_labels,
        ocorr_values=ocorr_values,
    )


@app.route("/achados/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
def editar_achado(item_id):
    item = AchadoPerdido.query.get_or_404(item_id)

    if request.method == "POST":
        # Captura com fallbacks (mantém compatibilidade com seu form atual)
        identificacao    = (request.form.get("identificacao") or request.form.get("nome") or "").strip()
        descricao        = (request.form.get("descricao") or request.form.get("cpf") or "").strip()
        data_hora_info   = (request.form.get("data_hora_info") or request.form.get("armario") or "").strip()
        local_encontrado = (request.form.get("local_encontrado") or request.form.get("local") or request.form.get("chave") or "").strip()
        turno_raw        = (request.form.get("turno") or "").strip()

        # validações simples
        if not descricao:
            flash("Informe a descrição do objeto.", "warning")
            return redirect(request.url)

        turno = None
        if turno_raw:
            try:
                turno = int(turno_raw)
                if turno not in (1, 2, 3, 4):
                    flash("Turno deve ser 1, 2, 3 ou 4.", "warning")
                    return redirect(request.url)
            except ValueError:
                flash("Turno inválido.", "warning")
                return redirect(request.url)

        # foto opcional (substitui se enviar nova)
        foto_file = request.files.get("foto")
        if foto_file and foto_file.filename:
            if not _allowed_file(foto_file.filename):
                flash("Formato de imagem não permitido.", "warning")
                return redirect(request.url)

            upload_folder = current_app.config.get(
                "UPLOAD_ACHADOS",
                os.path.join(current_app.root_path, "static", "uploads", "achados"),
            )
            os.makedirs(upload_folder, exist_ok=True)

            safe_name = secure_filename(foto_file.filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_name = f"{ts}_{safe_name}"
            abs_dest = os.path.join(upload_folder, safe_name)
            foto_file.save(abs_dest)

            # Salva caminho relativo a /static
            foto_rel = os.path.relpath(
                abs_dest,
                start=os.path.join(current_app.root_path, "static"),
            ).replace("\\", "/")

            # Opcional: remover a antiga do disco (se quiser e se estiver dentro de /static)
            try:
                if item.foto_filename:
                    old_abs = os.path.join(current_app.root_path, "static", item.foto_filename)
                    if os.path.isfile(old_abs):
                        os.remove(old_abs)
            except Exception:
                pass

            item.foto_filename = foto_rel
            item.foto_mime = foto_file.mimetype
            try:
                item.foto_size_bytes = os.path.getsize(abs_dest)
            except OSError:
                item.foto_size_bytes = None

        # Atualiza campos
        item.identificacao = identificacao or None
        item.descricao_objeto = descricao
        item.data_hora_info = data_hora_info or None
        item.local_encontrado = local_encontrado or None
        item.turno = turno

        db.session.commit()
        flash("Registro atualizado com sucesso!", "success")
        return redirect(url_for("post_achados"))

    # GET -> carrega formulário simples
    return render_template("editar_achado.html", item=item)


# Excluir achado/perdido
@app.route("/achados/<int:item_id>/excluir", methods=["POST"])
@login_required
def excluir_achado(item_id):
    item = AchadoPerdido.query.get_or_404(item_id)

    # Opcional: apagar foto do disco se existir
    try:
        if item.foto_filename:
            abs_path = os.path.join(current_app.root_path, "static", item.foto_filename)
            if os.path.isfile(abs_path):
                os.remove(abs_path)
    except Exception:
        pass

    db.session.delete(item)
    db.session.commit()
    flash("Registro excluído com sucesso!", "success")
    return redirect(url_for("post_achados"))

# Página principal (renderiza seu template). Pode ficar como está se você já a tem.
@app.route("/ativos", methods=["GET"])
@login_required
def ativos():
    return render_template("ativos.html", pessoa=None, ativos=None)


@app.route("/cadastrar_ativo", methods=["POST"])
@login_required
def cadastrar_ativo():
    try:
        # 1) Campos do formulário
        nome        = (request.form.get("nome") or "").strip()
        cpf_raw     = (request.form.get("cpf") or "").strip()
        data_str    = (request.form.get("data") or "").strip()
        cargo       = (request.form.get("cargo") or "").strip()
        empresa     = (request.form.get("empresa") or "").strip()
        turno       = (request.form.get("turno") or "").strip()
        tipo_ativo  = (request.form.get("tipo_ativo") or "").strip()
        imei_numero = (request.form.get("imei_numero") or "").strip()
        observacoes = (request.form.get("observacoes") or "").strip()

        current_app.logger.info(
            f"[POST /cadastrar_ativo] nome={nome!r} cpf={cpf_raw!r} data={data_str!r} "
            f"tipo={tipo_ativo!r} imei_numero={imei_numero!r}"
        )

        if not imei_numero:
            flash("Informe o IMEI ou Nº do ativo.", "warning")
            return redirect(url_for("ativos"))

        # 2) Normaliza CPF
        cpf_norm = _normaliza_cpf(cpf_raw) if cpf_raw else None

        # 3) Data – vamos armazenar como string mesmo (coluna é String)
        data_val = data_str or None

        # 4) Localiza/cria PessoaAtivo (dono)
        pessoa = None
        if cpf_norm:
            pessoa = PessoaAtivo.query.filter_by(cpf=cpf_norm).first()

        if not pessoa:
            pessoa = PessoaAtivo(
                nome=nome or None,
                cpf=cpf_norm or None,
                data=data_val,
                cargo=cargo or None,
                empresa=empresa or None,
                turno=turno or None,
            )
            db.session.add(pessoa)
            db.session.flush()  # garante pessoa.id
        else:
            # Atualiza dados básicos se quiser manter sempre os mais recentes
            pessoa.nome = nome or pessoa.nome
            pessoa.data = data_val or pessoa.data
            pessoa.cargo = cargo or pessoa.cargo
            pessoa.empresa = empresa or pessoa.empresa
            pessoa.turno = turno or pessoa.turno

        # 5) Foto do dono (campo: foto_dono)
        foto_dono_file = request.files.get("foto_dono")
        if foto_dono_file and foto_dono_file.filename:
            if not _allowed_file(foto_dono_file.filename):
                flash("Formato de imagem não permitido para a foto do dono.", "warning")
            else:
                safe_name = secure_filename(foto_dono_file.filename)
                ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
                prefix = (cpf_norm or "dono").replace(".", "").replace("-", "")
                final_name = f"{prefix}_{ts}_{safe_name}"
                abs_path = os.path.join(FOTOS_DONO_DIR, final_name)

                foto_dono_file.save(abs_path)

                # No banco, guardamos caminho relativo a /static:
                # ex.: 'foto_dono/xxxxx.jpg'
                pessoa.foto_dono = f"foto_dono/{final_name}"

        # 6) Cria Ativo
        ativo = Ativo(
            pessoa=pessoa,
            tipo=tipo_ativo or None,
            imei_ou_numero=imei_numero or None,
            data=data_val,
            status="Em uso",
            observacoes=observacoes or None,
        )
        db.session.add(ativo)
        db.session.flush()  # garante ativo.id

        # 7) Fotos dos ativos (múltiplas) – campo: fotos_ativos
        files_ativos = request.files.getlist("fotos_ativos")
        if files_ativos:
            os.makedirs(FOTOS_ATIVOS_DIR, exist_ok=True)

            for f in files_ativos:
                if not f or not f.filename:
                    continue
                if not _allowed_file(f.filename):
                    flash(f"Formato de imagem não permitido: {f.filename}", "warning")
                    continue

                safe_name = secure_filename(f.filename)
                ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
                final_name = f"ativo_{ativo.id}_{ts}_{safe_name}"
                abs_path = os.path.join(FOTOS_ATIVOS_DIR, final_name)
                f.save(abs_path)

                # Caminho relativo a /static
                foto_rel = os.path.relpath(
                    abs_path,
                    start=os.path.join(current_app.root_path, "static"),
                ).replace("\\", "/")

                foto = FotoAtivo(
                    ativo=ativo,
                    filename=foto_rel,
                )
                db.session.add(foto)

        # 8) Commit
        db.session.commit()
        current_app.logger.info(
            f"[POST /cadastrar_ativo] OK: ativo_id={ativo.id} pessoa_id={getattr(pessoa,'id',None)}"
        )

        flash("Ativo e fotos cadastrados com sucesso!", "success")
        # Depois do cadastro, já manda para consulta por CPF do dono, se tiver
        if cpf_norm:
            return redirect(url_for("consulta_por_cpf", cpf=cpf_norm))
        return redirect(url_for("ativos"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao cadastrar ativo")
        flash(f"Erro ao cadastrar ativo: {e}", "danger")
        return redirect(url_for("ativos"))
# ========== Consultas (coluna direita do template) ==========

@app.route("/ativos/consulta/cpf", methods=["GET"])
@login_required
def consulta_por_cpf():
    cpf_raw = (request.args.get("cpf") or "").strip()
    cpf_norm = _normaliza_cpf(cpf_raw) if cpf_raw else None

    pessoa = None
    ativos = []

    if cpf_norm:
        pessoa = PessoaAtivo.query.filter_by(cpf=cpf_norm).first()
        if pessoa:
            ativos = (
                Ativo.query.filter_by(pessoa_id=pessoa.id)
                .order_by(Ativo.id.desc())
                .all()
            )
        else:
            flash("Nenhuma pessoa encontrada para o CPF informado.", "info")

    return render_template("ativos.html", pessoa=pessoa, ativos=ativos)

@app.route("/ativos/consulta/imei", methods=["GET"])
@login_required
def consulta_por_imei():
    imei = (request.args.get("imei") or "").strip()
    pessoa = None
    ativos = []

    if imei:
        ativos = (
            Ativo.query.filter(Ativo.imei_ou_numero.ilike(f"%{imei}%"))
            .order_by(Ativo.id.desc())
            .all()
        )
        if len(ativos) == 1 and ativos[0].pessoa:
            pessoa = ativos[0].pessoa
        elif not ativos:
            flash("Nenhum ativo encontrado para o IMEI informado.", "info")

    return render_template("ativos.html", pessoa=pessoa, ativos=ativos)

@app.route("/ativos/consulta/numero", methods=["GET"])
@login_required
def consulta_por_numero():
    numero = (request.args.get("numero") or "").strip()
    pessoa = None
    ativos = []

    if numero:
        ativos = (
            Ativo.query.filter(Ativo.imei_ou_numero.ilike(f"%{numero}%"))
            .order_by(Ativo.id.desc())
            .all()
        )
        if len(ativos) == 1 and ativos[0].pessoa:
            pessoa = ativos[0].pessoa
        elif not ativos:
            flash("Nenhum ativo encontrado para o número informado.", "info")

    return render_template("ativos.html", pessoa=pessoa, ativos=ativos)

@app.route("/editar_ativos", methods=["GET"])
@login_required
def editar_ativos():
    cpf_raw = (request.args.get("cpf") or "").strip()
    ativo_id = request.args.get("ativo_id", type=int)

    pessoa = None
    ativos = []
    ativo_edit = None

    if cpf_raw:
        cpf_norm = _normaliza_cpf(cpf_raw)
        pessoa = PessoaAtivo.query.filter_by(cpf=cpf_norm).first()
        if pessoa:
            ativos = (
                Ativo.query
                .filter_by(pessoa_id=pessoa.id)
                .order_by(Ativo.id.desc())
                .all()
            )
            if ativo_id:
                ativo_edit = (
                    Ativo.query
                    .filter_by(id=ativo_id, pessoa_id=pessoa.id)
                    .first()
                )
        else:
            flash("Nenhum cadastro encontrado para este CPF.", "info")

    return render_template(
        "editar_ativos.html",
        pessoa=pessoa,
        ativos=ativos,
        ativo_edit=ativo_edit,
        cpf_busca=cpf_raw,
    )


@app.route("/ativos/<int:ativo_id>/editar", methods=["POST"])
@login_required
def editar_ativo(ativo_id):
    ativo = Ativo.query.get_or_404(ativo_id)
    pessoa = ativo.pessoa

    tipo = (request.form.get("tipo_ativo") or "").strip()
    observacoes = (request.form.get("observacoes") or "").strip()

    if tipo:
        ativo.tipo = tipo
    ativo.observacoes = observacoes or None

    # novas fotos (campo name="fotos")
    files = request.files.getlist("fotos")
    if files:
        upload_root = os.path.join(current_app.root_path, "static", "uploads", "ativos")
        os.makedirs(upload_root, exist_ok=True)

        for f in files:
            if not f or not f.filename:
                continue
            if not _allowed_file(f.filename):
                flash(f"Formato de imagem não permitido: {f.filename}", "warning")
                continue

            safe_name = secure_filename(f.filename)
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            final_name = f"{ativo.id}_{ts}_{safe_name}"
            abs_path = os.path.join(upload_root, final_name)
            f.save(abs_path)

            foto_rel = os.path.relpath(
                abs_path,
                start=os.path.join(current_app.root_path, "static"),
            ).replace("\\", "/")

            nova_foto = FotoAtivo(
                ativo_id=ativo.id,
                filename=foto_rel,
            )
            db.session.add(nova_foto)

    db.session.commit()
    flash("Ativo atualizado com sucesso!", "success")

    cpf_param = pessoa.cpf if pessoa and pessoa.cpf else ""
    if cpf_param:
        return redirect(url_for("editar_ativos", cpf=cpf_param, ativo_id=ativo.id))
    return redirect(url_for("editar_ativos"))


@app.route("/ativos/<int:ativo_id>/excluir", methods=["POST"])
@login_required
def excluir_ativo(ativo_id):
    ativo = Ativo.query.get_or_404(ativo_id)
    pessoa = ativo.pessoa

    # apaga fotos + arquivos
    for foto in list(ativo.fotos):
        if foto.filename:
            rel = foto.filename.lstrip("/").replace("\\", "/")
            abs_path = os.path.join(current_app.root_path, "static", rel)
            try:
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
            except OSError:
                pass
        db.session.delete(foto)

    db.session.delete(ativo)
    db.session.commit()
    flash("Ativo excluído com sucesso!", "success")

    cpf_param = pessoa.cpf if pessoa and pessoa.cpf else ""
    if cpf_param:
        return redirect(url_for("editar_ativos", cpf=cpf_param))
    return redirect(url_for("editar_ativos"))


@app.route("/ativos/excluir_pessoa/<int:pessoa_id>", methods=["POST"])
@login_required
def excluir_pessoa_ativos(pessoa_id):
    pessoa = PessoaAtivo.query.get_or_404(pessoa_id)

    # apaga foto do dono (se houver)
    if pessoa.foto_dono:
        rel = pessoa.foto_dono.lstrip("/").replace("\\", "/")
        abs_path = os.path.join(current_app.root_path, "static", rel)
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except OSError:
            pass

    # apaga todos os ativos + fotos + arquivos
    for ativo in list(pessoa.ativos):
        for foto in list(ativo.fotos):
            if foto.filename:
                rel_f = foto.filename.lstrip("/").replace("\\", "/")
                abs_path_f = os.path.join(current_app.root_path, "static", rel_f)
                try:
                    if os.path.isfile(abs_path_f):
                        os.remove(abs_path_f)
                except OSError:
                    pass
            db.session.delete(foto)
        db.session.delete(ativo)

    db.session.delete(pessoa)
    db.session.commit()
    flash("Cadastro e todos os ativos deste CPF foram excluídos.", "success")
    return redirect(url_for("editar_ativos"))



@app.route("/controle_acessos", methods=["GET", "POST"])
@login_required
def controle_acessos():
    if request.method == "POST":
        nome = (request.form.get("nome_solicitante") or "").strip()
        data_str = (request.form.get("data_ocorrencia") or "").strip()
        empresa = (request.form.get("empresa") or "").strip()
        cpf_raw = (request.form.get("envolvido_gc") or "").strip()
        responsavel = (request.form.get("responsavel") or "").strip()
        turno_label = (request.form.get("turno") or "").strip()

        if not nome:
            flash("Informe o Nome.", "warning")
            return redirect(url_for("controle_acessos"))

        data_reg = None
        if data_str:
            try:
                data_reg = datetime.strptime(data_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Data inválida (use YYYY-MM-DD).", "warning")
                return redirect(url_for("controle_acessos"))

        turno = _turno_from_label(turno_label)
        cpf = _normaliza_cpf(cpf_raw)

        foto_rel = foto_mime = None
        foto_size = None
        foto_file = request.files.get("foto")
        if foto_file and foto_file.filename:
            foto_rel, foto_mime, foto_size = _save_acesso_foto(foto_file)

        reg = AcessoRegistro(
            nome=nome,
            data_registro=data_reg,
            empresa=empresa or None,
            cpf=cpf or None,
            responsavel=responsavel or None,
            turno=turno,
            foto_filename=foto_rel,
            foto_mime=foto_mime,
            foto_size_bytes=foto_size,
        )

        db.session.add(reg)
        db.session.commit()
        flash("Acesso registrado com sucesso!", "success")
        return redirect(url_for("pesquisar_acesso"))

    # GET: renderiza a página do formulário (seu template).
    return render_template("acessos.html")


@app.route("/pesquisar_acesso", methods=["GET"])
@login_required
def pesquisar_acesso():
    # Filtros simples
    nome_q = (request.args.get("nome") or "").strip()
    cpf_q_raw = (request.args.get("cpf") or "").strip()
    data_q = (request.args.get("data") or "").strip()

    query = AcessoRegistro.query

    if nome_q:
        query = query.filter(AcessoRegistro.nome.ilike(f"%{nome_q}%"))
    if cpf_q_raw:
        cpf_q = _normaliza_cpf(cpf_q_raw)
        if cpf_q:
            query = query.filter(AcessoRegistro.cpf == cpf_q)
    if data_q:
        try:
            d = datetime.strptime(data_q, "%Y-%m-%d").date()
            query = query.filter(AcessoRegistro.data_registro == d)
        except ValueError:
            flash("Data do filtro inválida. Use YYYY-MM-DD.", "warning")

    registros = query.order_by(AcessoRegistro.created_at.desc()).limit(50).all()

    # Você pode ter um template dedicado (ex.: pesquisar_acesso.html)
    # que liste registros com a foto:
    return render_template(
        "pesquisar_acesso.html",
        registros=registros,
        filtro_nome=nome_q,
        filtro_cpf=cpf_q_raw,
        filtro_data=data_q,
    )
# imports necessários no topo do arquivo
from Security_Leroy.models import AcessoRegistro
import os

# --- LISTAGEM / POSTAGENS DE ACESSOS ---
@app.route("/post_acessos", methods=["GET"])
@login_required
def post_acessos():
    registros = AcessoRegistro.query.order_by(AcessoRegistro.created_at.desc()).all()
    return render_template("pesquisar_acesso.html", registros=registros)

# --- EXCLUIR UM REGISTRO DE ACESSO ---
@app.route("/acessos/<int:acesso_id>/excluir", methods=["POST"])
@login_required
def excluir_acesso(acesso_id):
    reg = AcessoRegistro.query.get_or_404(acesso_id)

    # Remove a foto do disco (se existir e for caminho relativo a /static)
    if reg.foto_filename:
        try:
            # normaliza para caminho físico
            rel = reg.foto_filename.lstrip("/").replace("\\", "/")
            abs_path = os.path.join(current_app.root_path, "static", rel)
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except OSError:
            pass

    db.session.delete(reg)
    db.session.commit()
    flash("Registro de acesso excluído com sucesso.", "success")
    return redirect(url_for("pesquisar_acesso"))



@app.route("/perfil/girar-foto", methods=["POST"])
@login_required
def girar_foto_perfil():
    # Verifica arquivo atual
    filename = getattr(current_user, "foto_perfil", None)
    if not filename:
        flash("Nenhuma foto de perfil para girar.", "warning")
        return redirect(url_for("editar_perfil"))

    # Caminhos
    pasta = os.path.join(current_app.root_path, "static", "foto_perfil")
    caminho = os.path.join(pasta, filename)

    # Se estiver usando a default, primeiro faz uma cópia pro usuário
    if filename.lower() == "default.png" or not os.path.isfile(caminho):
        # Cria cópia personalizada a partir da default
        origem_default = os.path.join(pasta, "default.png")
        if not os.path.isfile(origem_default):
            flash("Imagem padrão não encontrada para copiar.", "danger")
            return redirect(url_for("editar_perfil"))

        # Gera um nome novo
        base, ext = os.path.splitext("perfil_" + str(current_user.id) + ".png")
        novo_nome = base + ext
        novo_caminho = os.path.join(pasta, novo_nome)

        try:
            img = Image.open(origem_default)
            img.save(novo_caminho)
        except Exception as e:
            flash(f"Falha ao criar cópia da foto: {e}", "danger")
            return redirect(url_for("editar_perfil"))

        current_user.foto_perfil = novo_nome
        db.session.commit()
        filename = novo_nome
        caminho = novo_caminho

    # Gira a imagem 90° no sentido horário (PIL usa ângulo anti-horário, então -90)
    try:
        img = Image.open(caminho)
        # Corrige orientação EXIF antes (caso venha de celular)
        img = ImageOps.exif_transpose(img)
        img = img.rotate(-90, expand=True)  # horário
        # Mantém o formato original, se possível
        ext = os.path.splitext(filename)[1].lower()
        format_hint = "PNG" if ext not in [".jpg", ".jpeg"] else "JPEG"
        img.save(caminho, format=format_hint)
        flash("Foto girada com sucesso!", "success")
    except Exception as e:
        current_app.logger.exception("Erro ao girar foto de perfil")
        flash(f"Não foi possível girar a foto: {e}", "danger")

    return redirect(url_for("editar_perfil"))


# ------------------------------------------------------
@app.route("/passagem_turno", methods=["GET", "POST"])
@login_required
def passagem_turno():
    if request.method == "POST":
        nome          = (request.form.get("nome") or "").strip()
        auditorias    = (request.form.get("auditorias") or "").strip()
        data_hora     = (request.form.get("data_hora") or "").strip()
        lancamento    = (request.form.get("lancamento") or "").strip()
        turno_raw     = (request.form.get("turno") or "").strip()
        operador      = (request.form.get("operador") or "").strip()
        monitoramento = (request.form.get("monitoramento") or "").strip()
        liberacao     = (request.form.get("liberacao") or "").strip()

        if not nome:
            flash("Informe o nome na passagem de turno.", "warning")
            return redirect(url_for("passagem_turno"))

        turno = None
        if turno_raw:
            try:
                t = int(turno_raw)
                if t in (1, 2, 3, 4):
                    turno = t
            except ValueError:
                turno = None

        reg = PassagemTurno(
            nome=nome,
            auditorias=auditorias or None,
            data_hora=data_hora or None,
            lancamento=lancamento or None,
            turno=turno,
            operador=operador or None,
            monitoramento=monitoramento or None,
            liberacao=liberacao or None,
        )

        try:
            db.session.add(reg)
            db.session.commit()
            flash("Passagem de turno registrada com sucesso!", "success")
            return redirect(url_for("post_passagem_turno"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Erro ao salvar PassagemTurno")
            flash(f"Erro ao salvar passagem de turno: {e}", "danger")
            return redirect(url_for("passagem_turno"))

    return render_template("passagem_turno.html")




@app.route("/post_passagem_turno", methods=["GET"])
@login_required
def post_passagem_turno():
    registros = PassagemTurno.query.order_by(PassagemTurno.created_at.desc()).all()
    return render_template("post_passagem_turno.html", registros=registros)


@app.route("/passagem_turno/<int:passagem_id>/excluir", methods=["POST"])
@login_required
def excluir_passagem_turno(passagem_id):
    reg = PassagemTurno.query.get_or_404(passagem_id)
    db.session.delete(reg)
    db.session.commit()
    flash("Registro de passagem de turno excluído com sucesso.", "success")
    return redirect(url_for("post_passagem_turno"))

from flask import request, render_template, redirect, url_for, flash


#@app.route("/solicitacao_imagem", methods=["GET", "POST"])
#@login_required
#def solicitacao_imagem():
    #form = FormSolicitacaoImagem()

    #if form.validate_on_submit():
        #solicitacao = SolicitacaoImagem(
            #nome=form.nome.data.strip(),
            #descricao_ocorrencia=form.descricao_ocorrencia.data.strip(),
            #data_hora_info=form.data_hora_info.data.strip(),
            #envolvidos=form.envolvidos.data.strip() if form.envolvidos.data else None,
            #turno=form.turno.data or None,
            #coordenador=form.coordenador.data.strip() if form.coordenador.data else None,
            #operador_id=current_user.id,
        #)
        #db.session.add(solicitacao)
        #db.session.commit()

        #flash("Solicitação de imagem registrada com sucesso!", "success")
        #return redirect(url_for("solicitacao_imagem"))

    #return render_template("investigacoes.html", form=form)




@app.route("/post_investigacoes", methods=["GET"])
@login_required
def post_investigacoes():
    investigacoes = (
        SolicitacaoImagem.query
        .order_by(SolicitacaoImagem.id.desc())
        .all()
    )
    return render_template("post_investigacoes.html", investigacoes=investigacoes)


@app.route("/investigacoes/<int:inv_id>/status", methods=["POST"])
@login_required
def atualizar_status_investigacao(inv_id):
    inv = SolicitacaoImagem.query.get_or_404(inv_id)

    acao = (request.form.get("status") or "").strip().lower()

    try:
        if acao == "excluir":
            db.session.delete(inv)
            db.session.commit()
            flash("Investigação excluída com sucesso!", "success")

        elif acao in ("pendente", "em andamento", "fechado"):
            # grava padronizado (primeira maiúscula)
            if acao == "em andamento":
                inv.status = "Em andamento"
            elif acao == "pendente":
                inv.status = "Pendente"
            elif acao == "fechado":
                inv.status = "Fechado"

            db.session.commit()
            flash("Status atualizado com sucesso!", "success")

        else:
            flash("Ação de status inválida.", "warning")

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao atualizar status de investigação")
        flash(f"Erro ao atualizar: {e}", "danger")

    return redirect(url_for("post_investigacoes"))

@app.route("/armarios/pesquisar", methods=["GET"])
@login_required
def pesquisar_armarios():
    nome_q = (request.args.get("nome") or "").strip()
    cpf_q_raw = (request.args.get("cpf") or "").strip()
    arm_q = (request.args.get("armario") or "").strip()

    cpf_q = _normaliza_cpf(cpf_q_raw)

    query = ArmarioRegistro.query
    if nome_q:
        query = query.filter(ArmarioRegistro.nome.ilike(f"%{nome_q}%"))
    if cpf_q:
        query = query.filter(ArmarioRegistro.cpf == cpf_q)
    if arm_q:
        query = query.filter(ArmarioRegistro.armario.ilike(f"%{arm_q}%"))

    resultados = query.order_by(ArmarioRegistro.created_at.desc()).all()

    if not resultados:
        flash("Nenhum registro encontrado para os filtros informados.", "info")

    return render_template(
        "armarios.html",
        resultados=resultados,
        filtro_nome=nome_q,
        filtro_cpf=cpf_q_raw,
        filtro_armario=arm_q,
    )

@app.route("/armarios/<int:armario_id>/editar", methods=["GET", "POST"])
@login_required
def editar_armario(armario_id):
    reg = ArmarioRegistro.query.get_or_404(armario_id)

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        cpf_raw = (request.form.get("cpf") or "").strip()
        armario = (request.form.get("armario") or "").strip()
        chave = (request.form.get("chave") or "").strip()
        coordenador = (request.form.get("coordenador") or "").strip()
        turno_str = (request.form.get("turno") or "").strip()

        if not nome:
            flash("Informe o Nome.", "warning")
            return redirect(request.url)
        if not cpf_raw:
            flash("Informe o CPF.", "warning")
            return redirect(request.url)
        if not armario:
            flash("Informe o número/identificação do Armário.", "warning")
            return redirect(request.url)

        cpf_normalizado = _normaliza_cpf(cpf_raw)

        turno_int, turno_err = _valida_turno(turno_str)
        if turno_err:
            flash(turno_err, "warning")
            return redirect(request.url)

        try:
            reg.nome = nome
            reg.cpf = cpf_normalizado
            reg.armario = armario
            reg.chave = chave or None
            reg.turno = turno_int
            reg.coordenador = coordenador or None

            db.session.commit()
            flash("Registro de armário atualizado com sucesso!", "success")

            # se você tiver a rota pesquisar_armarios, use ela:
            return redirect(url_for("pesquisar_armarios"))
            # se não tiver, pode trocar por:
            # return redirect(url_for("armarios"))

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Erro ao atualizar ArmarioRegistro")
            flash(f"Erro ao atualizar: {e}", "danger")
            return redirect(request.url)

    # GET -> mostra um template de edição (você pode criar editar_armario.html)
    return render_template("editar_armario.html", registro=reg)

@app.route("/armarios/<int:armario_id>/excluir", methods=["POST"])
@login_required
def excluir_armario(armario_id):
    reg = ArmarioRegistro.query.get_or_404(armario_id)

    try:
        db.session.delete(reg)
        db.session.commit()
        flash("Registro de armário excluído com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao excluir ArmarioRegistro")
        flash(f"Erro ao excluir: {e}", "danger")

    # volta para a tela de pesquisa/listagem
    return redirect(url_for("pesquisar_armarios"))
    # se preferir, pode usar:
    # return redirect(url_for("armarios"))

def formatar_cpf(cpf_numerico: str) -> str:
    if len(cpf_numerico) != 11:
        return cpf_numerico
    return f"{cpf_numerico[0:3]}.{cpf_numerico[3:6]}.{cpf_numerico[6:9]}-{cpf_numerico[9:]}"


@app.route("/api/armario_por_cpf", methods=["GET"])
def armario_por_cpf():
    cpf = request.args.get("cpf", "").strip()

    # deixa só números
    cpf_digits = "".join(filter(str.isdigit, cpf))

    if not cpf_digits:
        return jsonify({"sucesso": False, "mensagem": "CPF não informado."}), 400

    # Normaliza o CPF do banco removendo "." e "-" e compara só pelos dígitos
    registro = ArmarioRegistro.query.filter(
        func.replace(
            func.replace(ArmarioRegistro.cpf, ".", ""),
            "-", ""
        ) == cpf_digits
    ).first()

    if not registro:
        return jsonify({"sucesso": False, "mensagem": "CPF não encontrado."}), 404

    return jsonify({
        "sucesso": True,
        "nome": registro.nome or "",
        "armario": registro.armario or "",
        "chave": registro.chave or "",
        "turno": str(registro.turno) if registro.turno is not None else "",
        "coordenador": registro.coordenador or ""
    })
@app.route("/retirada_chave", methods=["GET", "POST"])
def retirada_chave():
    if request.method == "POST":
        ret_cpf         = request.form.get("ret_cpf")
        ret_nome        = request.form.get("ret_nome")
        ret_armario     = request.form.get("ret_armario")
        ret_chave       = request.form.get("ret_chave")
        ret_turno       = request.form.get("ret_turno")
        ret_coordenador = request.form.get("ret_coordenador")

        # aqui você registra a retirada em outra tabela, se quiser
        # retirada = RetiradaArmario(...)
        # db.session.add(retirada)
        # db.session.commit()

        return redirect(url_for("retirada"))

    return render_template("retirada.html")




@app.route("/anc_posts")
def anc_posts():
    posts = ANC.query.order_by(ANC.created_at.desc()).all()
    return render_template("anc_posts.html", anc_posts=posts)

# Fechar ANC
@app.route("/anc/<int:anc_id>/fechar", methods=["POST"])
def anc_alterar_status(anc_id):
    anc = ANC.query.get_or_404(anc_id)
    anc.status = "Fechada"
    db.session.commit()
    flash(f"ANC #{anc.id} fechada com sucesso!", "success")
    return redirect(url_for("anc_posts"))


# Anexar arquivo/imagem
@app.route("/anc/<int:anc_id>/anexar", methods=["POST"])
@login_required
def anc_anexar_arquivo(anc_id):
    try:
        anc = ANC.query.get_or_404(anc_id)

        # 1) arquivo (imagem)
        file = request.files.get("arquivo")
        if not file or file.filename.strip() == "":
            flash("Nenhum arquivo selecionado.", "warning")
            return redirect(url_for("anc_posts"))

        if not _allowed_file(file.filename):
            flash("Formato de arquivo não permitido. Envie apenas imagens.", "warning")
            return redirect(url_for("anc_posts"))

        upload_root = os.path.join(current_app.root_path, "static/uploads/anc")
        os.makedirs(upload_root, exist_ok=True)

        filename = secure_filename(file.filename)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        final_name = f"{anc.id}_{ts}_{filename}"
        abs_path = os.path.join(upload_root, final_name)

        file.save(abs_path)

        foto = ANCFoto(
            anc_id=anc.id,
            filename=f"uploads/anc/{final_name}",  # relativo ao /static
            mime_type=file.mimetype,
            size_bytes=os.path.getsize(abs_path),
            storage_path=f"uploads/anc/{final_name}",
        )
        db.session.add(foto)

        # 2) assinatura (PNG)
        assinatura_base64 = (request.form.get("assinatura_base64") or "").strip()
        if assinatura_base64:
            rel_path = salvar_assinatura_png(anc.id, assinatura_base64)
            anc.assinatura_filename = rel_path  # ex: uploads/anc/assinaturas/anc_1_assinatura_x.png

        db.session.commit()
        flash("Arquivo e assinatura enviados com sucesso!", "success")
        return redirect(url_for("anc_posts"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao anexar arquivo/assinatura")
        flash(f"Erro ao anexar: {e}", "danger")
        return redirect(url_for("anc_posts"))
# LISTA DO MURAL
@app.route("/mural")
@login_required
def mural():
    mural_posts = Mural.query.order_by(Mural.data_criacao.desc()).all()
    return render_template("mural.html", mural_posts=mural_posts)


# NOVA POSTAGEM NO MURAL
@app.route("/mural/novo", methods=["GET", "POST"])
@login_required
def criar_mural():
    form = MuralForm()

    if form.validate_on_submit():
        imagem_file = form.imagem.data
        filename = None

        if imagem_file:
            filename = secure_filename(imagem_file.filename)
            # pasta: static/mural
            upload_folder = os.path.join(current_app.root_path, "static", "mural")
            os.makedirs(upload_folder, exist_ok=True)
            upload_path = os.path.join(upload_folder, filename)
            imagem_file.save(upload_path)

        mural_post = Mural(
            titulo=form.titulo.data.strip() if form.titulo.data else None,
            corpo=form.corpo.data.strip() if form.corpo.data else None,
            imagem_filename=filename,
            autor=current_user
        )

        db.session.add(mural_post)
        db.session.commit()
        flash("Postagem adicionada ao mural com sucesso!", "success")
        return redirect(url_for("mural"))

    return render_template("novo_mural.html", form=form)


@app.route("/mural/<int:mural_id>/editar", methods=["GET", "POST"])
@login_required
def editar_mural(mural_id):
    mural_post = Mural.query.get_or_404(mural_id)

    # Só o autor pode editar
    if mural_post.autor != current_user:
        abort(403)

    form = MuralForm()

    if form.validate_on_submit():
        # Atualiza título e corpo
        mural_post.titulo = form.titulo.data.strip() if form.titulo.data else None
        mural_post.corpo = form.corpo.data.strip() if form.corpo.data else None

        # Se o usuário enviar uma nova imagem, substitui
        imagem_file = form.imagem.data
        if imagem_file:
            filename = secure_filename(imagem_file.filename)
            upload_folder = os.path.join(current_app.root_path, "static", "mural")
            os.makedirs(upload_folder, exist_ok=True)
            upload_path = os.path.join(upload_folder, filename)

            # Remove imagem antiga (se houver) – opcional
            if mural_post.imagem_filename:
                old_path = os.path.join(upload_folder, mural_post.imagem_filename)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    # Se der erro ao deletar, só ignora para não quebrar a edição
                    pass

            imagem_file.save(upload_path)
            mural_post.imagem_filename = filename

        db.session.commit()
        flash("Postagem do mural atualizada com sucesso!", "success")
        return redirect(url_for("mural"))

    # Pré-preencher o form no GET
    if request.method == "GET":
        form.titulo.data = mural_post.titulo
        form.corpo.data = mural_post.corpo

    return render_template("mural_editar.html", form=form, mural_post=mural_post)

@app.route("/mural/<int:mural_id>/excluir", methods=["POST"])
@login_required
def excluir_mural(mural_id):
    mural_post = Mural.query.get_or_404(mural_id)

    # Só o autor pode excluir
    if mural_post.autor != current_user:
        abort(403)

    # Apagar imagem do disco (se houver)
    if mural_post.imagem_filename:
        upload_folder = os.path.join(current_app.root_path, "static", "mural")
        img_path = os.path.join(upload_folder, mural_post.imagem_filename)
        try:
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception:
            # Se falhar, não impede de apagar o registro
            pass

    db.session.delete(mural_post)
    db.session.commit()
    flash("Postagem do mural excluída com sucesso!", "success")
    return redirect(url_for("mural"))
