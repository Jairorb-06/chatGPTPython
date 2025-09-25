import sqlite3
import json
import os
from datetime import datetime
from .models import User

# Obtener la ruta del directorio raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, 'chat_conversations.db')

def init_database():
    """Inicializa la base de datos y crea las tablas necesarias"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Tabla para usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            picture TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla para conversaciones (ahora con user_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
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

# Funciones para usuarios
def create_user(user_id, email, name, picture=None):
    """Crea un nuevo usuario"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            'INSERT INTO users (id, email, name, picture) VALUES (?, ?, ?, ?)',
            (user_id, email, name, picture)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Usuario ya existe, actualizar información
        cursor.execute(
            'UPDATE users SET name = ?, picture = ?, last_login = CURRENT_TIMESTAMP WHERE id = ?',
            (name, picture, user_id)
        )
        conn.commit()
    
    conn.close()

def get_user(user_id):
    """Obtiene un usuario por ID"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, email, name, picture FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    
    conn.close()
    
    if row:
        return User(row[0], row[1], row[2], row[3])
    return None

def get_user_by_email(email):
    """Obtiene un usuario por email"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, email, name, picture FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    conn.close()
    
    if row:
        return User(row[0], row[1], row[2], row[3])
    return None

# Funciones para conversaciones (modificadas para incluir user_id)
def create_conversation(conv_id, name, user_id):
    """Crea una nueva conversación para un usuario específico"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO conversations (id, user_id, name) VALUES (?, ?, ?)',
        (conv_id, user_id, name)
    )
    
    # Agregar mensaje del sistema
    cursor.execute(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conv_id, 'system', 'Eres un asistente experto en analizar documentos, imágenes y responder con precisión y profundidad.')
    )
    
    conn.commit()
    conn.close()

def get_user_conversations(user_id):
    """Obtiene todas las conversaciones de un usuario específico"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT id, name FROM conversations WHERE user_id = ? ORDER BY updated_at DESC',
        (user_id,)
    )
    conversations = {}
    
    for row in cursor.fetchall():
        conv_id, name = row
        conversations[conv_id] = {'name': name}
    
    conn.close()
    return conversations

def get_conversation_messages(conv_id, user_id):
    """Obtiene todos los mensajes de una conversación (verificando que pertenezca al usuario)"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Verificar que la conversación pertenece al usuario
    cursor.execute(
        'SELECT COUNT(*) FROM conversations WHERE id = ? AND user_id = ?',
        (conv_id, user_id)
    )
    
    if cursor.fetchone()[0] == 0:
        conn.close()
        return []
    
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

def add_message(conv_id, role, content, user_id):
    """Agrega un mensaje a una conversación (verificando que pertenezca al usuario)"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Verificar que la conversación pertenece al usuario
    cursor.execute(
        'SELECT COUNT(*) FROM conversations WHERE id = ? AND user_id = ?',
        (conv_id, user_id)
    )
    
    if cursor.fetchone()[0] == 0:
        conn.close()
        return False
    
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
        'UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
        (conv_id, user_id)
    )
    
    conn.commit()
    conn.close()
    return True

def delete_conversation(conv_id, user_id):
    """Elimina una conversación del usuario"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        'DELETE FROM conversations WHERE id = ? AND user_id = ?',
        (conv_id, user_id)
    )
    
    conn.commit()
    conn.close()

def conversation_exists(conv_id, user_id=None):
    """Verifica si existe una conversación"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute(
            'SELECT COUNT(*) FROM conversations WHERE id = ? AND user_id = ?', 
            (conv_id, user_id)
        )
    else:
        cursor.execute('SELECT COUNT(*) FROM conversations WHERE id = ?', (conv_id,))
    
    exists = cursor.fetchone()[0] > 0
    
    conn.close()
    return exists

def get_user_conversation_count(user_id):
    """Obtiene el número total de conversaciones de un usuario"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM conversations WHERE user_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    
    conn.close()
    return count

# Mantener funciones antiguas para compatibilidad (pero ahora vacías o con comportamiento por defecto)
def get_all_conversations():
    """Función deprecated - usar get_user_conversations en su lugar"""
    return {}

def get_conversation_count():
    """Función deprecated - usar get_user_conversation_count en su lugar"""
    return 0