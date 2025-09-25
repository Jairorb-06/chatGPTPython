from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from flask_login import login_user, logout_user, login_required, current_user
from openai import OpenAI
import os
from dotenv import load_dotenv

from docx import Document
import fitz  # PyMuPDF
import base64
import markdown
from .. import database 
import time

load_dotenv('config.env')

main = Blueprint('main', __name__)

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

# init database
database.init_database()

print(f"Base de datos ubicada en: {database.DATABASE_PATH}")
print(f"¿Archivo existe?: {os.path.exists(database.DATABASE_PATH)}")

def get_system_message():
    return {"role": "system", "content": "Eres un asistente experto en analizar documentos, imágenes y responder con precisión y profundidad."}

def create_new_conversation(name=None, user_id=None):
    """Crea una nueva conversación para el usuario actual"""
    if not user_id:
        user_id = current_user.id
    
    # Obtener el número de conversaciones del usuario para generar ID único
    existing_conversations = database.get_user_conversations(user_id)
    
    # Generar un ID único que combine user_id y contador
    if existing_conversations:
        # Extraer números de los IDs existentes del usuario y obtener el máximo
        existing_numbers = []
        user_prefix = f"chat_{user_id}_"
        
        for conv_id in existing_conversations.keys():
            if conv_id.startswith(user_prefix):
                try:
                    # Extraer el número después del user_id
                    parts = conv_id.split('_')
                    if len(parts) >= 3:  # chat_userid_number
                        num = int(parts[-1])  # Último elemento es el número
                        existing_numbers.append(num)
                except (IndexError, ValueError):
                    pass
        
        conversation_counter = max(existing_numbers) + 1 if existing_numbers else 1
    else:
        conversation_counter = 1
    
    # Crear ID único por usuario: chat_userid_numero
    conv_id = f"chat_{user_id}_{conversation_counter}"
    
    # Usar el nombre proporcionado o uno por defecto
    conversation_name = name if name else f"Conversación {conversation_counter}"
    
    # Verificar que el ID no exista (doble verificación)
    attempts = 0
    while database.conversation_exists(conv_id, user_id) and attempts < 10:
        conversation_counter += 1
        conv_id = f"chat_{user_id}_{conversation_counter}"
        attempts += 1
    
    if attempts >= 10:
        # Si después de 10 intentos aún hay conflicto, usar timestamp
        import time
        conv_id = f"chat_{user_id}_{int(time.time())}"
    
    # Crear en la base de datos
    database.create_conversation(conv_id, conversation_name, user_id)
    
    return conv_id

def get_current_conversation(user_id=None):
    """Obtiene o crea la conversación actual del usuario"""
    if not user_id:
        user_id = current_user.id
    
    # Obtener conversaciones del usuario
    conversations = database.get_user_conversations(user_id)
    
    # Si no hay conversación en sesión o no existe, crear una nueva
    current_conversation_id = session.get('current_conversation_id')
    
    if not current_conversation_id or current_conversation_id not in conversations:
        current_conversation_id = create_new_conversation(user_id=user_id)
        session['current_conversation_id'] = current_conversation_id
    
    # Cargar mensajes desde la base de datos
    messages = database.get_conversation_messages(current_conversation_id, user_id)
    
    return {
        "id": current_conversation_id,
        "name": conversations.get(current_conversation_id, {}).get('name', 'Conversación'),
        "messages": messages
    }

def read_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

def read_docx(file_path):
    doc = Document(file_path)
    return "\n".join([p.text for p in doc.paragraphs])

def encode_image_to_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
    
def get_full_response(messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, min_length=300):
    full_answer = ""
    continue_prompt = "Por favor continúa desde donde quedaste, sin repetir el texto anterior."

    for _ in range(2):  # máximo 3 llamadas para evitar bucles infinitos
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )

        part = response.choices[0].message.content.strip()
        full_answer += "\n" + part

        # Si ya alcanzamos la longitud mínima, rompemos
        if len(full_answer.split()) >= min_length:
            break

        # Agregar mensaje para que continúe
        messages.append({"role": "assistant", "content": part})
        messages.append({"role": "user", "content": continue_prompt})

    return full_answer.strip()

def render_chat_for_template(history):
    """
    Recibe la lista completa de mensajes (chat_history) y devuelve
    una lista de dicts [{role, content}] listos para el template.
    """
    rendered = []
    for m in history:
        if m.get("role") not in ("user", "assistant"):
            continue

        content = m.get("content", "")

        # Si el contenido viene en formato multimodal (lista con text + image_url)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, dict) and item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if url:
                        # Mostramos la imagen como markdown
                        parts.append(f"![Imagen adjunta]({url})")
            content = "\n\n".join(parts)

        # Convierte markdown a HTML
        html = markdown.markdown(content)
        rendered.append({"role": m["role"], "content": html})
    return rendered

# Rutas de autenticación
@main.route('/login')
def login():
    return render_template('login.html')

@main.route('/auth/google')
def google_login():
    try:
        import urllib.parse
        
        # Parámetros para la autorización de Google
        params = {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'redirect_uri': url_for('main.google_callback', _external=True),
            'scope': 'openid email profile',
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        # Construir URL de autorización
        auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
        print(f"Redirect a: {auth_url}")
        
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Error en Google OAuth: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error de configuración de Google OAuth. Verifica las credenciales.')
        return redirect(url_for('main.login'))

@main.route('/auth/google/callback')
def google_callback():
    try:
        import requests
        
        # Obtener el código de autorización
        code = request.args.get('code')
        if not code:
            print("Error: No se recibió código de autorización")
            flash('Error: No se recibió código de autorización')
            return redirect(url_for('main.login'))
        
        print(f"Código recibido: {code[:20]}...")
        
        # Intercambiar código por token de acceso
        token_data = {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': url_for('main.google_callback', _external=True)
        }
        
        print("=== DEBUG: Intercambiando código por token ===")
        token_response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
        print("Token response status:", token_response.status_code)
        
        if token_response.status_code != 200:
            print("Error en token response:", token_response.text)
            flash('Error al obtener token de acceso')
            return redirect(url_for('main.login'))
        
        token_info = token_response.json()
        access_token = token_info.get('access_token')
        
        if not access_token:
            print("Error: No se pudo obtener access token")
            print("Token info:", token_info)
            flash('Error: No se pudo obtener token de acceso')
            return redirect(url_for('main.login'))
        
        print("Access token obtenido exitosamente")
        
        # Obtener información del usuario
        print("=== DEBUG: Obteniendo información del usuario ===")
        user_response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        print("User response status:", user_response.status_code)
        if user_response.status_code != 200:
            print("Error en user response:", user_response.text)
            flash('Error al obtener información del usuario')
            return redirect(url_for('main.login'))
        
        user_info = user_response.json()
        print("User info:", {k: v for k, v in user_info.items() if k != 'picture'})  # No imprimir la URL de la foto
        
        if user_info and 'id' in user_info:
            # Crear o actualizar usuario
            database.create_user(
                user_id=user_info['id'],
                email=user_info['email'], 
                name=user_info['name'],
                picture=user_info.get('picture')
            )
            
            # Obtener usuario y hacer login
            user = database.get_user(user_info['id'])
            if user:
                login_user(user)
                print("Login exitoso")
                return redirect(url_for('main.index'))
            else:
                print("Error: No se pudo crear/obtener el usuario")
                flash('Error al crear usuario')
                return redirect(url_for('main.login'))
        
        print("Error: Información de usuario incompleta")
        flash('Error: Información de usuario incompleta')
        return redirect(url_for('main.login'))
        
    except Exception as e:
        print(f"Error en callback de Google: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error al autenticar con Google')
        return redirect(url_for('main.login'))

@main.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('main.login'))

# Rutas principales
@main.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'GET':
        current_conv = get_current_conversation()
        conversations = database.get_user_conversations(current_user.id)
        
        return render_template('index.html', 
                             chat=render_chat_for_template(current_conv["messages"]),
                             conversations=conversations,
                             current_id=current_conv["id"],
                             user=current_user)
    
    if request.method == 'POST':
        file = request.files.get("file")
        user_prompt = request.form.get('question')

        if not user_prompt:
            current_conv = get_current_conversation()
            conversations = database.get_user_conversations(current_user.id)
            return render_template('index.html', 
                                 chat=render_chat_for_template(current_conv["messages"]),
                                 conversations=conversations,
                                 current_id=current_conv["id"],
                                 user=current_user,
                                 error="❗ No escribiste ninguna pregunta.")

        temperature = float(request.form.get('temperature', 0.9))
        max_tokens = int(request.form.get('max_tokens', 1000))
        top_p = float(request.form.get('top_p', 1))
        frequency_penalty = float(request.form.get('frequency_penalty', 0))
        presence_penalty = float(request.form.get('presence_penalty', 0.6))

        current_conv = get_current_conversation()
        
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un asistente experto en responder de forma muy detallada y extensa. "
                    "Todas tus respuestas deben tener como mínimo 200 palabras, estructuradas en secciones claras "
                    "con títulos, ejemplos y conclusiones. "
                    "Si la pregunta es corta, amplía el contexto con explicaciones, comparaciones y referencias."
                )   
            }
        ]

        if file and file.filename != "":
            file_ext = file.filename.split(".")[-1].lower()
            filepath = f"./temp/{file.filename}"
            os.makedirs("temp", exist_ok=True)
            file.save(filepath)

            if file_ext == "pdf":
                extracted_text = read_pdf(filepath)
                user_message = f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                database.add_message(current_conv["id"], "user", user_message, current_user.id)
            elif file_ext == "docx":
                extracted_text = read_docx(filepath)
                user_message = f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                database.add_message(current_conv["id"], "user", user_message, current_user.id)
            elif file_ext in ["jpg", "jpeg", "png"]:
                base64_image = encode_image_to_base64(filepath)
                user_message = [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
                database.add_message(current_conv["id"], "user", user_message, current_user.id)
            else:
                database.add_message(current_conv["id"], "user", user_prompt, current_user.id)
        else:
            database.add_message(current_conv["id"], "user", user_prompt, current_user.id)

        # Obtener mensajes actualizados para la llamada a OpenAI
        messages = database.get_conversation_messages(current_conv["id"], current_user.id)
        
        # Llamada a OpenAI usando get_full_response para respuestas más largas
        ai_reply = get_full_response(
            messages=messages[-3:],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            min_length=200  # palabras mínimas
        )
        
        database.add_message(current_conv["id"], "assistant", ai_reply, current_user.id)

        # Recargar conversación actualizada
        current_conv = get_current_conversation()
        conversations = database.get_user_conversations(current_user.id)
        rendered_chat = render_chat_for_template(current_conv["messages"])
        
        return render_template('index.html', 
                             chat=rendered_chat,
                             conversations=conversations,
                             current_id=current_conv["id"],
                             user=current_user)

@main.route('/new_conversation', methods=['POST'])
@login_required
def new_conversation():
    conversation_name = request.json.get('name')
    conv_id = create_new_conversation(conversation_name, current_user.id)
    session['current_conversation_id'] = conv_id
    return jsonify({"success": True, "conversation_id": conv_id})

@main.route('/switch_conversation', methods=['POST'])
@login_required
def switch_conversation():
    conv_id = request.json.get('conversation_id')
    print(f"Intentando cambiar a conversación: {conv_id}")
    
    if database.conversation_exists(conv_id, current_user.id):
        session['current_conversation_id'] = conv_id
        print(f"Conversación cambiada exitosamente a: {conv_id}")
        return jsonify({"success": True})
    
    print(f"Conversación {conv_id} no encontrada")
    return jsonify({"success": False})

@main.route('/delete_conversation', methods=['POST'])
@login_required
def delete_conversation():
    conv_id = request.json.get('conversation_id')
    
    if database.conversation_exists(conv_id, current_user.id) and database.get_user_conversation_count(current_user.id) > 1:
        # Eliminar de BD
        database.delete_conversation(conv_id, current_user.id)
        
        # Si eliminamos la conversación actual, limpiar sesión
        if session.get('current_conversation_id') == conv_id:
            session.pop('current_conversation_id', None)
        
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "No se puede eliminar la última conversación"})

@main.route('/audio', methods=['POST'])
@login_required
def handle_audio():
    try:
        audio_file = request.files.get('audio')
        if not audio_file:
            return jsonify({"error": "No se recibió archivo de audio"}), 400
        
        # Guardar el archivo de audio temporalmente
        audio_path = f"./temp/audio_{int(time.time())}.wav"
        os.makedirs("temp", exist_ok=True)
        audio_file.save(audio_path)
        
        # Transcribir el audio usando Whisper de OpenAI
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        user_prompt = transcription.text
        
        # Eliminar archivo temporal
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        if not user_prompt.strip():
            current_conv = get_current_conversation()
            conversations = database.get_user_conversations(current_user.id)
            return render_template('index.html', 
                                 chat=render_chat_for_template(current_conv["messages"]),
                                 conversations=conversations,
                                 current_id=current_conv["id"],
                                 user=current_user,
                                 error="❗ No se pudo transcribir el audio.")
        
        # Usar parámetros por defecto para la respuesta por voz
        temperature = 0.7
        max_tokens = 1500
        top_p = 1
        frequency_penalty = 0.2
        presence_penalty = 0.8
        
        current_conv = get_current_conversation()
        
        # Agregar mensaje del usuario
        database.add_message(current_conv["id"], "user", user_prompt, current_user.id)
        
        # Obtener mensajes actualizados
        messages = database.get_conversation_messages(current_conv["id"], current_user.id)
        
        # Obtener respuesta de OpenAI
        ai_reply = get_full_response(
            messages=messages[-3:],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            min_length=200
        )
        
        # Agregar respuesta del asistente
        database.add_message(current_conv["id"], "assistant", ai_reply, current_user.id)
        
        # Recargar conversación actualizada
        current_conv = get_current_conversation()
        conversations = database.get_user_conversations(current_user.id)
        rendered_chat = render_chat_for_template(current_conv["messages"])
        
        return render_template('index.html', 
                             chat=rendered_chat,
                             conversations=conversations,
                             current_id=current_conv["id"],
                             user=current_user)
                             
    except Exception as e:
        print(f"Error procesando audio: {str(e)}")
        current_conv = get_current_conversation()
        conversations = database.get_user_conversations(current_user.id)
        return render_template('index.html', 
                             chat=render_chat_for_template(current_conv["messages"]),
                             conversations=conversations,
                             current_id=current_conv["id"],
                             user=current_user,
                             error="❗ Error procesando el audio.")