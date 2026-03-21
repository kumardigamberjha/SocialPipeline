from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.db.supabase import get_supabase

router = APIRouter(prefix="/api/auth", tags=["auth"])

class AuthCredentials(BaseModel):
    email: str
    password: str

@router.post("/register", summary="Register a new user")
async def register(creds: AuthCredentials):
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        res = client.auth.sign_up({"email": creds.email, "password": creds.password})
        
        # Save user to custom users table
        if res.user:
            client.table("users").insert({"id": res.user.id, "email": res.user.email}).execute()
        return {"user": res.user, "session": res.session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", summary="Login user")
async def login(creds: AuthCredentials):
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        res = client.auth.sign_in_with_password({"email": creds.email, "password": creds.password})
        return {"user": res.user, "session": res.session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
