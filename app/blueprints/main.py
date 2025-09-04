from flask import Blueprint, render_template, request, jsonify
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

# Cargar conversaciones desde la base de datos al iniciar
conversations = database.get_all_conversations()
current_conversation_id = None
# conversation_counter = database.get_conversation_count() + 1
existing_conversations = database.get_all_conversations()
if existing_conversations:
    # Extraer números de los IDs existentes y obtener el máximo
    existing_numbers = []
    for conv_id in existing_conversations.keys():
        if conv_id.startswith('chat_'):
            try:
                num = int(conv_id.split('_')[1])
                existing_numbers.append(num)
            except (IndexError, ValueError):
                pass
    conversation_counter = max(existing_numbers) + 1 if existing_numbers else 1
else:
    conversation_counter = 1

def get_system_message():
    return {"role": "system", "content": "Eres un asistente experto en analizar documentos, imágenes y responder con precisión y profundidad."}

def create_new_conversation(name=None):
    global conversation_counter, current_conversation_id
    conv_id = f"chat_{conversation_counter}"
    
    # Usar el nombre proporcionado o uno por defecto
    conversation_name = name if name else f"Conversación {conversation_counter}"
    
    # Crear en la base de datos
    database.create_conversation(conv_id, conversation_name)
    
    # Actualizar el diccionario local
    conversations[conv_id] = {
        "name": conversation_name,
        "messages": [get_system_message()]
    }
    current_conversation_id = conv_id
    conversation_counter += 1
    return conv_id


def get_current_conversation():
    global current_conversation_id
    if current_conversation_id is None or current_conversation_id not in conversations:
        create_new_conversation()
    
    # Cargar mensajes desde la base de datos
    messages = database.get_conversation_messages(current_conversation_id)
    conversations[current_conversation_id]["messages"] = messages
    
    return conversations[current_conversation_id]

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

@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        current_conv = get_current_conversation()
        return render_template('index.html', 
                             chat=render_chat_for_template(current_conv["messages"]),
                             conversations=conversations,
                             current_id=current_conversation_id)
    
    if request.method == 'POST':
        file = request.files.get("file")
        user_prompt = request.form.get('question')

        if not user_prompt:
            current_conv = get_current_conversation()
            return render_template('index.html', 
                                 chat=render_chat_for_template(current_conv["messages"]),
                                 conversations=conversations,
                                 current_id=current_conversation_id,
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
                current_conv["messages"].append({"role": "user", "content": user_message})
                # Guardar en BD
                database.add_message(current_conversation_id, "user", user_message)
            elif file_ext == "docx":
                extracted_text = read_docx(filepath)
                user_message = f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                current_conv["messages"].append({"role": "user", "content": user_message})
                # Guardar en BD
                database.add_message(current_conversation_id, "user", user_message)
            elif file_ext in ["jpg", "jpeg", "png"]:
                base64_image = encode_image_to_base64(filepath)
                user_message = [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
                current_conv["messages"].append({"role": "user", "content": user_message})
                # Guardar en BD
                database.add_message(current_conversation_id, "user", user_message)
            else:
                current_conv["messages"].append({"role": "user", "content": user_prompt})
                # Guardar en BD
                database.add_message(current_conversation_id, "user", user_prompt)
        else:
            current_conv["messages"].append({"role": "user", "content": user_prompt})
            # Guardar en BD
            database.add_message(current_conversation_id, "user", user_prompt)

        # Llamada a OpenAI usando get_full_response para respuestas más largas
        ai_reply = get_full_response(
            messages=current_conv["messages"][-3:],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            min_length=200  # palabras mínimas
        )
        
        current_conv["messages"].append({"role": "assistant", "content": ai_reply})
        # Guardar en BD
        database.add_message(current_conversation_id, "assistant", ai_reply)

        rendered_chat = render_chat_for_template(current_conv["messages"])
        return render_template('index.html', 
                             chat=rendered_chat,
                             conversations=conversations,
                             current_id=current_conversation_id)

@main.route('/new_conversation', methods=['POST'])
def new_conversation():
    conversation_name = request.json.get('name')
    conv_id = create_new_conversation(conversation_name)
    return jsonify({"success": True, "conversation_id": conv_id})

@main.route('/switch_conversation', methods=['POST'])
def switch_conversation():
    global current_conversation_id, conversations
    conv_id = request.json.get('conversation_id')
    print(f"Intentando cambiar a conversación: {conv_id}")
    
    # Recargar conversaciones desde BD
    conversations = database.get_all_conversations()
    print(f"Conversaciones disponibles: {list(conversations.keys())}")
    
    if database.conversation_exists(conv_id):
        current_conversation_id = conv_id
        print(f"Conversación cambiada exitosamente a: {current_conversation_id}")
        return jsonify({"success": True})
    
    print(f"Conversación {conv_id} no encontrada")
    return jsonify({"success": False})

@main.route('/delete_conversation', methods=['POST'])
def delete_conversation():
    global current_conversation_id, conversations
    conv_id = request.json.get('conversation_id')
    
    if database.conversation_exists(conv_id) and database.get_conversation_count() > 1:
        # Eliminar de BD
        database.delete_conversation(conv_id)
        
        # Recargar conversaciones
        conversations = database.get_all_conversations()
        
        # Si eliminamos la conversación actual, cambiamos a otra
        if current_conversation_id == conv_id:
            current_conversation_id = list(conversations.keys())[0]
        
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "No se puede eliminar la última conversación"})

@main.route('/audio', methods=['POST'])
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
            return render_template('index.html', 
                                 chat=render_chat_for_template(current_conv["messages"]),
                                 conversations=conversations,
                                 current_id=current_conversation_id,
                                 error="❗ No se pudo transcribir el audio.")
        
        # Usar parámetros por defecto para la respuesta por voz
        temperature = 0.7
        max_tokens = 1500
        top_p = 1
        frequency_penalty = 0.2
        presence_penalty = 0.8
        
        current_conv = get_current_conversation()
        
        # Agregar mensaje del usuario
        current_conv["messages"].append({"role": "user", "content": user_prompt})
        database.add_message(current_conversation_id, "user", user_prompt)
        
        # Obtener respuesta de OpenAI
        ai_reply = get_full_response(
            messages=current_conv["messages"][-3:],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            min_length=200
        )
        
        # Agregar respuesta del asistente
        current_conv["messages"].append({"role": "assistant", "content": ai_reply})
        database.add_message(current_conversation_id, "assistant", ai_reply)
        
        rendered_chat = render_chat_for_template(current_conv["messages"])
        return render_template('index.html', 
                             chat=rendered_chat,
                             conversations=conversations,
                             current_id=current_conversation_id)
                             
    except Exception as e:
        print(f"Error procesando audio: {str(e)}")
        current_conv = get_current_conversation()
        return render_template('index.html', 
                             chat=render_chat_for_template(current_conv["messages"]),
                             conversations=conversations,
                             current_id=current_conversation_id,
                             error="❗ Error procesando el audio.")