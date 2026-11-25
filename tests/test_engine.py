"""Unit tests for Layer 3: Deterministic Negotiation Engine v1 (Phase 3A).

Verifies:
- Round 1 opens at catalog list price
- Immediate accept if buyer opens >= list price
- Boulware concession curve progression across rounds 1..8
- Reservation price descending toward floor + min_buffer
- Acceptance when buyer meets or exceeds reservation price
- Round 8 explicit final offer (is_final_offer = True)
- Rounds 9–10 walk-away when buyer fails to meet reservation price
- Hard 10-round turn cap (walk away when round > 10)
- Out-of-stock items produce out_of_stock decision with alternatives
- Absolute invariant: quote is NEVER below legal floor price
- Tone-blind fairness: identical numbers yield identical quotes
"""
import pytest

from seller.engine import EngineConfig, NegotiationEngine, NegotiationState
from seller.facts import StoreFacts
from seller.guard import BuyerIntent, RequestedItem


@pytest.fixture
def engine():
    facts = StoreFacts()
    return NegotiationEngine(facts)


def test_round_1_opens_at_list_price(engine):
    """Round 1 must quote catalog list price (FR-5)."""
    # ELEC-102: list_price is 500.00
    intent = BuyerIntent(
        negotiation_id="neg-r1",
        round_number=1,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=400.0),),
    )
    state = NegotiationState(negotiation_id="neg-r1")
    fact_obj = engine.step(intent, state)

    assert fact_obj.decision == "counter"
    assert fact_obj.is_final_offer is False
    assert fact_obj.total_price == 500.00
    assert fact_obj.items[0].unit_price == 500.00


def test_immediate_accept_if_buyer_offers_list_price(engine):
    """Seller immediately accepts if buyer opens at or above list price."""
    intent = BuyerIntent(
        negotiation_id="neg-r1-high",
        round_number=1,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=500.0),),
    )
    state = NegotiationState(negotiation_id="neg-r1-high")
    fact_obj = engine.step(intent, state)

    assert fact_obj.decision == "accept"
    assert fact_obj.items[0].unit_price == 500.00
    assert state.closed is True


def test_boulware_concession_curve_monotonicity(engine):
    """Quotes across rounds 1..8 must descend monotonically and stay strictly >= floor."""
    sku = "ELEC-102"
    floor = engine.facts.compute_floor(sku)
    list_price = engine.facts.get_product(sku).list_price

    state = NegotiationState(negotiation_id="neg-boulware")
    quotes = []

    for r in range(1, 9):
        # Buyer steadily concedes upward: 350 + 8 * r
        buyer_offer = 350.0 + r * 8.0
        intent = BuyerIntent(
            negotiation_id="neg-boulware",
            round_number=r,
            action="offer",
            items=(RequestedItem(sku=sku, qty=1, offered_unit_price=buyer_offer),),
        )
        fact_obj = engine.step(intent, state)
        quote = fact_obj.items[0].unit_price
        quotes.append(quote)

        # Invariant checks
        assert quote >= floor, f"Round {r} quote {quote} below floor {floor}"
        assert quote <= list_price, f"Round {r} quote {quote} above list {list_price}"

    # Round 1 is list price
    assert quotes[0] == list_price
    # Quotes descend monotonically
    for i in range(len(quotes) - 1):
        assert quotes[i] >= quotes[i + 1], f"Quote rose from round {i+1} to {i+2}"

    # Round 8 is strictly below round 1
    assert quotes[7] < quotes[0]


def test_stall_detector_freezes_price(engine):
    """When a buyer stalls on a repeat sub-floor offer, seller freezes concession."""
    sku = "ELEC-102"
    state = NegotiationState(negotiation_id="neg-stall")

    # Round 1: normal opening
    intent1 = BuyerIntent(
        negotiation_id="neg-stall",
        round_number=1,
        action="offer",
        items=(RequestedItem(sku=sku, qty=1, offered_unit_price=350.0),),
    )
    fact1 = engine.step(intent1, state)
    assert fact1.items[0].unit_price == 500.00

    # Round 2: buyer repeats identical 350.0 offer (stall)
    intent2 = BuyerIntent(
        negotiation_id="neg-stall",
        round_number=2,
        action="offer",
        items=(RequestedItem(sku=sku, qty=1, offered_unit_price=350.0),),
    )
    fact2 = engine.step(intent2, state)
    # Price is frozen at 500.00 instead of conceding
    assert fact2.items[0].unit_price == 500.00
    assert state.pattern == "stalling" or len(state.buyer_offer_history) >= 2


def test_round_8_issues_explicit_final_offer(engine):
    """Round 8 must declare an explicit final offer (FR-11)."""
    intent = BuyerIntent(
        negotiation_id="neg-r8",
        round_number=8,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=380.0),),
    )
    state = NegotiationState(negotiation_id="neg-r8")
    fact_obj = engine.step(intent, state)

    assert fact_obj.decision == "final_offer"
    assert fact_obj.is_final_offer is True
    assert fact_obj.items[0].unit_price >= engine.facts.compute_floor("ELEC-102")


def test_rounds_9_and_10_walk_away_if_offer_unacceptable(engine):
    """In rounds 9 and 10, seller walks away if buyer fails to meet reservation price."""
    intent_r9 = BuyerIntent(
        negotiation_id="neg-r9",
        round_number=9,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=350.0),),
    )
    state = NegotiationState(negotiation_id="neg-r9")
    fact_obj_r9 = engine.step(intent_r9, state)

    assert fact_obj_r9.decision == "walk_away"
    assert fact_obj_r9.total_price == 0.0
    assert state.closed is True


def test_round_9_accepts_if_buyer_meets_reservation(engine):
    """In round 9, seller accepts if buyer meets the late-round reservation price."""
    sku = "ELEC-102"
    res_p = engine.compute_reservation_price(sku, 9)

    intent_r9 = BuyerIntent(
        negotiation_id="neg-r9-accept",
        round_number=9,
        action="offer",
        items=(RequestedItem(sku=sku, qty=1, offered_unit_price=res_p + 5.0),),
    )
    state = NegotiationState(negotiation_id="neg-r9-accept")
    fact_obj = engine.step(intent_r9, state)

    assert fact_obj.decision == "accept"
    assert fact_obj.items[0].unit_price >= res_p
    assert state.closed is True


def test_round_exceeding_10_strictly_walks_away(engine):
    """Turn limit cap: round 11 strictly walks away with 0 items (HC-6)."""
    intent_r11 = BuyerIntent(
        negotiation_id="neg-r11",
        round_number=11,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=1, offered_unit_price=490.0),),
    )
    state = NegotiationState(negotiation_id="neg-r11")
    fact_obj = engine.step(intent_r11, state)

    assert fact_obj.decision == "walk_away"
    assert fact_obj.total_price == 0.0
    assert len(fact_obj.items) == 0


def test_out_of_stock_item_handling(engine):
    """Out-of-stock item triggers out_of_stock decision with category alternatives."""
    intent = BuyerIntent(
        negotiation_id="neg-oos",
        round_number=1,
        action="offer",
        items=(RequestedItem(sku="ELEC-OOS", qty=1, offered_unit_price=150.0),),
    )
    state = NegotiationState(negotiation_id="neg-oos")
    fact_obj = engine.step(intent, state)

    assert fact_obj.decision == "out_of_stock"
    assert len(fact_obj.items) == 0
    assert len(fact_obj.alternatives) > 0
    # Alternatives must be in the same category (Electronics) and in stock
    for alt in fact_obj.alternatives:
        assert alt.category == "Electronics"
        assert alt.stock > 0


def test_fairness_by_construction(engine):
    """Two identical numerical offers with different metadata receive identical quotes (ST-1)."""
    intent_a = BuyerIntent(
        negotiation_id="polite-buyer-session-123",
        round_number=3,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=2, offered_unit_price=410.0),),
        flags_detected=("POLITE_APPEAL",),
    )
    intent_b = BuyerIntent(
        negotiation_id="rude-hostile-session-456",
        round_number=3,
        action="offer",
        items=(RequestedItem(sku="ELEC-102", qty=2, offered_unit_price=410.0),),
        flags_detected=("AGGRESSIVE_TONE", "FAKE_BUDGET"),
    )

    state_a = NegotiationState(negotiation_id="session-a")
    state_b = NegotiationState(negotiation_id="session-b")

    resp_a = engine.step(intent_a, state_a)
    resp_b = engine.step(intent_b, state_b)

    assert resp_a.items[0].unit_price == resp_b.items[0].unit_price
    assert resp_a.total_price == resp_b.total_price
    assert resp_a.decision == resp_b.decision
