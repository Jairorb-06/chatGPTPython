from flask import Blueprint, render_template, request
from openai import OpenAI

import os
from dotenv import load_dotenv

load_dotenv('config.env')

main = Blueprint('main', __name__)

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

conversations = []

@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('index.html')
    
    if request.form['question']:
        question = 'YO: ' + request.form['question']
        
        # Obtener parámetros del formulario
        temperature = float(request.form.get('temperature', 0.9))
        max_tokens = int(request.form.get('max_tokens', 50))
        top_p = float(request.form.get('top_p', 1))
        frequency_penalty = float(request.form.get('frequency_penalty', 0))
        presence_penalty = float(request.form.get('presence_penalty', 0.6))

        # OpenAI v1.0+
        response = client.chat.completions.create(
            model='gpt-4-turbo', 
            messages=[
                {"role": "user", "content": question}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,  
        )

        answer = 'AI: ' + response.choices[0].message.content.strip()

        conversations.append(question)
        conversations.append(answer)

        return render_template('index.html', chat=conversations)
    
    else:
        return render_template('index.html')