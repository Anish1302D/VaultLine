"""Unit tests for Layer 3: Engine v2 Multi-SKU Bundles & Volume Tiers (Phase 3B).

Verifies:
- Multi-SKU bundle discount application (3% bundle discount for len(items) > 1)
- Volume tier discounts (qty >= 3: 2%, qty >= 5: 4%, qty >= 10: 7%)
- Combined volume + bundle discounts
- Strict independent line-item floor clamping (HC-1, FR-9: no cross-item subsidies)
- Cumulative stock aggregation across duplicate lines in bundles (HC-3)
- Out-of-stock resolution in bundles with alternatives
- Bundle acceptance criteria based on bundle reservation and floor totals
- Total price arithmetic exactness across all line items
"""
import pytest

from seller.engine import EngineConfig, NegotiationEngine, NegotiationState
from seller.facts import StoreFacts
from seller.guard import BuyerIntent, RequestedItem


@pytest.fixture
def engine():
    facts = StoreFacts()
    return NegotiationEngine(facts)


def test_volume_tier_discounts(engine):
    """Verify volume tier discount percentages according to store policy."""
    assert engine.compute_volume_discount("ELEC-102", 1) == 0.0
    assert engine.compute_volume_discount("ELEC-102", 2) == 0.0
    assert engine.compute_volume_discount("ELEC-102", 3) == 0.02
    assert engine.compute_volume_discount("ELEC-102", 4) == 0.02
    assert engine.compute_volume_discount("ELEC-102", 5) == 0.04
    assert engine.compute_volume_discount("ELEC-102", 9) == 0.04
    assert engine.compute_volume_discount("ELEC-102", 10) == 0.07
    assert engine.compute_volume_discount("ELEC-102", 20) == 0.07


def test_multi_sku_bundle_receives_bundle_discount(engine):
    """Multi-item bundle receives bundle discount (3%) on rounds >= 2."""
    state = NegotiationState(negotiation_id="bundle-disc")
    # Single item quote at round 3
    single_intent = BuyerIntent(
        negotiation_id="single",
        round_number=3,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=440.0),),
    )
    fact_single = engine.step(single_intent, NegotiationState("single"))
    single_quote = fact_single.items[0].unit_price

    # Multi-item bundle quote at round 3 (ELEC-102 + HOME-201)
    bundle_intent = BuyerIntent(
        negotiation_id="bundle",
        round_number=3,
        action="offer",
        items=(
            RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=440.0),
            RequestedItem(sku="HOME-201", qty=1, offered_unit_price=280.0),
        ),
    )
    fact_bundle = engine.step(bundle_intent, NegotiationState("bundle"))
    bundle_elec102_quote = fact_bundle.items[0].unit_price

    # Bundle quote should be discounted by ~3% compared to single quote (bounded by floor)
    floor = engine.facts.compute_floor("ELEC-102")
    assert bundle_elec102_quote >= floor
    assert bundle_elec102_quote <= single_quote


def test_combined_bundle_and_volume_discount(engine):
    """Bundle item with qty >= 5 gets combined 4% volume + 3% bundle discount (7% total)."""
    state = NegotiationState(negotiation_id="bundle-vol")
    bundle_intent = BuyerIntent(
        negotiation_id="bundle-vol",
        round_number=3,
        action="offer",
        items=(
            RequestedItem(sku="ELEC-102", qty=5, offered_unit_price=440.0),
            RequestedItem(sku="ACC-401", qty=1, offered_unit_price=40.0),
        ),
    )
    fact_bundle = engine.step(bundle_intent, state)
    elec_line = fact_bundle.items[0]

    floor = engine.facts.compute_floor("ELEC-102")
    base_p = engine.compute_concession_price("ELEC-102", 3)
    # Expected discount = 4% + 3% = 7%
    expected_unit = round(base_p * (1.0 - 0.07), 2)
    expected_clamped = max(floor, expected_unit)

    assert elec_line.unit_price == expected_clamped
    assert elec_line.line_total == round(expected_clamped * 5, 2)


def test_independent_floor_clamping_prevents_subsidies(engine):
    """In a bundle with margin-dominated item (ELEC-101), price is clamped to floor."""
    # ELEC-101: cost 420.00, list 500.00, min_margin 0.16 -> floor is 500.01!
    # Even in a bundle with 7% volume+bundle discount, ELEC-101 MUST be clamped to 500.01!
    state = NegotiationState(negotiation_id="bundle-clamp")
    bundle_intent = BuyerIntent(
        negotiation_id="bundle-clamp",
        round_number=5,
        action="offer",
        items=(
            RequestedItem(sku="ELEC-101", qty=5, offered_unit_price=450.0),
            RequestedItem(sku="ACC-401", qty=10, offered_unit_price=30.0),
        ),
    )
    fact = engine.step(bundle_intent, state)
    elec101_line = fact.items[0]

    # Must be clamped strictly to its floor of 500.01 (cannot drop below)
    assert elec101_line.unit_price == 500.01
    assert elec101_line.line_total == round(500.01 * 5, 2)


def test_bundle_stock_aggregation_overflow(engine):
    """Duplicate lines for same SKU in bundle are summed; overflow triggers out_of_stock."""
    # ELEC-101 has stock 25
    # Buyer requests 15 units + 12 units = 27 units total
    intent = BuyerIntent(
        negotiation_id="overflow-bundle",
        round_number=1,
        action="offer",
        items=(
            RequestedItem(sku="ELEC-101", qty=15, offered_unit_price=490.0),
            RequestedItem(sku="ELEC-101", qty=12, offered_unit_price=490.0),
        ),
    )
    state = NegotiationState("overflow-bundle")
    fact = engine.step(intent, state)

    assert fact.decision == "out_of_stock"
    assert len(fact.items) == 0
    assert len(fact.alternatives) > 0


def test_bundle_immediate_acceptance_on_fair_total(engine):
    """Seller immediately accepts bundle when buyer offers >= bundle reservation total."""
    sku1 = "ELEC-102"  # floor 430.01, list 500
    sku2 = "HOME-201"  # floor ~269.24, list 320
    qty1, qty2 = 2, 1

    res1 = engine.compute_reservation_price(sku1, 3)
    res2 = engine.compute_reservation_price(sku2, 3)
    bundle_res_total = round(res1 * qty1 + res2 * qty2, 2)

    intent = BuyerIntent(
        negotiation_id="bundle-accept",
        round_number=3,
        action="offer",
        items=(
            RequestedItem(sku=sku1, qty=qty1, offered_unit_price=res1 + 5.0),
            RequestedItem(sku=sku2, qty=qty2, offered_unit_price=res2 + 5.0),
        ),
        offered_total=bundle_res_total + 15.0,
    )
    state = NegotiationState("bundle-accept")
    fact = engine.step(intent, state)

    assert fact.decision == "accept"
    assert state.closed is True
    assert len(fact.items) == 2
    # Verify exact math
    assert fact.total_price == round(
        fact.items[0].line_total + fact.items[1].line_total, 2
    )


def test_bundle_exact_arithmetic_invariants(engine):
    """Every bundle line total == unit_price * qty and total == sum(line_totals)."""
    intent = BuyerIntent(
        negotiation_id="bundle-math",
        round_number=4,
        action="offer",
        items=(
            RequestedItem(sku="ELEC-102", qty=3, offered_unit_price=420.0),
            RequestedItem(sku="OFF-301", qty=5, offered_unit_price=220.0),
            RequestedItem(sku="ACC-401", qty=10, offered_unit_price=35.0),
        ),
    )
    state = NegotiationState("bundle-math")
    fact = engine.step(intent, state)

    assert fact.decision == "counter"
    sum_lines = 0.0
    for line in fact.items:
        expected_line = round(line.unit_price * line.qty, 2)
        assert line.line_total == expected_line
        sum_lines += expected_line

    assert fact.total_price == round(sum_lines, 2)
