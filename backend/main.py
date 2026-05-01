from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import sqlite3
import hashlib
import secrets
from datetime import datetime
import os

app = FastAPI(title="Mail System API", version="1.0.0")

# CORS - разрешаем запросы с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ БАЗА ДАННЫХ ============
def get_db():
    conn = sqlite3.connect('mail.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Создаём таблицы при запуске
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
conn.execute('''
    CREATE TABLE IF NOT EXISTS registration_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE,
        used INTEGER DEFAULT 0,
        created_at TEXT
    )
''')
conn.commit()
conn.close()

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token() -> str:
    return secrets.token_hex(32)

# ============ API АУТЕНТИФИКАЦИИ ============
@app.post("/api/register")
def register(email: str, username: str, password: str, registration_token: str = None):
    conn = get_db()
    
    # Проверка на спам-регистрацию
    if registration_token:
        token_check = conn.execute(
            "SELECT id FROM registration_tokens WHERE token = ? AND used = 0",
            (registration_token,)
        ).fetchone()
        if not token_check:
            conn.close()
            raise HTTPException(status_code=403, detail="Invalid or used registration token")
    
    # Проверка существования пользователя
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Создание пользователя
    hashed = hash_password(password)
    conn.execute(
        "INSERT INTO users (email, username, password, created_at) VALUES (?, ?, ?, ?)",
        (email, username, hashed, datetime.now().isoformat())
    )
    
    # Отмечаем токен как использованный
    if registration_token:
        conn.execute("UPDATE registration_tokens SET used = 1 WHERE token = ?", (registration_token,))
    
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    
    access_token = generate_token()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user_id, "email": email, "username": username}
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
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = generate_token()
    return {
        "access_token": access_token,
        "token_type": "bearer",
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
def get_inbox(email: str = None):
    conn = get_db()
    if email:
        emails = conn.execute(
            "SELECT id, sender, subject, content, is_read, created_at FROM emails WHERE recipient = ? ORDER BY id DESC",
            (email,)
        ).fetchall()
    else:
        emails = conn.execute(
            "SELECT id, sender, subject, content, is_read, created_at FROM emails ORDER BY id DESC"
        ).fetchall()
    
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
    conn.close()
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

# ============ АДМИН-ПАНЕЛЬ ============
@app.get("/admin")
def admin_panel():
    conn = get_db()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    unread = conn.execute("SELECT COUNT(*) FROM emails WHERE is_read = 0").fetchone()[0]
    conn.close()
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel - Mail System</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ margin-bottom: 24px; color: #3b82f6; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }}
            .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; }}
            .stat-number {{ font-size: 36px; font-weight: bold; color: #3b82f6; }}
            .stat-label {{ color: #94a3b8; margin-top: 8px; }}
            .section {{ margin-bottom: 40px; }}
            .section h2 {{ margin-bottom: 16px; color: #94a3b8; }}
            table {{ width: 100%; background: #1e293b; border-radius: 12px; overflow: hidden; border-collapse: collapse; }}
            th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #334155; }}
            th {{ background: #334155; color: #e2e8f0; }}
            .badge {{ background: #22c55e; color: white; padding: 2px 8px; border-radius: 20px; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin Panel - Mail System</h1>
            <div class="stats">
                <div class="stat-card"><div class="stat-number">{users}</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-number">{emails}</div><div class="stat-label">Total Emails</div></div>
                <div class="stat-card"><div class="stat-number">{unread}</div><div class="stat-label">Unread Emails</div></div>
            </div>
            <div class="section">
                <h2>📊 Users List</h2>
                <table>
                    <thead><tr><th>ID</th><th>Email</th><th>Username</th><th>Created At</th></tr></thead>
                    <tbody>
                        {''.join([f"<tr><td>{u['id']}</td><td>{u['email']}</td><td>{u['username']}</td><td>{u['created_at'] or 'Unknown'}</td></tr>" for u in conn.execute("SELECT id, email, username, created_at FROM users ORDER BY id DESC").fetchall()])}
                    </tbody>
                </table>
            </div>
            <div class="section">
                <h2>📧 Recent Emails</h2>
                <table>
                    <thead><tr><th>ID</th><th>From</th><th>To</th><th>Subject</th><th>Date</th></tr></thead>
                    <tbody>
                        {''.join([f"<tr><td>{e['id']}</td><td>{e['sender']}</td><td>{e['recipient']}</td><td>{e['subject'] or '(no subject)'}</td><td>{e['created_at'][:16]}</td></tr>" for e in conn.execute("SELECT id, sender, recipient, subject, created_at FROM emails ORDER BY id DESC LIMIT 20").fetchall()])}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

# ============ АДМИН API ============
@app.get("/api/admin/stats")
def admin_stats():
    conn = get_db()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    unread = conn.execute("SELECT COUNT(*) FROM emails WHERE is_read = 0").fetchone()[0]
    conn.close()
    return {"users": users, "emails": emails, "unread": unread}

@app.get("/api/admin/users")
def admin_users():
    conn = get_db()
    users = conn.execute("SELECT id, email, username, created_at FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return [{"id": u[0], "email": u[1], "username": u[2], "created_at": u[3]} for u in users]

@app.get("/api/admin/emails")
def admin_emails():
    conn = get_db()
    emails = conn.execute("SELECT id, sender, recipient, subject, created_at FROM emails ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return [{"id": e[0], "sender": e[1], "recipient": e[2], "subject": e[3], "created_at": e[4]} for e in emails]

@app.post("/api/admin/create-token")
def create_token(data: dict):
    token = data.get('token', secrets.token_hex(16))
    conn = get_db()
    try:
        conn.execute("INSERT INTO registration_tokens (token, created_at) VALUES (?, ?)", (token, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return {"token": token, "message": "Token created successfully"}
    except:
        conn.close()
        raise HTTPException(status_code=400, detail="Token already exists")

@app.get("/api/admin/tokens")
def admin_tokens():
    conn = get_db()
    tokens = conn.execute("SELECT token, used, created_at FROM registration_tokens ORDER BY id DESC").fetchall()
    conn.close()
    return [{"token": t[0], "used": bool(t[1]), "created_at": t[2]} for t in tokens]

# ============ ЗАПУСК ============
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("✅ MAIL SYSTEM WITH ADMIN PANEL")
    print("📧 http://localhost:8000")
    print("🔐 Admin panel: http://localhost:8000/admin")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
