from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib
import secrets
from datetime import datetime

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ БАЗА ДАННЫХ (SQLite) ============
def get_db():
    conn = sqlite3.connect('mail.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Создаём таблицы
conn = get_db()
conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        username TEXT,
        password TEXT,
        created_at TEXT
    )
''')
conn.execute('''
    CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        subject TEXT,
        content TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    )
''')
conn.commit()
conn.close()

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ============ API АУТЕНТИФИКАЦИИ ============
@app.post("/api/register")
def register(email: str, username: str, password: str):
    conn = get_db()
    
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        return {"success": False, "error": "Email already exists"}
    
    hashed = hash_password(password)
    conn.execute(
        "INSERT INTO users (email, username, password, created_at) VALUES (?, ?, ?, ?)",
        (email, username, hashed, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    token = secrets.token_hex(32)
    return {
        "success": True,
        "access_token": token,
        "user": {"email": email, "username": username}
    }

@app.post("/api/login")
def login(email: str, password: str):
    conn = get_db()
    hashed = hash_password(password)
    
    user = conn.execute(
        "SELECT id, email, username FROM users WHERE email = ? AND password = ?",
        (email, hashed)
    ).fetchone()
    conn.close()
    
    if not user:
        return {"success": False, "error": "Invalid credentials"}
    
    token = secrets.token_hex(32)
    return {
        "success": True,
        "access_token": token,
        "user": {"id": user[0], "email": user[1], "username": user[2]}
    }

# ============ API ПИСЕМ ============
@app.post("/api/send")
def send_email(to: str, subject: str, body: str, from_email: str = "user@test.com"):
    conn = get_db()
    conn.execute(
        "INSERT INTO emails (sender, recipient, subject, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (from_email, to, subject, body, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Email sent"}

@app.get("/api/inbox")
def get_inbox():
    conn = get_db()
    emails = conn.execute(
        "SELECT id, sender, subject, content, is_read, created_at FROM emails ORDER BY id DESC"
    ).fetchall()
    conn.close()
    
    result = []
    for row in emails:
        result.append({
            "id": row[0],
            "sender_email": row[1],
            "sender_name": row[1].split('@')[0] if '@' in row[1] else row[1],
            "subject": row[2] or "",
            "body_preview": (row[3] or "")[:100],
            "is_read": bool(row[4]),
            "sent_at": row[5]
        })
    return result

@app.get("/api/email/{email_id}")
def get_email(email_id: int):
    conn = get_db()
    conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (email_id,))
    conn.commit()
    
    email = conn.execute(
        "SELECT id, sender, recipient, subject, content, created_at FROM emails WHERE id = ?",
        (email_id,)
    ).fetchone()
    conn.close()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    return {
        "id": email[0],
        "sender_email": email[1],
        "sender_name": email[1].split('@')[0] if '@' in email[1] else email[1],
        "recipient_email": email[2],
        "subject": email[3] or "",
        "body": email[4] or "",
        "is_read": True,
        "sent_at": email[5]
    }

# ============ ЗАПУСК ============
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("✅ MAIL SYSTEM RUNNING")
    print("📧 http://localhost:8000")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
