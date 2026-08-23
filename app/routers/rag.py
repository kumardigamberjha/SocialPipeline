from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.auth_deps import get_current_user
from app.db.qdrant import add_document, search_document

router = APIRouter(prefix="/api/rag", tags=["rag"])


class RagQuery(BaseModel):
    query: str


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload a file (txt) for RAG embedding."""
    # Stays async only for the UploadFile read, which is genuinely async I/O.
    try:
        content = await file.read()
        text = content.decode("utf-8")
        # add_document runs sentence-transformers embedding — CPU-bound and
        # synchronous. Threaded off the loop rather than awaited directly.
        import asyncio

        success = await asyncio.to_thread(add_document, user["id"], text, file.filename)
        if success:
            return {"status": "success", "message": f"{file.filename} embedded successfully."}
        raise HTTPException(status_code=500, detail="Qdrant missing")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# `def`, not `async def`: search_document is a synchronous Qdrant call with no
# async I/O of its own, so a plain def lets FastAPI run it in the threadpool.
@router.post("/query")
def query_document(req: RagQuery, user: dict = Depends(get_current_user)):
    """Query uploaded documents for RAG context."""
    results = search_document(user["id"], req.query)
    return {"results": results}
