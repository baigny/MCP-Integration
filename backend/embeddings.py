"""HuggingFace sentence-transformers embedding wrapper (local, no API key)."""
import threading

from sentence_transformers import SentenceTransformer

MODEL = "all-MiniLM-L6-v2"

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Loads (and caches) the embedding model once per process. Reused across
    calls/threads so we don't re-download or re-init on every embed."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    # Model is already downloaded after the first run - skip the
                    # network round-trip HF Hub otherwise makes on every load to
                    # check for updates (that check alone was ~5s per call).
                    _model = SentenceTransformer(MODEL, local_files_only=True)
                except OSError:
                    _model = SentenceTransformer(MODEL)
    return _model


def embed_text(text):
    """Returns embedding vector (list[float]) for a single string."""
    return _get_model().encode(text).tolist()


def embed_texts(texts):
    """Returns list of embedding vectors for a list of strings, in one batched call."""
    if not texts:
        return []
    return _get_model().encode(texts).tolist()
