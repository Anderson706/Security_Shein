from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, generate_csrf

app = Flask(__name__)

app.config['SECRET_KEY'] = '07abe10a5f998c5cd99bcc482244bf03'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///comunidade.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

database = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login_conta'
login_manager.login_message_category = 'alert-danger'

csrf = CSRFProtect(app)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

@app.context_processor
def inject_has_endpoint():
    def has_endpoint(name: str) -> bool:
        return name in app.view_functions
    return dict(has_endpoint=has_endpoint)

# ✅ IMPORTA ROTAS NO FINAL (evita circular import)
from Security_Leroy import routers
