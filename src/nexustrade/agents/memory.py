"""ChromaDB market situation memory.

Stores market situations (context + signal + outcome) in a vector database
for retrieval of similar historical situations during agent analysis.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _try_import_chromadb():
    try:
        import chromadb
        return chromadb, True
    except ImportError:
        return None, False


class MarketMemory:
    """Stores and retrieves market situations using vector similarity.

    Uses ChromaDB for embedding storage and similarity search.
    Falls back to a simple in-memory list if ChromaDB is not available.
    """

    def __init__(
        self,
        collection_name: str = "market_memory",
        persist_directory: str | None = None,
        retention_days: int = 90,
        max_entries: int = 10000,
        similarity_threshold: float = 0.75,
    ) -> None:
        self._collection_name = collection_name
        self._persist_dir = persist_directory
        self._retention_days = retention_days
        self._max_entries = max_entries
        self._similarity_threshold = similarity_threshold
        self._collection = None
        self._client = None
        self._available = False
        self._fallback_store: list[dict[str, Any]] = []
        self._initialize()

    def _initialize(self) -> None:
        chromadb, available = _try_import_chromadb()
        if not available:
            logger.warning("ChromaDB not installed. Using in-memory fallback.")
            return

        try:
            if self._persist_dir:
                self._client = chromadb.PersistentClient(path=self._persist_dir)
            else:
                self._client = chromadb.Client()

            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("ChromaDB memory initialized: %s", self._collection_name)
        except Exception:
            logger.exception("Failed to initialize ChromaDB")

    async def store(
        self,
        symbol: str,
        situation_text: str,
        signal_direction: str,
        confidence: float,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a market situation in memory.

        Args:
            symbol: Ticker symbol
            situation_text: Description of the market situation
            signal_direction: The signal that was generated
            confidence: Signal confidence
            outcome: Optional — actual outcome (filled in later)
            metadata: Additional context

        Returns:
            Memory entry ID
        """
        entry_id = uuid4().hex
        meta = {
            "symbol": symbol,
            "signal_direction": signal_direction,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        if outcome:
            meta["outcome"] = outcome

        if self._available and self._collection is not None:
            self._collection.add(
                documents=[situation_text],
                metadatas=[meta],
                ids=[entry_id],
            )
        else:
            self._fallback_store.append({
                "id": entry_id,
                "document": situation_text,
                "metadata": meta,
            })

        # Enforce max entries
        await self._enforce_limits()

        return entry_id

    async def query_similar(
        self,
        situation_text: str,
        symbol: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Query for similar historical situations.

        Args:
            situation_text: Current market situation description
            symbol: Optional — filter by symbol
            n_results: Maximum results to return

        Returns:
            List of similar situations with metadata
        """
        if self._available and self._collection is not None:
            where_filter = {"symbol": symbol} if symbol else None
            try:
                results = self._collection.query(
                    query_texts=[situation_text],
                    n_results=n_results,
                    where=where_filter,
                )
                entries = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        distance = results["distances"][0][i] if results["distances"] else 1.0
                        similarity = 1.0 - distance
                        if similarity >= self._similarity_threshold:
                            entries.append({
                                "document": doc,
                                "metadata": meta,
                                "similarity": round(similarity, 3),
                            })
                return entries
            except Exception:
                logger.exception("ChromaDB query failed")
                return []
        else:
            # Fallback: return recent entries (no similarity)
            filtered = self._fallback_store
            if symbol:
                filtered = [e for e in filtered if e["metadata"].get("symbol") == symbol]
            return [
                {"document": e["document"], "metadata": e["metadata"], "similarity": 0.5}
                for e in filtered[-n_results:]
            ]

    async def update_outcome(
        self, entry_id: str, outcome: str, pnl: float | None = None
    ) -> None:
        """Update a memory entry with the actual outcome."""
        if self._available and self._collection is not None:
            try:
                existing = self._collection.get(ids=[entry_id])
                if existing and existing["metadatas"]:
                    meta = existing["metadatas"][0]
                    meta["outcome"] = outcome
                    if pnl is not None:
                        meta["pnl"] = pnl
                    self._collection.update(ids=[entry_id], metadatas=[meta])
            except Exception:
                logger.exception("Failed to update outcome for %s", entry_id)
        else:
            for entry in self._fallback_store:
                if entry["id"] == entry_id:
                    entry["metadata"]["outcome"] = outcome
                    if pnl is not None:
                        entry["metadata"]["pnl"] = pnl
                    break

    async def _enforce_limits(self) -> None:
        """Enforce retention and size limits."""
        if self._available and self._collection is not None:
            count = self._collection.count()
            if count > self._max_entries:
                # Delete oldest entries
                excess = count - self._max_entries
                try:
                    all_items = self._collection.get(limit=excess)
                    if all_items and all_items["ids"]:
                        self._collection.delete(ids=all_items["ids"][:excess])
                except Exception:
                    pass
        else:
            if len(self._fallback_store) > self._max_entries:
                self._fallback_store = self._fallback_store[-self._max_entries:]

    async def prune_expired(self) -> int:
        """Remove entries older than retention_days. Returns count removed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        cutoff_iso = cutoff.isoformat()

        if self._available and self._collection is not None:
            try:
                all_items = self._collection.get()
                if not all_items or not all_items["ids"]:
                    return 0
                expired_ids = []
                for i, meta in enumerate(all_items["metadatas"] or []):
                    ts = meta.get("timestamp", "")
                    if ts and ts < cutoff_iso:
                        expired_ids.append(all_items["ids"][i])
                if expired_ids:
                    self._collection.delete(ids=expired_ids)
                return len(expired_ids)
            except Exception:
                return 0
        else:
            before = len(self._fallback_store)
            self._fallback_store = [
                e for e in self._fallback_store
                if e["metadata"].get("timestamp", "") >= cutoff_iso
            ]
            return before - len(self._fallback_store)

    @property
    def count(self) -> int:
        if self._available and self._collection is not None:
            return self._collection.count()
        return len(self._fallback_store)
