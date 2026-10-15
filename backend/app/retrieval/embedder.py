"""Local embeddings (TR-L-02). The weights are baked into the image; nothing is downloaded at runtime."""
import os
from functools import lru_cache

import fastembed
from fastembed import TextEmbedding

from app.retrieval.model_name import MODEL_NAME

CACHE_DIR = os.environ.get("FASTEMBED_CACHE_PATH", "/opt/fastembed")


def model_id() -> str:
    """Stored with every vector so a model change is detected and triggers re-embedding."""
    return f"{MODEL_NAME}@fastembed-{fastembed.__version__}"


@lru_cache
def _model() -> TextEmbedding:
    return TextEmbedding(MODEL_NAME, cache_dir=CACHE_DIR, local_files_only=True)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().query_embed([text]))).tolist()
