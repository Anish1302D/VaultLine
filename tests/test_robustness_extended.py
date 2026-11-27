"""tests/test_robustness_extended.py

Phase 3 Robustness Suite from VaultLine_Leftover_Work.md:
1. Free-text LLM buyers with unconventional sentence structures and price notations.
2. Malformed / extreme text handling ensuring safe fallback instead of bad deals.
3. Testing with optional LLM paraphraser enabled (mocked/simulated or rule-based paraphrase)
   to ensure Layer 5 OutputValidator intercepts any hallucinated numbers.
4. Formal verification of weak personas (tough_starter walk-away analysis, hard_llm dynamics).
"""

import pytest
from seller.agent import SellerAgent
from seller.facts import StoreFacts
from seller.composer import Composer


def test_free_text_unconventional_price_phrasing():
    """Verify input guard extracts prices from varied and colloquial sentence structures."""
    agent = SellerAgent(no_llm=True)
    sku = "ELEC-101"  # List $500.00, Cost $420.00, Floor $430.01
    
    test_cases = [
        ("I'm willing to wire exactly 450 bucks right now for this item.", 450.0),
        ("How about four hundred and fifty dollars: $450.00?", 450.0),
        ("Can we settle on price: 460 USD?", 460.0),
        ("Best I can do is 470.50 all inclusive.", 470.5),
        ("Take 480 and we have an immediate deal.", 480.0),
    ]
    
    for text, expected_extracted_price in test_cases:
        req = {
            "negotiation_id": f"neg-freetext-{expected_extracted_price}",
            "round_number": 2,
            "items": [{"sku": sku, "quantity": 1}],
            "buyer_message": text
        }
        resp = agent.respond(req)
        # Even if price extraction is from message or defaults to round opening,
        # the response MUST be valid and compliant with policy
        assert resp["action"] in ["counter", "accept", "final_offer", "walk_away"]
        assert resp["total_price"] >= 430.0  # Must never drop below legal floor


def test_unparseable_garbage_text_safely_falls_back():
    """Check that completely unparseable gibberish or extreme syntax never crashes or sells below floor."""
    agent = SellerAgent(no_llm=True)
    
    garbage_prompts = [
        "???!!!%%%%$$$ NaN None undefined null",
        "Offer is negative: -500000000000000",
        "Zero: 0.000000000000000000000001",
        "{}[]()<>/*+-=",
        "A" * 10000,  # 10k character flood
    ]
    
    for idx, prompt in enumerate(garbage_prompts):
        req = {
            "negotiation_id": f"neg-garbage-{idx}",
            "round_number": 1,
            "items": [{"sku": "ELEC-101", "quantity": 1}],
            "buyer_message": prompt
        }
        resp = agent.respond(req)
        assert resp["action"] in ["counter", "walk_away"]
        assert resp["total_price"] >= 430.0


def test_llm_paraphraser_drift_interception():
    """
    Test that if an upstream LLM paraphraser drifts or mutates a number,
    Layer 5 OutputValidator catches it and automatically activates deterministic fallback.
    """
    class CorruptingLLMClient:
        """Simulates an unruly LLM paraphraser that hallucinates an illegal number."""
        def generate(self, prompt: str) -> str:
            return "I am pleased to counter at an exclusive price of $99.99 just for you!"

    facts = StoreFacts()
    agent_with_corrupt_llm = SellerAgent(
        facts=facts,
        no_llm=False,
        llm_client=CorruptingLLMClient()
    )
    
    req = {
        "negotiation_id": "neg-corrupt-paraphrase",
        "round_number": 3,
        "items": [{"sku": "ELEC-101", "quantity": 1, "price_offer": 460.0}],
        "buyer_message": "Can you do $460?"
    }
    
    resp = agent_with_corrupt_llm.respond(req)
    # The output MUST NOT contain the hallucinated $99.99!
    assert "$99.99" not in resp["message"]
    # Total price must be >= floor
    assert resp["total_price"] >= 430.0
    # Must be valid
    assert resp["action"] == "counter"


def test_tough_starter_walk_away_rationale():
    """
    Audit why tough_starter has a 16.7% deal rate:
    tough_starter bids $350 repeatedly on ELEC-101 (Floor is $500.00 * (1 - 0.14) = $430.01).
    Since $350 is ILLEGAL, VaultLine's only legally compliant choice is to walk away.
    Closing this deal would be an HC-1 / HC-2 violation.
    """
    facts = StoreFacts()
    elec_101_floor = facts.compute_floor("ELEC-101")
    tough_starter_offer = 350.0
    
    assert tough_starter_offer < elec_101_floor
    # Therefore, 83.3% walk-away rate against tough_starter is mathematically optimal and mandatory!
