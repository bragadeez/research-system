"""
core/rag_engine.py

Core RAG engine for ScholarNode AI.
Handles report ingestion, semantic search via ChromaDB, and query answering via Gemini.
"""
from __future__ import annotations

import os
import re
import shutil
from textwrap import dedent
from typing import Dict, List, Optional, Tuple

from loguru import logger
import chromadb

from config import settings
from core.llm_client import llm


# Lazy loading of sentence_transformers to save startup time
_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        except Exception as exc:
            logger.error(f"[RAG] Failed to load SentenceTransformer: {exc}")
            raise exc
    return _embedder


def clean_markdown_headers(text: str) -> List[Tuple[str, str]]:
    """
    Split markdown into sections based on H2 headers (##).
    Returns list of (section_title, section_content).
    """
    sections = []
    # Find all ## headers
    pattern = r"(^|\n)##\s+(.+)"
    matches = list(re.finditer(pattern, text))
    
    if not matches:
        return [("General", text)]
        
    # Add intro before first ## if it exists
    first_start = matches[0].start()
    intro = text[:first_start].strip()
    if intro:
        sections.append(("Introduction", intro))
        
    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections.append((title, content))
            
    return sections


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """
    Chops text into overlapping chunks.
    """
    chunks = []
    if len(text) <= chunk_size:
        return [text]
        
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
        
    return chunks


class RAGEngine:
    def __init__(self):
        self._chroma_client = None

    @property
    def chroma_client(self) -> chromadb.PersistentClient:
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        return self._chroma_client

    def build_index(self, session_id: str, report_md: str, sources: List[dict] = None) -> bool:
        """
        Builds ChromaDB collection for a session.
        Chunks and embeds the report and top source abstracts.
        """
        try:
            client = self.chroma_client
            collection_name = f"session_{session_id}"
            
            # Delete if exists to rebuild cleanly
            try:
                client.delete_collection(name=collection_name)
            except Exception:
                pass
                
            collection = client.create_collection(name=collection_name)
            
            documents: List[str] = []
            metadatas: List[dict] = []
            ids: List[str] = []
            
            # 1. Parse report markdown by headers
            sections = clean_markdown_headers(report_md)
            chunk_idx = 0
            for sec_title, sec_content in sections:
                chunks = chunk_text(sec_content, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
                for i, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append({
                        "source_type": "report",
                        "section": sec_title,
                        "chunk_index": i,
                    })
                    ids.append(f"report_{chunk_idx}")
                    chunk_idx += 1
                    
            # 2. Add source document summaries / papers if available
            if sources:
                for idx, src in enumerate(sources):
                    title = src.get("title", f"Source {idx}")
                    url = src.get("url", "")
                    content = src.get("content", "")
                    if content:
                        chunks = chunk_text(content, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
                        for i, chunk in enumerate(chunks[:3]):  # limit to top 3 chunks per source to prevent bloat
                            documents.append(chunk)
                            metadatas.append({
                                "source_type": "external_source",
                                "title": title,
                                "url": url,
                                "chunk_index": i,
                            })
                            ids.append(f"source_{idx}_{i}")
                            
            if not documents:
                return False
                
            # Embed
            embedder = get_embedder()
            embeddings = embedder.encode(documents)
            
            # Add to collection
            collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"[RAG] Indexed session {session_id}: {len(documents)} chunks")
            return True
            
        except Exception as exc:
            logger.error(f"[RAG] Failed to build index for session {session_id}: {exc}")
            return False

    def query(self, session_id: str, user_query: str, chat_history: List[dict] = None) -> Tuple[str, List[dict]]:
        """
        Queries the vector database, formats context, and uses Gemini to answer.
        Returns:
            (answer_text, source_references)
        """
        try:
            client = self.chroma_client
            collection_name = f"session_{session_id}"
            
            try:
                collection = client.get_collection(name=collection_name)
            except Exception:
                # Collection doesn't exist, return warning
                return "Vector store has not been initialised for this session. Please wait for the research to finish or build the index.", []
                
            # Embed query
            embedder = get_embedder()
            query_embedding = embedder.encode([user_query])[0].tolist()
            
            # Search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=settings.RAG_TOP_K
            )
            
            retrieved_chunks = results.get("documents", [[]])[0]
            retrieved_metadatas = results.get("metadatas", [[]])[0]
            
            # Format context
            context_blocks = []
            source_references = []
            for doc, meta in zip(retrieved_chunks, retrieved_metadatas):
                stype = meta.get("source_type", "unknown")
                if stype == "report":
                    label = f"Report Section: {meta.get('section', 'General')}"
                else:
                    label = f"External Source: {meta.get('title', 'Unknown')} ({meta.get('url', '')})"
                    
                context_blocks.append(f"[{label}]\n{doc}")
                source_references.append({
                    "type": stype,
                    "title": meta.get("section") if stype == "report" else meta.get("title"),
                    "url": meta.get("url") if stype != "report" else "",
                    "snippet": doc[:160] + "..."
                })
                
            context = "\n\n".join(context_blocks)
            
            # Format history
            history_lines = []
            if chat_history:
                for h in chat_history[-settings.RAG_MAX_HISTORY:]:
                    role = "User" if h.get("role") == "user" else "Assistant"
                    history_lines.append(f"{role}: {h.get('content')}")
            history = "\n".join(history_lines) if history_lines else "No previous history."
            
            # Format prompt
            prompt = dedent(f"""\
            You are ScholarNode AI, a professional research assistant.
            Use the following pieces of retrieved context and the conversation history to answer the user's question.
            If you don't know the answer, say that you don't know based on the provided context. Do not make up information.
            
            CONTEXT FROM RESEARCH REPORT AND SOURCES:
            {context}
            
            CONVERSATION HISTORY:
            {history}
            
            USER QUESTION: {user_query}
            
            Provide a detailed, helpful, and objective answer in markdown format. Cite specific sections or papers when possible.
            """)
            
            # Generate response
            # Using Gemini Client blockingly since it is wrapped in an async handler at server.py
            # or we can do async if we call it from an async handler (which server.py is).
            # Let's provide a synchronous run option or we can make this query method async!
            # Since query is called from async server.py, let's make query async.
            return prompt, source_references
            
        except Exception as exc:
            logger.error(f"[RAG] Query execution failed: {exc}")
            return "An error occurred while retrieval QA execution.", []

    async def answer_async(self, session_id: str, user_query: str, chat_history: List[dict] = None) -> Tuple[str, List[dict]]:
        """
        Async wrapper to retrieve context and invoke Gemini.
        """
        prompt, source_references = self.query(session_id, user_query, chat_history)
        if len(source_references) == 0 and prompt.startswith("Vector store"):
            return prompt, []
            
        try:
            answer = await llm.generate_text_async(prompt, high_reasoning=False)
            return answer, source_references
        except Exception as e:
            logger.error(f"[RAG] LLM generation failed: {e}")
            return f"Error generating answer: {e}", source_references

    def delete_index(self, session_id: str):
        """Clean up ChromaDB collection for a session to save disk space."""
        try:
            client = self.chroma_client
            client.delete_collection(name=f"session_{session_id}")
            logger.info(f"[RAG] Deleted index for session {session_id}")
        except Exception:
            pass


rag_engine = RAGEngine()
