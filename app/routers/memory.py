from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.db.qdrant import save_memory, search_memory
from app.core.auth_deps import get_current_user

router = APIRouter(prefix="/api/memory", tags=["memory"])

class MemorySave(BaseModel):
    text: str

class MemoryQuery(BaseModel):
    query: str

@router.post("/save")
async def save_user_memory(req: MemorySave, user: dict = Depends(get_current_user)):
    """Save persistent memory for an agent/user combination."""
    success = save_memory(user['id'], req.text)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Memory DB missing")

@router.post("/search")
async def search_user_memory(req: MemoryQuery, user: dict = Depends(get_current_user)):
    """Search vector memory for context injection."""
    results = search_memory(user['id'], req.query)
    return {"results": results}
