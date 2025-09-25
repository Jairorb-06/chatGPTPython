#!/usr/bin/env python3
"""
Script para migrar la base de datos a la nueva estructura con usuarios
"""

import sqlite3
import os
import json
from datetime import datetime

# Obtener la ruta de la base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'chat_conversations.db')

def backup_database():
    """Crear una copia de seguridad de la base de datos"""
    backup_path = DATABASE_PATH.replace('.db', '_backup.db')
    
    if os.path.exists(DATABASE_PATH):
        import shutil
        shutil.copy2(DATABASE_PATH, backup_path)
        print(f"✅ Backup creado en: {backup_path}")
        return True
    return False

def migrate_database():
    """Migrar la base de datos a la nueva estructura"""
    
    print("🔄 Iniciando migración de base de datos...")
    
    # Crear backup
    backup_created = backup_database()
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. Crear tabla de usuarios si no existe
        print("📝 Creando tabla de usuarios...")
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
        
        # 2. Verificar si la columna user_id ya existe
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in columns:
            print("➕ Agregando columna user_id a conversations...")
            
            # Crear un usuario por defecto para conversaciones existentes
            default_user_id = "default_user_migration"
            cursor.execute('''
                INSERT OR IGNORE INTO users (id, email, name, picture) 
                VALUES (?, ?, ?, ?)
            ''', (default_user_id, 'usuario@migracion.com', 'Usuario Migración', None))
            
            # Agregar la columna user_id
            cursor.execute('ALTER TABLE conversations ADD COLUMN user_id TEXT')
            
            # Actualizar todas las conversaciones existentes para usar el usuario por defecto
            cursor.execute('UPDATE conversations SET user_id = ? WHERE user_id IS NULL', (default_user_id,))
            
            print("✅ Columna user_id agregada exitosamente")
        else:
            print("ℹ️  Columna user_id ya existe")
        
        # 3. Crear nueva tabla de conversaciones con la estructura correcta si es necesario
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations_new (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Verificar si necesitamos migrar datos
        cursor.execute("SELECT COUNT(*) FROM conversations_new")
        new_table_count = cursor.fetchone()[0]
        
        if new_table_count == 0:
            print("📦 Migrando datos a la nueva tabla...")
            cursor.execute('''
                INSERT INTO conversations_new (id, user_id, name, created_at, updated_at)
                SELECT id, user_id, name, created_at, updated_at FROM conversations
            ''')
            
            # Eliminar tabla vieja y renombrar la nueva
            cursor.execute('DROP TABLE conversations')
            cursor.execute('ALTER TABLE conversations_new RENAME TO conversations')
            print("✅ Migración de datos completada")
        else:
            cursor.execute('DROP TABLE conversations_new')
            print("ℹ️  Datos ya migrados")
        
        # 4. Crear tabla de mensajes si no existe (debería existir)
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
        print("✅ Migración completada exitosamente")
        
        # Mostrar estadísticas
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM conversations")
        conversations_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        messages_count = cursor.fetchone()[0]
        
        print(f"\n📊 Estadísticas de la base de datos:")
        print(f"   👥 Usuarios: {users_count}")
        print(f"   💬 Conversaciones: {conversations_count}")
        print(f"   💭 Mensajes: {messages_count}")
        
    except Exception as e:
        print(f"❌ Error durante la migración: {str(e)}")
        conn.rollback()
        
        if backup_created:
            print("🔄 Puedes restaurar desde el backup si es necesario")
        
        raise
    finally:
        conn.close()

def verify_migration():
    """Verificar que la migración fue exitosa"""
    print("\n🔍 Verificando migración...")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Verificar estructura de las tablas
        cursor.execute("PRAGMA table_info(users)")
        users_columns = [column[1] for column in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(conversations)")
        conversations_columns = [column[1] for column in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(messages)")
        messages_columns = [column[1] for column in cursor.fetchall()]
        
        required_users_columns = ['id', 'email', 'name', 'picture', 'created_at', 'last_login']
        required_conversations_columns = ['id', 'user_id', 'name', 'created_at', 'updated_at']
        required_messages_columns = ['id', 'conversation_id', 'role', 'content', 'created_at']
        
        # Verificar columnas
        users_ok = all(col in users_columns for col in required_users_columns)
        conversations_ok = all(col in conversations_columns for col in required_conversations_columns)
        messages_ok = all(col in messages_columns for col in required_messages_columns)
        
        if users_ok and conversations_ok and messages_ok:
            print("✅ Verificación exitosa - Todas las tablas tienen la estructura correcta")
            return True
        else:
            print("❌ Verificación fallida - Faltan columnas:")
            if not users_ok:
                missing = set(required_users_columns) - set(users_columns)
                print(f"   Tabla users: faltan {missing}")
            if not conversations_ok:
                missing = set(required_conversations_columns) - set(conversations_columns)
                print(f"   Tabla conversations: faltan {missing}")
            if not messages_ok:
                missing = set(required_messages_columns) - set(messages_columns)
                print(f"   Tabla messages: faltan {missing}")
            return False
            
    except Exception as e:
        print(f"❌ Error durante la verificación: {str(e)}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Script de migración de base de datos")
    print("=====================================\n")
    
    if not os.path.exists(DATABASE_PATH):
        print(f"❌ No se encontró la base de datos en: {DATABASE_PATH}")
        print("La base de datos se creará automáticamente cuando ejecutes la aplicación.")
        exit(1)
    
    try:
        migrate_database()
        if verify_migration():
            print("\n🎉 ¡Migración completada exitosamente!")
            print("Ya puedes ejecutar tu aplicación Flask.")
        else:
            print("\n❌ La migración no se completó correctamente.")
            
    except Exception as e:
        print(f"\n💥 Error fatal durante la migración: {str(e)}")
        print("Por favor revisa el error y vuelve a intentar.")