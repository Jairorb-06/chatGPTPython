from flask import Flask
from flask_login import LoginManager
import os
from dotenv import load_dotenv

# Instancia global de login manager
login_manager = LoginManager()

def create_app():
    load_dotenv('config.env')

    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY', 'tu_clave_secreta_por_defecto_12345')

    # Configurar Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.database import get_user
        return get_user(user_id)

    # Registrar blueprints
    from app.blueprints.main import main
    app.register_blueprint(main)

    return app