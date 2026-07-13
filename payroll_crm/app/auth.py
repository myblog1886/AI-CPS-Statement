import os
import bcrypt
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from app.models import User

def hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt())

def verify_password(plain: str, hashed) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode()
    return bcrypt.checkpw(plain.encode(), hashed)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

def set_session(request: Request, user_id: int):
    from itsdangerous import URLSafeSerializer
    s = URLSafeSerializer(SECRET_KEY)
    request.session["user_id"] = s.dumps(user_id)

def get_user_id_from_session(request: Request):
    from itsdangerous import URLSafeSerializer, BadSignature
    token = request.session.get("user_id")
    if not token:
        return None
    try:
        s = URLSafeSerializer(SECRET_KEY)
        return s.loads(token)
    except BadSignature:
        return None

def get_current_user(request: Request, session: Session):
    user_id = get_user_id_from_session(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def role_required(role: str):
    def dependency(request: Request, session: Session):
        user = get_current_user(request, session)
        if user.role != role:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return dependency
