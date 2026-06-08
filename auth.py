"""Auth utilities - JWT tokens, password hashing, encryption"""
import bcrypt
import jwt
import os
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production-123")
ENCRYPT_KEY = os.getenv("ENCRYPT_KEY", Fernet.generate_key().decode())
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

_fernet = Fernet(ENCRYPT_KEY.encode() if isinstance(ENCRYPT_KEY, str) else ENCRYPT_KEY)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("user_id")
    except:
        return None

def encrypt(text: str) -> str:
    return _fernet.encrypt(text.encode()).decode()

def decrypt(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()
