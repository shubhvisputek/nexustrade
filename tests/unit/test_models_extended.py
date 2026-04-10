"""Tests for options models, extended order types, and commodities support."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nexustrade.core.models import (
    OptionContract,
    OptionChain,
    OptionGreeks,
    OptionType,
    Order,
    OrderSide,
    OrderType,
)
from nexustrade.data.commodities import (
    CommoditySymbolResolver,
    FuturesContract,
    RolloverManager,
)


# ---------------------------------------------------------------------------
# Options models
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOptionGreeks:
    def test_creation(self):
        g = OptionGreeks(delta=0.5, gamma=0.03, theta=-0.02, vega=0.15, rho=0.01, iv=0.25)
        assert g.delta == 0.5
        assert g.iv == 0.25

    def test_serialization(self):
        g = OptionGreeks(delta=0.5, gamma=0.03, theta=-0.02, vega=0.15, rho=0.01, iv=0.25)
        d = g.to_dict()
        assert d["delta"] == 0.5
        assert d["iv"] == 0.25
        assert isinstance(d, dict)


@pytest.mark.unit
class TestOptionContract:
    def _make_contract(self, **overrides):
        defaults = dict(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            option_type=OptionType.CALL,
            strike=150.0,
            expiry=datetime(2024, 1, 19, tzinfo=timezone.utc),
            greeks=OptionGreeks(delta=0.6, gamma=0.04, theta=-0.03, vega=0.2, rho=0.01, iv=0.3),
            bid=5.0,
            ask=5.5,
            last=5.25,
            volume=1234.0,
            open_interest=5678.0,
            source="test",
        )
        defaults.update(overrides)
        return OptionContract(**defaults)

    def test_creation(self):
        c = self._make_contract()
        assert c.option_type == OptionType.CALL
        assert c.strike == 150.0
        assert c.greeks is not None
        assert c.greeks.delta == 0.6

    def test_creation_no_greeks(self):
        c = self._make_contract(greeks=None)
        assert c.greeks is None

    def test_option_type_coercion(self):
        c = self._make_contract(option_type="put")
        assert c.option_type == OptionType.PUT

    def test_serialization(self):
        c = self._make_contract()
        d = c.to_dict()
        assert d["option_type"] == "call"
        assert d["greeks"]["delta"] == 0.6
        assert d["expiry"] == "2024-01-19T00:00:00+00:00"


@pytest.mark.unit
class TestOptionChain:
    def test_creation(self):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            option_type=OptionType.CALL,
            strike=150.0,
            expiry=datetime(2024, 1, 19, tzinfo=timezone.utc),
            greeks=None,
            bid=5.0,
            ask=5.5,
            last=5.25,
            volume=100.0,
            open_interest=200.0,
            source="test",
        )
        chain = OptionChain(
            underlying="AAPL",
            expiry=datetime(2024, 1, 19, tzinfo=timezone.utc),
            contracts=[contract],
            timestamp=datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            source="test",
        )
        assert chain.underlying == "AAPL"
        assert len(chain.contracts) == 1

    def test_serialization(self):
        chain = OptionChain(
            underlying="AAPL",
            expiry=datetime(2024, 1, 19, tzinfo=timezone.utc),
            contracts=[],
            timestamp=datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            source="test",
        )
        d = chain.to_dict()
        assert d["underlying"] == "AAPL"
        assert d["contracts"] == []


# ---------------------------------------------------------------------------
# Extended OrderType enum
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrderTypeExtended:
    @pytest.mark.parametrize("member", ["SPREAD", "STRADDLE", "STRANGLE", "IRON_CONDOR"])
    def test_new_option_order_types_exist(self, member):
        assert hasattr(OrderType, member)

    def test_spread_value(self):
        assert OrderType.SPREAD.value == "spread"

    def test_iron_condor_value(self):
        assert OrderType.IRON_CONDOR.value == "iron_condor"


# ---------------------------------------------------------------------------
# Multi-leg Order
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMultiLegOrder:
    def test_single_leg_default(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
        assert order.legs is None

    def test_multi_leg_order(self):
        leg1 = Order(symbol="AAPL240119C00150000", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, price=5.0)
        leg2 = Order(symbol="AAPL240119P00150000", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, price=3.0)
        straddle = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.STRADDLE,
            quantity=1,
            legs=[leg1, leg2],
        )
        assert straddle.legs is not None
        assert len(straddle.legs) == 2
        assert straddle.order_type == OrderType.STRADDLE

    def test_multi_leg_serialization(self):
        leg1 = Order(symbol="X", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, price=1.0)
        parent = Order(symbol="X", side=OrderSide.BUY, order_type=OrderType.SPREAD, quantity=1, legs=[leg1])
        d = parent.to_dict()
        assert len(d["legs"]) == 1
        assert d["legs"][0]["symbol"] == "X"


# ---------------------------------------------------------------------------
# Commodities
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCommoditySymbolResolver:
    def setup_method(self):
        self.resolver = CommoditySymbolResolver()

    def test_resolve_known(self):
        assert self.resolver.resolve("gold") == "GC"
        assert self.resolver.resolve("crude") == "CL"
        assert self.resolver.resolve("silver") == "SI"
        assert self.resolver.resolve("natural_gas") == "NG"

    def test_resolve_case_insensitive(self):
        assert self.resolver.resolve("Gold") == "GC"
        assert self.resolver.resolve("GOLD") == "GC"

    def test_resolve_unknown_passes_through(self):
        assert self.resolver.resolve("ES") == "ES"

    def test_get_front_month_early_in_month(self):
        ref = datetime(2024, 12, 10, tzinfo=timezone.utc)
        result = self.resolver.get_front_month("GC", ref)
        assert result == "GCZ24"  # December 2024

    def test_get_front_month_late_in_month_rolls(self):
        ref = datetime(2024, 11, 20, tzinfo=timezone.utc)
        result = self.resolver.get_front_month("GC", ref)
        assert result == "GCZ24"  # Rolls to December 2024

    def test_get_front_month_december_rolls_to_january(self):
        ref = datetime(2024, 12, 20, tzinfo=timezone.utc)
        result = self.resolver.get_front_month("CL", ref)
        assert result == "CLF25"  # January 2025

    def test_get_continuous(self):
        assert self.resolver.get_continuous("GC") == "GC=F"
        assert self.resolver.get_continuous("CL") == "CL=F"

    def test_month_codes_complete(self):
        assert len(CommoditySymbolResolver.MONTH_CODES) == 12


@pytest.mark.unit
class TestRolloverManager:
    def setup_method(self):
        self.manager = RolloverManager()

    def test_should_roll_true(self):
        expiry = datetime.now(timezone.utc) + __import__("datetime").timedelta(days=3)
        contract = FuturesContract(
            symbol="GCZ24", underlying="GC", expiry=expiry,
            exchange="COMEX", multiplier=100.0, tick_size=0.1,
        )
        assert self.manager.should_roll(contract, days_before_expiry=5) is True

    def test_should_roll_false(self):
        expiry = datetime.now(timezone.utc) + __import__("datetime").timedelta(days=30)
        contract = FuturesContract(
            symbol="GCZ24", underlying="GC", expiry=expiry,
            exchange="COMEX", multiplier=100.0, tick_size=0.1,
        )
        assert self.manager.should_roll(contract, days_before_expiry=5) is False

    def test_get_next_contract(self):
        contract = FuturesContract(
            symbol="GCZ24", underlying="GC",
            expiry=datetime(2024, 12, 15, tzinfo=timezone.utc),
            exchange="COMEX", multiplier=100.0, tick_size=0.1,
        )
        nxt = self.manager.get_next_contract(contract)
        assert nxt.symbol == "GCF25"
        assert nxt.underlying == "GC"
        assert nxt.expiry.month == 1
        assert nxt.expiry.year == 2025
        assert nxt.exchange == "COMEX"
