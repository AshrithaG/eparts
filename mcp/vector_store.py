"""
Vector Store MCP server — ChromaDB wrapper for RAG over sessions and artifacts.

Tools exposed:
  embed_and_store()  — chunk text, embed, and upsert into a collection
  query()            — semantic search over a collection
  delete()           — remove documents by ID

Used by: Coach Memory Agent, ML Decision Agent
Embedding model: all-MiniLM-L6-v2 (consistent with client ML POC)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger("mcp.vector_store")

DEFAULT_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./memory/chroma")
COLLECTION_SESSIONS = "coach_sessions"
COLLECTION_DECISIONS = "ml_decisions"


class VectorStoreMCP:
    def __init__(self, persist_dir: str | None = None):
        path = persist_dir or DEFAULT_PERSIST_DIR
        self._client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        # Use local ONNX embedding model — no API key required
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        self._embedding_fn = ONNXMiniLM_L6_V2()
        logger.info(f"ChromaDB initialized at {path} (embedding: ONNX MiniLM-L6-v2)")

    def get_or_create_collection(self, name: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embedding_fn,
        )

    def embed_and_store(
        self,
        collection_name: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> int:
        """
        Store documents in a ChromaDB collection.
        ChromaDB handles embedding via its default model.
        Returns the number of documents stored.
        """
        collection = self.get_or_create_collection(collection_name)
        collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info(f"Stored {len(documents)} documents in '{collection_name}'")
        return len(documents)

    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over a collection. Returns ranked results with
        document text, metadata, and distance scores.
        """
        collection = self.get_or_create_collection(collection_name)

        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(n_results, collection.count() or 1),
        }
        if where:
            kwargs["where"] = where

        if collection.count() == 0:
            logger.warning(f"Collection '{collection_name}' is empty")
            return []

        results = collection.query(**kwargs)

        parsed = []
        for i in range(len(results["ids"][0])):
            parsed.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
            })

        logger.info(
            f"Query on '{collection_name}': '{query_text[:60]}...' → {len(parsed)} results"
        )
        return parsed

    def delete(self, collection_name: str, ids: list[str]) -> None:
        """Remove documents by ID from a collection."""
        collection = self.get_or_create_collection(collection_name)
        collection.delete(ids=ids)
        logger.info(f"Deleted {len(ids)} documents from '{collection_name}'")

    def count(self, collection_name: str) -> int:
        """Return the number of documents in a collection."""
        collection = self.get_or_create_collection(collection_name)
        return collection.count()
