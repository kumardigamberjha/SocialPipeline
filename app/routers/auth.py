from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import bcrypt
import jwt
from datetime import datetime, timedelta
from app.db import queries
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

class AuthCredentials(BaseModel):
    email: str
    password: str

@router.post("/register", summary="Register a new user")
async def register(creds: AuthCredentials):
    settings = get_settings()
    
    # Check if email already exists
    existing_user = queries.get_user_by_email(creds.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already registered")
        
    # Hash password
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(creds.password.encode('utf-8'), salt).decode('utf-8')
    
    try:
        user = queries.create_user(creds.email, password_hash)
        queries.init_usage(user['id'])
        
        # Generate JWT token
        payload = {
            "sub": user['id'],
            "email": user['email'],
            "exp": datetime.utcnow() + timedelta(days=settings.jwt_expire_days)
        }
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
        
        # Remove password_hash from response
        user.pop('password_hash', None)
        return {"user": user, "session": {"access_token": token}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", summary="Login user")
async def login(creds: AuthCredentials):
    settings = get_settings()
    
    user = queries.get_user_by_email(creds.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    # Check password
    if not bcrypt.checkpw(creds.password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    # Generate JWT token
    payload = {
        "sub": user['id'],
        "email": user['email'],
        "exp": datetime.utcnow() + timedelta(days=settings.jwt_expire_days)
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    
    # Remove password_hash from response
    user.pop('password_hash', None)
    return {"user": user, "session": {"access_token": token}}
