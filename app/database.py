import sqlite3
import json
import os
from datetime import datetime

# Obtener la ruta del directorio raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, 'chat_conversations.db')

def init_database():
    """Inicializa la base de datos y crea las tablas necesarias"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Tabla para conversaciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla para mensajes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def create_conversation(conv_id, name):
    """Crea una nueva conversación"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO conversations (id, name) VALUES (?, ?)',
        (conv_id, name)
    )
    
    # Agregar mensaje del sistema
    cursor.execute(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conv_id, 'system', 'Eres un asistente experto en analizar documentos, imágenes y responder con precisión y profundidad.')
    )
    
    conn.commit()
    conn.close()

def get_all_conversations():
    """Obtiene todas las conversaciones"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, name FROM conversations ORDER BY updated_at DESC')
    conversations = {}
    
    for row in cursor.fetchall():
        conv_id, name = row
        conversations[conv_id] = {'name': name}
    
    conn.close()
    return conversations

def get_conversation_messages(conv_id):
    """Obtiene todos los mensajes de una conversación"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC',
        (conv_id,)
    )
    
    messages = []
    for row in cursor.fetchall():
        role, content = row
        # Intentar parsear content como JSON (para mensajes multimodales)
        try:
            parsed_content = json.loads(content)
            messages.append({'role': role, 'content': parsed_content})
        except json.JSONDecodeError:
            messages.append({'role': role, 'content': content})
    
    conn.close()
    return messages

def add_message(conv_id, role, content):
    """Agrega un mensaje a una conversación"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Si el content es una lista (multimodal), convertir a JSON
    if isinstance(content, list):
        content_str = json.dumps(content)
    else:
        content_str = content
    
    cursor.execute(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conv_id, role, content_str)
    )
    
    # Actualizar timestamp de la conversación
    cursor.execute(
        'UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (conv_id,)
    )
    
    conn.commit()
    conn.close()

def delete_conversation(conv_id):
    """Elimina una conversación y todos sus mensajes"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))
    conn.commit()
    conn.close()

def conversation_exists(conv_id):
    """Verifica si existe una conversación"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM conversations WHERE id = ?', (conv_id,))
    exists = cursor.fetchone()[0] > 0
    
    conn.close()
    return exists

def get_conversation_count():
    """Obtiene el número total de conversaciones"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM conversations')
    count = cursor.fetchone()[0]
    
    conn.close()
    return count