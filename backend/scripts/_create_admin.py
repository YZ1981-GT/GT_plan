"""创建 admin 用户"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from app.core.security import hash_password

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform"
engine = create_engine(DB_URL)

with engine.connect() as conn:
    exists = conn.execute(text("SELECT id FROM users WHERE username='admin'")).fetchone()
    if exists:
        print(f"admin already exists: {exists[0]}")
    else:
        uid = uuid.uuid4()
        hashed = hash_password("admin123")
        conn.execute(text(
            "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted) "
            "VALUES (:id, :u, :e, :p, :r, true, false)"
        ), {"id": uid, "u": "admin", "e": "admin@gt.com", "p": hashed, "r": "admin"})
        conn.commit()
        print(f"Created admin user: {uid}")

engine.dispose()
