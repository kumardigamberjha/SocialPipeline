from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List
from app.db.qdrant import add_document, search_document

router = APIRouter(prefix="/api/rag", tags=["rag"])

class RagQuery(BaseModel):
    user_id: str
    query: str

@router.post("/upload")
async def upload_document(user_id: str = Form(...), file: UploadFile = File(...)):
    """Upload a file (txt) for RAG embedding."""
    try:
        content = await file.read()
        text = content.decode("utf-8")
        success = add_document(user_id, text, file.filename)
        if success:
            return {"status": "success", "message": f"{file.filename} embedded successfully."}
        raise HTTPException(status_code=500, detail="Qdrant missing")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/query")
async def query_document(req: RagQuery):
    """Query uploaded documents for RAG context."""
    results = search_document(req.user_id, req.query)
    return {"results": results}
