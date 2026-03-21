from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.qdrant import save_memory, search_memory

router = APIRouter(prefix="/api/memory", tags=["memory"])

class MemorySave(BaseModel):
    user_id: str
    text: str

class MemoryQuery(BaseModel):
    user_id: str
    query: str

@router.post("/save")
async def save_user_memory(req: MemorySave):
    """Save persistent memory for an agent/user combination."""
    success = save_memory(req.user_id, req.text)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Memory DB missing")

@router.post("/search")
async def search_user_memory(req: MemoryQuery):
    """Search vector memory for context injection."""
    results = search_memory(req.user_id, req.query)
    return {"results": results}
