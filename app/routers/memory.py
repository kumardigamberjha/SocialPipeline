from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth_deps import get_current_user
from app.db.qdrant import save_memory, search_memory

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemorySave(BaseModel):
    text: str


class MemoryQuery(BaseModel):
    query: str


# `def`, not `async def`: save_memory/search_memory are synchronous Qdrant
# calls, and the async versions of these handlers awaited them directly on the
# event loop, blocking every other request for the round trip. A plain `def`
# is run in FastAPI's threadpool automatically.


@router.post("/save")
def save_user_memory(req: MemorySave, user: dict = Depends(get_current_user)):
    """Save persistent memory for an agent/user combination."""
    success = save_memory(user["id"], req.text)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Memory DB missing")


@router.post("/search")
def search_user_memory(req: MemoryQuery, user: dict = Depends(get_current_user)):
    """Search vector memory for context injection."""
    results = search_memory(user["id"], req.query)
    return {"results": results}
