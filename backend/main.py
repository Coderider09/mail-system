from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os
import hashlib
import secrets
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

app = FastAPI()

# CORS - разрешаем запросы с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ============
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost/maildb')

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============ МОДЕЛИ ДАННЫХ ============
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Email(Base):
    __tablename__ = "emails"
    
    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    subject = Column(String, default="")
    content = Column(Text, default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token() -> str:
    return secrets.token_hex(32)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============ API ============
@app.post("/api/register")
def register(email: str, username: str, password: str, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return {"success": False, "error": "Email already exists"}
    
    hashed = hash_password(password)
    new_user = User(email=email, username=username, password=hashed, created_at=datetime.utcnow())
    db.add(new_user)
    db.commit()
    
    return {"success": True, "message": "User created"}

@app.post("/api/login")
def login(email: str, password: str, db: Session = Depends(get_db)):
    hashed = hash_password(password)
    user = db.query(User).filter(User.email == email, User.password == hashed).first()
    
    if not user:
        return {"success": False, "error": "Invalid credentials"}
    
    token = generate_token()
    return {
        "success": True,
        "access_token": token,
        "user": {"id": user.id, "email": user.email, "username": user.username}
    }

@app.post("/api/send")
def send_email(to: str, subject: str, body: str, from_email: str = "user@test.com", db: Session = Depends(get_db)):
    new_email = Email(sender=from_email, recipient=to, subject=subject, content=body, created_at=datetime.utcnow())
    db.add(new_email)
    db.commit()
    return {"success": True}

@app.get("/api/inbox")
def get_inbox(db: Session = Depends(get_db)):
    emails = db.query(Email).order_by(Email.id.desc()).all()
    
    result = []
    for row in emails:
        result.append({
            "id": row.id,
            "sender_email": row.sender,
            "sender_name": row.sender.split('@')[0] if '@' in row.sender else row.sender,
            "subject": row.subject or "",
            "body_preview": (row.content or "")[:100],
            "is_read": row.is_read,
            "sent_at": row.created_at.isoformat() if row.created_at else ""
        })
    return result

@app.get("/api/email/{email_id}")
def get_email(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    
    if not email:
        return {"error": "Not found"}
    
    email.is_read = True
    db.commit()
    
    return {
        "id": email.id,
        "sender_email": email.sender,
        "sender_name": email.sender.split('@')[0] if '@' in email.sender else email.sender,
        "recipient_email": email.recipient,
        "subject": email.subject or "",
        "body": email.content or "",
        "is_read": True,
        "sent_at": email.created_at.isoformat() if email.created_at else ""
    }

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_emails = db.query(Email).count()
    unread_emails = db.query(Email).filter(Email.is_read == False).count()
    
    users = db.query(User).order_by(User.id.desc()).all()
    emails = db.query(Email).order_by(Email.id.desc()).limit(30).all()
    
    users_rows = ""
    for u in users:
        users_rows += f"<tr><td>{u.id}</td><td>{u.email}</td><td>{u.username}</td><td>{u.created_at}</td></tr>"
    
    emails_rows = ""
    for e in emails:
        emails_rows += f"<tr><td>{e.id}</td><td>{e.sender}</td><td>{e.recipient}</td><td>{e.subject or '(no subject)'}</td><td>{str(e.created_at)[:16]}</td></tr>"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <style>
            body {{ font-family: Arial; background: #0f172a; color: #e2e8f0; padding: 40px; }}
            .stats {{ display: flex; gap: 20px; }}
            .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; }}
            .stat-number {{ font-size: 36px; color: #3b82f6; }}
            table {{ width: 100%; background: #1e293b; border-collapse: collapse; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #334155; }}
        </style>
    </head>
    <body>
        <h1>Admin Panel</h1>
        <div class="stats">
            <div class="stat-card"><div class="stat-number">{total_users}</div><div>Users</div></div>
            <div class="stat-card"><div class="stat-number">{total_emails}</div><div>Emails</div></div>
            <div class="stat-card"><div class="stat-number">{unread_emails}</div><div>Unread</div></div>
        </div>
        <h2>Users</h2>
        <table><tr><th>ID</th><th>Email</th><th>Username</th><th>Created</th></tr>{users_rows}</table>
        <h2>Recent Emails</h2>
        <table><tr><th>ID</th><th>From</th><th>To</th><th>Subject</th><th>Date</th></tr>{emails_rows}</table>
        <a href="/">Back to site</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
