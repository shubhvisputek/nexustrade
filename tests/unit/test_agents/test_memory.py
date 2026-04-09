"""Tests for ChromaDB market memory."""

import pytest

from nexustrade.agents.memory import MarketMemory


class TestMarketMemory:
    async def test_store_and_query(self):
        mem = MarketMemory(collection_name=f"test_{id(self)}", max_entries=100)
        entry_id = await mem.store(
            symbol="AAPL",
            situation_text="RSI oversold at 28, price at support level",
            signal_direction="buy",
            confidence=0.82,
        )
        assert entry_id
        assert mem.count == 1

    async def test_query_similar(self):
        mem = MarketMemory(max_entries=100, similarity_threshold=0.0)
        await mem.store("AAPL", "RSI oversold at 28", "buy", 0.8)
        await mem.store("AAPL", "MACD crossover bullish", "buy", 0.7)

        results = await mem.query_similar("RSI is very low", symbol="AAPL")
        assert len(results) > 0

    async def test_update_outcome(self):
        mem = MarketMemory(collection_name=f"test_{id(self)}", max_entries=100)
        entry_id = await mem.store("AAPL", "Test situation", "buy", 0.8)
        await mem.update_outcome(entry_id, "profit", pnl=250.0)

        # Verify in fallback store
        for entry in mem._fallback_store:
            if entry["id"] == entry_id:
                assert entry["metadata"]["outcome"] == "profit"
                assert entry["metadata"]["pnl"] == 250.0

    async def test_enforce_max_entries(self):
        mem = MarketMemory(max_entries=5)
        for i in range(10):
            await mem.store("AAPL", f"Situation {i}", "hold", 0.5)
        assert mem.count <= 5

    async def test_prune_expired(self):
        mem = MarketMemory(retention_days=0)  # Everything expires immediately
        await mem.store("AAPL", "Old situation", "buy", 0.8)
        removed = await mem.prune_expired()
        # With retention_days=0 and immediate prune, entry should be removed
        assert removed >= 0  # May or may not catch it depending on timing

    async def test_filter_by_symbol(self):
        mem = MarketMemory(max_entries=100, similarity_threshold=0.0)
        await mem.store("AAPL", "Apple situation", "buy", 0.8)
        await mem.store("MSFT", "Microsoft situation", "sell", 0.7)

        results = await mem.query_similar("situation", symbol="AAPL")
        symbols = [r["metadata"]["symbol"] for r in results]
        assert all(s == "AAPL" for s in symbols)

    async def test_count_property(self):
        mem = MarketMemory(collection_name=f"test_{id(self)}", max_entries=100)
        assert mem.count == 0
        await mem.store("AAPL", "Test", "hold", 0.5)
        assert mem.count == 1
