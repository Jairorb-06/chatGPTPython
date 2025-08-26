from flask import Blueprint, render_template, request, jsonify
from openai import OpenAI

import os
from dotenv import load_dotenv

from docx import Document
import fitz  # PyMuPDF
import base64
import markdown

load_dotenv('config.env')

main = Blueprint('main', __name__)

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

# Diccionario para guardar todas las conversaciones
conversations = {}
current_conversation_id = None
conversation_counter = 1

def get_system_message():
    return {"role": "system", "content": "Eres un asistente experto en analizar documentos, imágenes y responder con precisión y profundidad."}

def create_new_conversation():
    global conversation_counter, current_conversation_id
    conv_id = f"chat_{conversation_counter}"
    conversations[conv_id] = {
        "name": f"Conversación {conversation_counter}",
        "messages": [get_system_message()]
    }
    current_conversation_id = conv_id
    conversation_counter += 1
    return conv_id

def get_current_conversation():
    global current_conversation_id
    if current_conversation_id is None or current_conversation_id not in conversations:
        create_new_conversation()
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
    
def get_full_response(messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, min_length=500):
    full_answer = ""
    continue_prompt = "Por favor continúa desde donde quedaste, sin repetir el texto anterior."

    for _ in range(3):  # máximo 3 llamadas para evitar bucles infinitos
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
        max_tokens = int(request.form.get('max_tokens', 3000))
        top_p = float(request.form.get('top_p', 1))
        frequency_penalty = float(request.form.get('frequency_penalty', 0))
        presence_penalty = float(request.form.get('presence_penalty', 0.6))

        current_conv = get_current_conversation()
        
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un asistente experto en responder de forma muy detallada y extensa. "
                    "Todas tus respuestas deben tener como mínimo 500 palabras, estructuradas en secciones claras "
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
                current_conv["messages"].append({
                    "role": "user",
                    "content": f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                })
            elif file_ext == "docx":
                extracted_text = read_docx(filepath)
                current_conv["messages"].append({
                    "role": "user",
                    "content": f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                })
            elif file_ext in ["jpg", "jpeg", "png"]:
                base64_image = encode_image_to_base64(filepath)
                current_conv["messages"].append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                })
            else:
                current_conv["messages"].append({"role": "user", "content": user_prompt})
        else:
            current_conv["messages"].append({"role": "user", "content": user_prompt})

        # Llamada a OpenAI usando get_full_response para respuestas más largas
        ai_reply = get_full_response(
            messages=current_conv["messages"][-3:],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            min_length=500  # palabras mínimas
        )
        
        current_conv["messages"].append({"role": "assistant", "content": ai_reply})

        rendered_chat = render_chat_for_template(current_conv["messages"])
        return render_template('index.html', 
                             chat=rendered_chat,
                             conversations=conversations,
                             current_id=current_conversation_id)

@main.route('/new_conversation', methods=['POST'])
def new_conversation():
    create_new_conversation()
    return jsonify({"success": True, "conversation_id": current_conversation_id})

@main.route('/switch_conversation', methods=['POST'])
def switch_conversation():
    global current_conversation_id
    conv_id = request.json.get('conversation_id')
    print(f"Intentando cambiar a conversación: {conv_id}")
    print(f"Conversaciones disponibles: {list(conversations.keys())}")
    
    if conv_id in conversations:
        current_conversation_id = conv_id
        print(f"Conversación cambiada exitosamente a: {current_conversation_id}")
        return jsonify({"success": True})
    
    print(f"Conversación {conv_id} no encontrada")
    return jsonify({"success": False})

@main.route('/delete_conversation', methods=['POST'])
def delete_conversation():
    global current_conversation_id
    conv_id = request.json.get('conversation_id')
    
    if conv_id in conversations and len(conversations) > 1:
        del conversations[conv_id]
        
        # Si eliminamos la conversación actual, cambiamos a otra
        if current_conversation_id == conv_id:
            current_conversation_id = list(conversations.keys())[0]
        
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "No se puede eliminar la última conversación"})