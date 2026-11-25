"""Milestone M1 Verification Suite & Phase 5A Buyer Integration.

Verifies:
- CooperativeLLMBuyer and HardLLMBuyer behavior
- Complete multi-round negotiations between VaultLine SellerAgent and 5 buyer bots:
  1. CooperativeStarterBuyer
  2. LinearStarterBuyer
  3. ToughStarterBuyer
  4. CooperativeLLMBuyer
  5. HardLLMBuyer
- Milestone M1 Exit Criteria:
  - 100% Policy Compliance: Exactly 0 policy violations (HC-1, HC-2, HC-3, HC-6)
  - Every agreed price is strictly >= legal floor price
  - Every closed deal respects stock availability
  - Max rounds capped at 10
"""
from pathlib import Path
import pytest

from buyers import (
    CooperativeLLMBuyer,
    CooperativeStarterBuyer,
    HardLLMBuyer,
    LinearStarterBuyer,
    ToughStarterBuyer,
)
from evaluate import audit_transcript, evaluate_transcripts, load_catalog, load_policy
from harness import run_single_negotiation
from seller.agent import SellerAgent
from seller.facts import StoreFacts


@pytest.fixture
def store_facts():
    return StoreFacts()


@pytest.fixture
def seller_agent(store_facts):
    return SellerAgent(facts=store_facts)


def test_cooperative_llm_buyer_closes_deal_with_seller(seller_agent, store_facts):
    """Cooperative LLM buyer negotiates and closes a profitable deal with SellerAgent."""
    sku = "ELEC-102"  # List: 500, Floor: 430.01
    prod = store_facts.get_product(sku)
    buyer = CooperativeLLMBuyer(use_simulation=True)

    transcript = run_single_negotiation(
        seller_agent=seller_agent,
        buyer_agent=buyer,
        sku=sku,
        qty=1,
        list_price=prod.list_price,
        cost=prod.cost,
        buyer_persona="cooperative_llm",
        seller_type="vaultline_v1",
    )

    assert transcript.closed is True, "Cooperative negotiation should successfully close"
    assert transcript.agreed_price is not None
    # Agreed price must be strictly >= legal floor
    floor = store_facts.compute_floor(sku)
    assert transcript.agreed_price >= floor, f"Agreed price {transcript.agreed_price} must be >= floor {floor}"
    assert transcript.rounds <= 10


def test_hard_llm_buyer_stall_and_resolution(seller_agent, store_facts):
    """Hard LLM buyer anchors low, stalls, and resolves cleanly without policy violations."""
    sku = "ELEC-102"
    prod = store_facts.get_product(sku)
    buyer = HardLLMBuyer(use_simulation=True)

    transcript = run_single_negotiation(
        seller_agent=seller_agent,
        buyer_agent=buyer,
        sku=sku,
        qty=1,
        list_price=prod.list_price,
        cost=prod.cost,
        buyer_persona="hard_llm",
        seller_type="vaultline_v1",
    )

    # In either outcome (deal closed or polite walk-away), rounds must be <= 10
    assert transcript.rounds <= 10
    if transcript.closed and transcript.agreed_price is not None:
        floor = store_facts.compute_floor(sku)
        assert transcript.agreed_price >= floor


def test_milestone_m1_zero_violations_across_all_buyers(seller_agent, store_facts):
    """Milestone M1 Gate: Runs negotiations across all 5 buyer bots and asserts 0 violations."""
    root_dir = Path(__file__).resolve().parent.parent
    catalog = load_catalog(root_dir / "data" / "store.csv")
    policy = load_policy(root_dir / "data" / "policy.json")

    buyers = [
        ("cooperative_starter", CooperativeStarterBuyer()),
        ("linear_starter", LinearStarterBuyer()),
        ("tough_starter", ToughStarterBuyer()),
        ("cooperative_llm", CooperativeLLMBuyer(use_simulation=True)),
        ("hard_llm", HardLLMBuyer(use_simulation=True)),
    ]

    test_skus = ["ELEC-101", "ELEC-102", "HOME-201", "OFF-301", "ACC-401"]
    transcripts = []

    for sku in test_skus:
        prod = catalog[sku]
        for name, buyer in buyers:
            # Create fresh seller instance per session
            seller = SellerAgent(facts=store_facts)
            t = run_single_negotiation(
                seller_agent=seller,
                buyer_agent=buyer,
                sku=sku,
                qty=1,
                list_price=prod["list_price"],
                cost=prod["cost"],
                buyer_persona=name,
                seller_type="vaultline_v1",
            )
            transcripts.append(t)

    metrics = evaluate_transcripts(transcripts, catalog, policy)

    # MILESTONE M1 PASS CRITERIA:
    # 1. Total policy violations must be strictly 0
    assert metrics.policy_violations == 0, (
        f"Milestone M1 Failed: {metrics.policy_violations} policy violations logged!\n"
        f"Details: {metrics.violation_details}"
    )

    # 2. Deals must close successfully
    assert metrics.deals_closed > 0, "At least some negotiations must successfully close"

    # 3. Average margin realized must be positive and healthy
    assert metrics.average_margin_percent > 15.0, (
        f"Average margin {metrics.average_margin_percent:.2f}% is too low"
    )

    # 4. Turn limit respected across all sessions
    for t in transcripts:
        assert t.rounds <= 10
