from flask import Blueprint, redirect, url_for, session, request
from flask_login import login_user, logout_user, login_required
from authlib.integrations.flask_client import OAuth
import os
from ..models import User
from .. import database

auth_bp = Blueprint('auth', __name__)

def init_oauth(app):
    """Inicializa OAuth con la configuración de Google"""
    oauth = OAuth(app)
    
    google = oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    
    return oauth, google

@auth_bp.route('/login')
def login():
    """Inicia el flujo de autenticación con Google"""
    from .. import oauth, google
    
    redirect_uri = url_for('auth.callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def callback():
    """Callback de Google OAuth"""
    from .. import oauth, google
    
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if user_info:
            # Crear o actualizar usuario
            user = User.create_or_update(
                user_id=user_info['sub'],
                email=user_info['email'],
                name=user_info['name'],
                picture=user_info.get('picture')
            )
            
            # Iniciar sesión
            login_user(user)
            
            # Redirigir a la página principal
            return redirect(url_for('main.index'))
        else:
            return redirect(url_for('auth.login'))
            
    except Exception as e:
        print(f"Error en callback de OAuth: {str(e)}")
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
@login_required
def logout():
    """Cerrar sesión del usuario"""
    logout_user()
    return redirect(url_for('auth.login'))