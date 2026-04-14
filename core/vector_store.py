"""
core/vector_store.py

Improvements vs original:
  1. Default embedding model: BAAI/bge-small-en-v1.5
     (outperforms all-MiniLM-L6-v2 on BEIR scientific benchmarks)
  2. Fixed ChromaDB metadata bug: lists are now JSON-serialized
     (ChromaDB only supports str/int/float/bool in metadata)
  3. Metadata deserialization on query (reverses the serialization)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from config import settings
from models.extraction import ExtractedEvidence

try:
    import chromadb
except Exception:
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Metadata serialization helpers ────────────────────────────────────────────
# ChromaDB only accepts str/int/float/bool — serialize lists and complex types

_LIST_FIELDS = {"supporting_sources", "keywords", "quality_flags"}


def _serialize_meta(meta: dict) -> dict:
    """Flatten list fields to JSON strings for ChromaDB storage."""
    out = {}
    for k, v in meta.items():
        if isinstance(v, list):
            out[k] = json.dumps(v)
        elif isinstance(v, bool):
            out[k] = v
        elif v is None:
            out[k] = ""
        elif hasattr(v, "value"):   # Enum
            out[k] = v.value
        else:
            out[k] = v
    return out


def _deserialize_meta(meta: dict) -> dict:
    """Restore list fields from JSON strings."""
    out = {}
    for k, v in meta.items():
        if k in _LIST_FIELDS and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        else:
            out[k] = v
    return out


class EvidenceStore:
    def __init__(
        self,
        persist_dir: str = None,
        collection_name: str = "research_evidence",
        embedding_model: str = None,
    ):
        self.persist_dir = Path(persist_dir or settings.EVIDENCE_STORE_PATH)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.collection_name = collection_name
        # CHANGED: BAAI/bge-small-en-v1.5 instead of all-MiniLM-L6-v2
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.fallback_path = self.persist_dir / "evidence.json"
        self._embedder = None
        self._backend = "fallback"
        self._memory: List[Dict] = []

        self._init_backend()

    @property
    def embedder(self):
        if self._embedder is None:
            if SentenceTransformer is None:
                return None
            try:
                self._embedder = SentenceTransformer(self.embedding_model)
                logger.info(f"[EvidenceStore] Loaded embedding model: {self.embedding_model}")
            except Exception as exc:
                logger.warning(f"[EvidenceStore] Embedding model load failed: {exc}")
                self._embedder = None
        return self._embedder

    def _init_backend(self):
        if chromadb is not None:
            try:
                self.client = chromadb.PersistentClient(path=str(self.persist_dir))
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                self._backend = "chroma"
                logger.info("[EvidenceStore] Using ChromaDB backend")
                return
            except Exception as exc:
                logger.warning(f"[EvidenceStore] ChromaDB unavailable: {exc}")

        self._backend = "fallback"
        self.collection = None
        self.client = None
        self._load_fallback()
        logger.info("[EvidenceStore] Using JSON fallback backend")

    def _load_fallback(self):
        if self.fallback_path.exists():
            try:
                self._memory = json.loads(self.fallback_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"[EvidenceStore] Failed to load fallback: {exc}")
                self._memory = []
        else:
            self._memory = []

    def _save_fallback(self):
        try:
            self.fallback_path.write_text(
                json.dumps(self._memory, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"[EvidenceStore] Failed to save fallback: {exc}")

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        embedder = self.embedder
        if embedder is None:
            return [[] for _ in texts]
        # Batch encode all texts at once — much faster than one-by-one
        vectors = embedder.encode(texts, normalize_embeddings=True, batch_size=64)
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]

    def upsert_evidences(self, evidences: List[ExtractedEvidence]) -> int:
        if not evidences:
            return 0

        docs = [e.evidence_text for e in evidences]
        embs = self._embed_texts(docs)
        ids = [e.evidence_id for e in evidences]

        if self._backend == "chroma":
            try:
                # FIX: serialize metadata so lists don't crash ChromaDB
                metas = [
                    _serialize_meta(e.model_dump(exclude={"evidence_text"}))
                    for e in evidences
                ]
                self.collection.upsert(
                    ids=ids,
                    documents=docs,
                    metadatas=metas,
                    embeddings=embs if embs and embs[0] else None,
                )
                return len(evidences)
            except Exception as exc:
                logger.warning(f"[EvidenceStore] Chroma upsert failed: {exc}")
                self._backend = "fallback"

        existing_ids = {item.get("evidence_id") for item in self._memory}
        added = 0
        for evidence in evidences:
            if evidence.evidence_id in existing_ids:
                continue
            self._memory.append(evidence.model_dump())
            added += 1
        if added:
            self._save_fallback()
        return added

    def query(
        self,
        query_text: str,
        top_k: int = 8,
        topic: Optional[str] = None,
        subtopic: Optional[str] = None,
    ) -> List[ExtractedEvidence]:
        if not query_text.strip():
            return []

        if self._backend == "chroma":
            try:
                query_emb = self._embed_texts([query_text])[0]
                if not query_emb:
                    return []

                where: dict = {}
                if topic:
                    where["topic"] = topic
                if subtopic:
                    where["subtopic"] = subtopic

                result = self.collection.query(
                    query_embeddings=[query_emb],
                    n_results=min(top_k, self.collection.count() or 1),
                    where=where or None,
                )

                docs = result.get("documents", [[]])[0]
                metas = result.get("metadatas", [[]])[0]
                ids = result.get("ids", [[]])[0]

                out = []
                for i, doc in enumerate(docs):
                    meta = _deserialize_meta(metas[i] if i < len(metas) else {})
                    out.append(ExtractedEvidence(
                        evidence_id=ids[i] if i < len(ids) else meta.get("evidence_id", ""),
                        evidence_text=doc,
                        **meta,
                    ))
                return out
            except Exception as exc:
                logger.warning(f"[EvidenceStore] Chroma query failed: {exc}")

        # Fallback: cosine similarity over in-memory store
        query_vec = self._embed_texts([query_text])[0]
        if not query_vec:
            return []

        scored = []
        for item in self._memory:
            if topic and item.get("topic") != topic:
                continue
            if subtopic and item.get("subtopic") != subtopic:
                continue
            text = item.get("evidence_text", "")
            if not text:
                continue
            item_vec = self._embed_texts([text])[0]
            sim = _cosine_similarity(query_vec, item_vec)
            scored.append((sim, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, item in scored[:top_k]:
            try:
                results.append(ExtractedEvidence(**item))
            except Exception:
                pass
        return results

    def stats(self) -> Dict:
        if self._backend == "chroma":
            try:
                count = self.collection.count()
            except Exception:
                count = 0
            return {"backend": "chroma", "count": count, "model": self.embedding_model}
        return {"backend": "fallback", "count": len(self._memory), "model": self.embedding_model}


evidence_store = EvidenceStore()
