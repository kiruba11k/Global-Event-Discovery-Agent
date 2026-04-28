"""
Embedder — uses sentence-transformers all-MiniLM-L6-v2 (free, runs locally).
No API calls, no cost, no rate limits.
384-dimensional dense vectors stored in FAISS.
"""
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
from config import get_settings
from loguru import logger

settings = get_settings()

# Singleton model — loaded once at startup
_model: Optional[SentenceTransformer] = None
_faiss_index: Optional[faiss.IndexFlatIP] = None  # Inner product = cosine on normalised vecs
_id_map: List[str] = []  # position → event_id

FAISS_PATH = "faiss_index.bin"
IDMAP_PATH = "faiss_idmap.npy"


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer(settings.embedding_model)
        logger.info("Embedding model loaded.")
    return _model


def get_index() -> faiss.IndexFlatIP:
    global _faiss_index
    if _faiss_index is None:
        _faiss_index = faiss.IndexFlatIP(settings.embedding_dim)
    return _faiss_index


def embed_text(text: str) -> np.ndarray:
    """Embed a single string → normalised float32 vector."""
    model = get_model()
    vec = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
    return vec[0].astype(np.float32)


def embed_texts(texts: List[str]) -> np.ndarray:
    """Batch embed → normalised float32 matrix."""
    model = get_model()
    vecs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=32)
    return vecs.astype(np.float32)


def build_event_text(event) -> str:
    """Combine event fields into a rich text for embedding."""
    parts = [
        event.name,
        event.description or "",
        event.short_summary or "",
        event.city or "",
        event.country or "",
        event.category or "",
        event.industry_tags or "",
        event.audience_personas or "",
    ]
    return " ".join(p for p in parts if p)


def build_profile_text(profile) -> str:
    """Combine ICP profile fields into text for embedding."""
    parts = [
        profile.company_name,
        profile.company_description,
        " ".join(profile.target_industries),
        " ".join(profile.target_personas),
        " ".join(profile.target_geographies),
        " ".join(profile.preferred_event_types),
    ]
    return " ".join(p for p in parts if p)


def add_events_to_index(events: list):
    """Add events to the FAISS index."""
    global _id_map
    index = get_index()

    texts = [build_event_text(e) for e in events]
    if not texts:
        return

    vecs = embed_texts(texts)
    index.add(vecs)
    _id_map.extend([e.id for e in events])
    logger.info(f"FAISS index now has {index.ntotal} vectors.")


def search_similar(profile_text: str, top_k: int = 50) -> List[Dict]:
    """
    Find top_k most similar events to the profile.
    Returns list of {id, score} sorted by score desc.
    """
    index = get_index()
    if index.ntotal == 0:
        logger.warning("FAISS index is empty — no semantic search possible.")
        return []

    query_vec = embed_text(profile_text).reshape(1, -1)
    k = min(top_k, index.ntotal)
    scores, indices = index.search(query_vec, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_id_map):
            continue
        results.append({"id": _id_map[idx], "cosine_score": float(score)})

    return results


def cosine_score(text_a: str, text_b: str) -> float:
    """Direct cosine similarity between two texts (no index needed)."""
    va = embed_text(text_a)
    vb = embed_text(text_b)
    return float(np.dot(va, vb))  # already normalised → dot = cosine


def save_index():
    global _faiss_index, _id_map
    if _faiss_index:
        faiss.write_index(_faiss_index, FAISS_PATH)
        np.save(IDMAP_PATH, np.array(_id_map))
        logger.info("FAISS index saved.")


def load_index():
    global _faiss_index, _id_map
    if os.path.exists(FAISS_PATH) and os.path.exists(IDMAP_PATH):
        _faiss_index = faiss.read_index(FAISS_PATH)
        _id_map = list(np.load(IDMAP_PATH, allow_pickle=True))
        logger.info(f"FAISS index loaded: {_faiss_index.ntotal} vectors.")
    else:
        _faiss_index = faiss.IndexFlatIP(settings.embedding_dim)
        _id_map = []
        logger.info("FAISS index initialised empty.")
