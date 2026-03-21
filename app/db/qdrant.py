"""
Qdrant client and memory/RAG storage functions.
"""
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue, PayloadSchemaType
from app.config import get_settings
import uuid

logger = logging.getLogger(__name__)

_qdrant: QdrantClient | None = None

MEMORY_COLLECTION = "memory_collection"
RAG_COLLECTION = "rag_collection"
DOCS_COLLECTION = "docs_collection"

def get_qdrant() -> QdrantClient | None:
    """Get the initialized Qdrant client."""
    global _qdrant
    if _qdrant:
        return _qdrant
        
    settings = get_settings()
    url = settings.qdrant_url or settings.qdrant_cluster_endpoint
    key = settings.qdrant_api_key or settings.qdrant_cluster_key
    
    try:
        if url and key:
            # Strip trailing slashes that might cause issues
            clean_url = url.rstrip("/")
            _qdrant = QdrantClient(url=clean_url, api_key=key, check_compatibility=False)
        elif url:
            _qdrant = QdrantClient(url=url, check_compatibility=False)
        else:
            _qdrant = QdrantClient(":memory:")
            logger.info("Using Qdrant in-memory fallback.")
            
        # Initialize Collections (assume 1536 dim for OpenAI, or 384 for all-MiniLM, we'll use 384 as default/mock)
        _init_collections(_qdrant)
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant: {e}")
        _qdrant = None
        
    return _qdrant

def _init_collections(client: QdrantClient):
    """Ensure baseline collections exist."""
    vector_size = 384 # Default fallback dimension
    collections = [MEMORY_COLLECTION, RAG_COLLECTION, DOCS_COLLECTION]
    
    try:
        logger.info("Initializing Qdrant collections...")
        # Wrap the whole block to catch metadata fetch errors
        try:
            existing = [c.name for c in client.get_collections().collections]
        except Exception as e:
            logger.warning(f"Could not fetch existing collections, trying to create anyway: {e}")
            existing = []

        for col in collections:
            if col not in existing:
                try:
                    client.create_collection(
                        collection_name=col,
                        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                    )
                    logger.info(f"Created Qdrant collection: {col}")
                except Exception as inner_e:
                    if "already exists" in str(inner_e).lower():
                        logger.info(f"Collection {col} already exists (idempotent)")
                    else:
                        logger.error(f"Failed to create collection {col}: {inner_e}")
            
            # Create payload index for user_id (required for MatchValue filtering)
            try:
                client.create_payload_index(
                    collection_name=col,
                    field_name="user_id",
                    field_schema=PayloadSchemaType.KEYWORD
                )
                logger.info(f"Ensured payload index for 'user_id' in {col}")
            except Exception as e:
                # Often fails if already exists, which is fine
                pass
    except Exception as e:
        logger.error(f"Qdrant collection init error: {e}")

# ── Pseudo-Embedding logic for now ──
def _get_embedding(text: str) -> list[float]:
    """Mock embedding generator for 384 dimensions. In prod, use `sentence-transformers` or `openai`."""
    # This is heavily mocked for architectural placeholders, normally we'd call an embedding model here
    import math
    base_val = sum(ord(c) for c in text)
    return [math.sin(base_val + i) for i in range(384)]

# ── 5. Memory Functions ─────────────────────────────────

def save_memory(user_id: str, text: str):
    """Save a conversational or agent memory block for a user."""
    client = get_qdrant()
    if not client: return False
    
    vector = _get_embedding(text)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"user_id": user_id, "text": text, "type": "memory"}
    )
    client.upsert(collection_name=MEMORY_COLLECTION, points=[point])
    return True

def search_memory(user_id: str, query: str, limit: int = 5) -> list[str]:
    """Search for relevant memories securely using user_id filtering."""
    client = get_qdrant()
    if not client: return []
    
    vector = _get_embedding(query)
    search_result = client.query_points(
        collection_name=MEMORY_COLLECTION,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
        limit=limit
    )
    return [hit.payload.get("text", "") for hit in search_result.points]

# ── 6. Basic RAG Functions ──────────────────────────────

def add_document(user_id: str, text: str, doc_name: str):
    """Store document chunked embeddings in RAG collection."""
    client = get_qdrant()
    if not client: return False
    
    # In a real pipeline, chunk the text here
    # We will simulate 1 chunk
    vector = _get_embedding(text)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"user_id": user_id, "text": text, "doc_name": doc_name}
    )
    client.upsert(collection_name=RAG_COLLECTION, points=[point])
    return True

def search_document(user_id: str, query: str, limit: int = 3) -> list[str]:
    """Search uploaded documents."""
    client = get_qdrant()
    if not client: return []
    
    vector = _get_embedding(query)
    search_result = client.query_points(
        collection_name=RAG_COLLECTION,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
        limit=limit
    )
    return [hit.payload.get("text", "") for hit in search_result.points]
