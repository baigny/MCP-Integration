"""ChromaDB persistent client + collection helpers."""
import threading

import chromadb

PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "resume_chunks"

_client = None
_client_lock = threading.Lock()


def get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(path=PERSIST_DIR)
    return _client


def get_collection():
    return get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(chunks):
    """chunks: list of {"id": str, "text": str, "embedding": list[float], "metadata": dict}"""
    if not chunks:
        return
    collection = get_collection()
    collection.upsert(
        ids=[c["id"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )


def query(embedding, top_k=10, where=None):
    collection = get_collection()
    kwargs = {"query_embeddings": [embedding], "n_results": top_k}
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def count():
    return get_collection().count()


def reset():
    get_client().delete_collection(COLLECTION_NAME)
