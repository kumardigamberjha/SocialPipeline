import jwt
from fastapi import Request
from app.config import get_settings
from app.db import queries

def get_current_user(request: Request) -> dict:
    """Decodes JWT from Authorization header or query parameters, falling back to dummy user if missing/invalid."""
    settings = get_settings()
    
    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    
    if not token:
        token = request.query_params.get("token")
        
    dummy_user = {
        "id": "00000000-0000-0000-0000-000000000000",
        "email": "dummy@example.com",
    }
    
    if not token:
        return dummy_user
        
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            return dummy_user
    except jwt.PyJWTError:
        return dummy_user
        
    user = queries.get_user_by_id(user_id)
    if user is None:
        return dummy_user
        
    return user
