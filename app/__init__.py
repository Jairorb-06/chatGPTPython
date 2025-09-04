from flask import Flask
import os
from dotenv import load_dotenv

def create_app():
    load_dotenv('config.env')

    app= Flask(__name__)

    app.secret_key = os.getenv('SECRET_KEY', 'tu_clave_secreta_por_defecto_12345')

    from app.blueprints.main import main
    app.register_blueprint(main)

    return app