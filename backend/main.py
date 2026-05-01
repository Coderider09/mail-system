from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import sqlite3
import hashlib
import secrets
from datetime import datetime

app = FastAPI()

# Разрешаем запросы с любых источников
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

def generate_token() -> str:
    return secrets.token_hex(32)

# ============ ГЛАВНАЯ СТРАНИЦА ============
@app.get("/")
def root():
    return {"message": "Mail System API is running", "docs": "/docs", "admin": "/admin"}

# ============ РЕГИСТРАЦИЯ ============
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
    
    return {"success": True, "message": "User created"}

# ============ ВХОД ============
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
    
    token = generate_token()
    return {
        "success": True,
        "access_token": token,
        "user": {"id": user[0], "email": user[1], "username": user[2]}
    }

# ============ ОТПРАВКА ПИСЬМА ============
@app.post("/api/send")
def send_email(to: str, subject: str, body: str, from_email: str = "user@test.com"):
    conn = get_db()
    conn.execute(
        "INSERT INTO emails (sender, recipient, subject, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (from_email, to, subject, body, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"success": True}

# ============ ПОЛУЧЕНИЕ ПИСЕМ ============
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

# ============ ПРОСМОТР ПИСЬМА ============
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
        return {"error": "Not found"}
    
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

# ============ АДМИН-ПАНЕЛЬ (РАБОТАЕТ!) ============
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    conn = get_db()
    
    # Получаем всех пользователей
    users = conn.execute("SELECT id, email, username, created_at FROM users ORDER BY id DESC").fetchall()
    
    # Получаем последние письма
    emails = conn.execute(
        "SELECT id, sender, recipient, subject, created_at FROM emails ORDER BY id DESC LIMIT 30"
    ).fetchall()
    
    # Статистика
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    unread_emails = conn.execute("SELECT COUNT(*) FROM emails WHERE is_read = 0").fetchone()[0]
    
    conn.close()
    
    # Создаём HTML страницу
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Admin Panel - Mail System</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                background: #0f172a; 
                color: #e2e8f0; 
                padding: 40px;
            }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ color: #3b82f6; margin-bottom: 24px; }}
            h2 {{ color: #94a3b8; margin: 32px 0 16px 0; font-size: 20px; }}
            .stats {{ display: flex; gap: 20px; margin-bottom: 40px; flex-wrap: wrap; }}
            .stat-card {{
                background: #1e293b;
                padding: 20px;
                border-radius: 12px;
                border: 1px solid #334155;
                min-width: 160px;
            }}
            .stat-number {{ font-size: 36px; font-weight: bold; color: #3b82f6; }}
            .stat-label {{ color: #94a3b8; margin-top: 8px; }}
            table {{
                width: 100%;
                background: #1e293b;
                border-radius: 12px;
                overflow: hidden;
                border-collapse: collapse;
            }}
            th, td {{
                padding: 12px 16px;
                text-align: left;
                border-bottom: 1px solid #334155;
            }}
            th {{ background: #334155; color: #e2e8f0; }}
            .back-link {{
                display: inline-block;
                margin-top: 40px;
                color: #3b82f6;
                text-decoration: none;
            }}
            .back-link:hover {{ text-decoration: underline; }}
            .badge {{
                background: #22c55e;
                color: white;
                padding: 2px 8px;
                border-radius: 20px;
                font-size: 11px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin Panel - Mail System</h1>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{total_users}</div>
                    <div class="stat-label">👥 Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_emails}</div>
                    <div class="stat-label">✉️ Total Emails</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{unread_emails}</div>
                    <div class="stat-label">📖 Unread Emails</div>
                </div>
            </div>
            
            <h2>📊 Users List</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Email</th>
                        <th>Username</th>
                        <th>Created At</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for user in users:
        html += f"""
                    <tr>
                        <td>{user['id']}</td>
                        <td>{user['email']}</td>
                        <td>{user['username']}</td>
                        <td>{user['created_at'] or 'Unknown'}</td>
                    </tr>
        """
    
    html += """
                </tbody>
            </table>
            
            <h2>📧 Recent Emails (last 30)</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>From</th>
                        <th>To</th>
                        <th>Subject</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for email in emails:
        html += f"""
                    <tr>
                        <td>{email['id']}</td>
                        <td>{email['sender'][:30]}</td>
                        <td>{email['recipient'][:30]}</td>
                        <td>{email['subject'] or '(no subject)'}</td>
                        <td>{email['created_at'][:16] if email['created_at'] else 'Unknown'}</td>
                    </tr>
        """
    
    html += """
                </tbody>
            </table>
            
            <a href="/" class="back-link">← Back to Mail System</a>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

# ============ API ДЛЯ АДМИНКИ ============
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

# ============ ЗАПУСК ============
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("✅ MAIL SYSTEM RUNNING")
    print("📧 http://localhost:8000")
    print("🔐 Admin: http://localhost:8000/admin")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
