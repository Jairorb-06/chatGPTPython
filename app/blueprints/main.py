from flask import Blueprint, render_template, request
from openai import OpenAI

import os
from dotenv import load_dotenv

from docx import Document
import fitz  # PyMuPDF
import base64

load_dotenv('config.env')

main = Blueprint('main', __name__)

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

conversations = []
chat_history = [
    {"role": "system", "content": "Eres un asistente experto en analizar documentos, imágenes y responder con precisión y profundidad."}
]


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

@main.route('/', methods=['GET', 'POST'])

def index():
    if request.method == 'GET':
        return render_template('index.html')
    
    if request.method == 'POST':
        file = request.files.get("file")
        user_prompt = request.form.get('question')

        if not user_prompt:
            return render_template('index.html', chat=["❗ No escribiste ninguna pregunta."])

        temperature = float(request.form.get('temperature', 0.9))
        max_tokens = int(request.form.get('max_tokens', 3000))
        top_p = float(request.form.get('top_p', 1))
        frequency_penalty = float(request.form.get('frequency_penalty', 0))
        presence_penalty = float(request.form.get('presence_penalty', 0.6))

        messages = [
            {
                "role": "system",
                # "content": "Eres un asistente experto en analizar documentos, imágenes y responder de forma precisa y detallada."
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
                chat_history.append({
                    "role": "user",
                    "content": f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                })
            elif file_ext == "docx":
                extracted_text = read_docx(filepath)
                chat_history.append({
                    "role": "user",
                    "content": f"{user_prompt}\n\nContenido del documento:\n{extracted_text}"
                })
            elif file_ext in ["jpg", "jpeg", "png"]:
                base64_image = encode_image_to_base64(filepath)
                chat_history.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                })
            else:
                chat_history.append({"role": "user", "content": user_prompt})
        else:
            chat_history.append({"role": "user", "content": user_prompt})

        # Llamada a OpenAI
        response = client.chat.completions.create(
            model='gpt-4o',
            # messages=chat_history,
            messages=chat_history[-3:],  # últimos 3 mensajes
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )

        ai_reply = response.choices[0].message.content.strip()
        chat_history.append({"role": "assistant", "content": ai_reply})

        conversations.append("Tú: " + user_prompt)
        conversations.append("AI: " + ai_reply)

        return render_template('index.html', chat=conversations)

    # Si no es GET ni POST válido:
    return render_template('index.html')