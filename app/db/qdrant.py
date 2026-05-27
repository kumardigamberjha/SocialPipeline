"""
Qdrant client and memory/RAG storage functions.

Uses sentence-transformers (all-MiniLM-L6-v2) for 384-dim embeddings.
All queries are scoped by user_id for multi-tenant data isolation.
"""

import logging
import uuid
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

_qdrant: QdrantClient | None = None
_qdrant_init_failed: bool = False

MEMORY_COLLECTION = "memory_collection"
RAG_COLLECTION = "rag_collection"
DOCS_COLLECTION = "docs_collection"

VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension


@lru_cache(maxsize=1)
def _get_embedding_model():
    """Lazy-load the sentence-transformer model (cached singleton)."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded sentence-transformers model: all-MiniLM-L6-v2")
        return model
    except ImportError:
        logger.warning(
            "sentence-transformers not installed. Install with: "
            "pip install sentence-transformers. Falling back to mock embeddings."
        )
        return None
    except Exception as e:
        logger.error("Failed to load embedding model: %s", e)
        return None


def get_qdrant() -> QdrantClient | None:
    """Get the initialized Qdrant client."""
    global _qdrant, _qdrant_init_failed

    if _qdrant:
        return _qdrant

    if _qdrant_init_failed:
        return None

    settings = get_settings()
    url = settings.qdrant_url or settings.qdrant_cluster_endpoint
    key = settings.qdrant_api_key or settings.qdrant_cluster_key

    try:
        if url and key:
            clean_url = url.rstrip("/")
            _qdrant = QdrantClient(url=clean_url, api_key=key, check_compatibility=False, timeout=5.0)
        elif url:
            _qdrant = QdrantClient(url=url, check_compatibility=False, timeout=5.0)
        else:
            _qdrant = QdrantClient(":memory:", timeout=5.0)
            logger.info("Using Qdrant in-memory fallback.")

        _init_collections(_qdrant)
    except Exception as e:
        logger.error("Failed to initialize Qdrant remotely: %s. Falling back to in-memory.", e)
        try:
            _qdrant = QdrantClient(":memory:", timeout=5.0)
            _init_collections(_qdrant)
        except Exception as inner_e:
            logger.error("Failed to initialize Qdrant in-memory: %s", inner_e)
            _qdrant = None
            _qdrant_init_failed = True

    return _qdrant


def _init_collections(client: QdrantClient):
    """Ensure baseline collections exist with payload indexes."""
    collections = [MEMORY_COLLECTION, RAG_COLLECTION, DOCS_COLLECTION]

    try:
        logger.info("Initializing Qdrant collections...")
        try:
            existing = [c.name for c in client.get_collections().collections]
        except Exception as e:
            logger.warning("Could not fetch existing collections, trying to create anyway: %s", e)
            existing = []

        for col in collections:
            if col not in existing:
                try:
                    client.create_collection(
                        collection_name=col,
                        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                    )
                    logger.info("Created Qdrant collection: %s", col)
                except Exception as inner_e:
                    if "already exists" in str(inner_e).lower():
                        logger.info("Collection %s already exists (idempotent)", col)
                    else:
                        logger.error("Failed to create collection %s: %s", col, inner_e)
                        raise inner_e

            # Create payload index for user_id filtering
            try:
                client.create_payload_index(
                    collection_name=col,
                    field_name="user_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info("Ensured payload index for 'user_id' in %s", col)
            except Exception:
                pass  # Often fails if already exists, which is fine
    except Exception as e:
        logger.error("Qdrant collection init error: %s", e)
        raise e


def _get_embedding(text: str) -> list[float]:
    """
    Generate a 384-dimensional embedding for the given text.
    Uses all-MiniLM-L6-v2 if available, falls back to deterministic mock.
    """
    model = _get_embedding_model()
    if model is not None:
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    # Fallback: deterministic mock embedding for development/testing
    import math
    base_val = sum(ord(c) for c in text)
    return [math.sin(base_val + i) for i in range(VECTOR_SIZE)]


# ── Memory Functions ─────────────────────────────────────────


def save_memory(user_id: str, text: str) -> bool:
    """Save a conversational or agent memory block for a user."""
    client = get_qdrant()
    if not client:
        return False

    vector = _get_embedding(text)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"user_id": user_id, "text": text, "type": "memory"},
    )
    client.upsert(
        collection_name=MEMORY_COLLECTION,
        points=[point],
    )
    return True


def search_memory(user_id: str, query: str, limit: int = 5) -> list[str]:
    """Search for relevant memories scoped to user_id."""
    client = get_qdrant()
    if not client:
        return []

    vector = _get_embedding(query)
    search_result = client.query_points(
        collection_name=MEMORY_COLLECTION,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
        limit=limit,
    )
    return [hit.payload.get("text", "") for hit in search_result.points]


# ── RAG Functions ────────────────────────────────────────────


def add_document(user_id: str, text: str, doc_name: str) -> bool:
    """Store document embeddings in the RAG collection, scoped to user_id."""
    client = get_qdrant()
    if not client:
        return False

    vector = _get_embedding(text)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"user_id": user_id, "text": text, "doc_name": doc_name},
    )
    client.upsert(
        collection_name=RAG_COLLECTION,
        points=[point],
    )
    return True


def search_document(user_id: str, query: str, limit: int = 3) -> list[str]:
    """Search uploaded documents, scoped to user_id."""
    client = get_qdrant()
    if not client:
        return []

    vector = _get_embedding(query)
    search_result = client.query_points(
        collection_name=RAG_COLLECTION,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
        limit=limit,
    )
    return [hit.payload.get("text", "") for hit in search_result.points]
