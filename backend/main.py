from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib
import secrets
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# База данных
conn = sqlite3.connect('mail.db', check_same_thread=False)

conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        username TEXT,
        password TEXT
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

@app.post("/api/register")
def register(data: dict):
    email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    hashed = hashlib.sha256(password.encode()).hexdigest()
    
    try:
        conn.execute("INSERT INTO users (email, username, password) VALUES (?, ?, ?)",
                    (email, username, hashed))
        conn.commit()
        token = secrets.token_hex(32)
        return {"success": True, "access_token": token, "user": {"email": email, "username": username}}
    except:
        return {"success": False, "error": "Email already exists"}

@app.post("/api/login")
def login(data: dict):
    email = data.get('email')
    password = data.get('password')
    hashed = hashlib.sha256(password.encode()).hexdigest()
    
    cursor = conn.execute("SELECT email, username FROM users WHERE email = ? AND password = ?",
                         (email, hashed))
    user = cursor.fetchone()
    
    if user:
        token = secrets.token_hex(32)
        return {"success": True, "access_token": token, "user": {"email": user[0], "username": user[1]}}
    return {"success": False, "error": "Invalid credentials"}

@app.post("/api/send")
def send_email(data: dict):
    to_email = data.get('to')
    subject = data.get('subject', 'No subject')
    body = data.get('body', '')
    from_email = data.get('from', 'user')
    
    conn.execute(
        "INSERT INTO emails (sender, recipient, subject, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (from_email, to_email, subject, body, datetime.now().isoformat())
    )
    conn.commit()
    return {"success": True, "message": "Email sent"}

@app.get("/api/inbox")
def get_inbox():
    cursor = conn.execute("SELECT id, sender, subject, content, is_read, created_at FROM emails ORDER BY id DESC")
    emails = []
    for row in cursor.fetchall():
        emails.append({
            "id": row[0],
            "sender_email": row[1],
            "sender_name": row[1].split('@')[0] if '@' in row[1] else row[1],
            "subject": row[2] or "",
            "body_preview": (row[3] or "")[:100],
            "is_read": bool(row[4]),
            "sent_at": row[5]
        })
    return emails

@app.get("/api/email/{email_id}")
def get_email(email_id: int):
    conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (email_id,))
    conn.commit()
    
    cursor = conn.execute("SELECT id, sender, recipient, subject, content, created_at FROM emails WHERE id = ?", (email_id,))
    row = cursor.fetchone()
    
    if row:
        return {
            "id": row[0],
            "sender_email": row[1],
            "recipient_email": row[2],
            "subject": row[3] or "",
            "body": row[4] or "",
            "is_read": True,
            "sent_at": row[5]
        }
    return {"error": "Not found"}

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("✅ SERVER RUNNING")
    print("http://localhost:8000")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)