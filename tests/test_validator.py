"""Unit tests for OutputValidator (Layer 5: Independent 7-Gate Verifier).

Verifies:
- All 7 gates pass on compliant draft responses
- Interception of Gate 1: Below-floor prices (e.g. $0.01 below floor)
- Interception of Gate 2: Discounts exceeding category max
- Interception of Gate 3: Out-of-stock items and quantity > stock
- Interception of Gate 4: Hallucinated numbers in natural-language prose
- Interception of Gate 5: Banned scarcity, pressure, and hidden fee phrases
- Interception of Gate 6: Arithmetic mismatch between unit_price, qty, line_total, and total_price
- Interception of Gate 7: Leaking confidential cost or secret floor phrases
- Deterministic Safe Fallback: Guaranteed 100% compliance of recovered responses
"""
import pytest

from seller.facts import StoreFacts
from seller.validator import OutputValidator


@pytest.fixture
def validator():
    facts = StoreFacts()
    return OutputValidator(facts)


def test_valid_response_passes_all_gates(validator):
    """A clean, policy-compliant response passes all 7 gates."""
    # ELEC-102: cost 300, list 500, floor 430.01
    draft = {
        "negotiation_id": "test-1",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-102",
                "name": "Pro ANC Earbuds",
                "qty": 2,
                "unit_price": 450.00,
                "line_total": 900.00,
            }
        ],
        "total_price": 900.00,
        "message": "We can offer 2 units at $450.00 each for a total of $900.00 in round 2.",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is True
    assert len(report.failed_gates) == 0


def test_gate_1_interception_below_floor_price(validator):
    """Gate 1 must catch any price below legal floor and apply safe fallback."""
    # ELEC-101: floor is 500.01
    # Draft offers $499.00 (below floor)
    draft = {
        "negotiation_id": "test-gate1",
        "round": 3,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-101",
                "name": "Ultra Wireless Headphones",
                "qty": 1,
                "unit_price": 499.00,
                "line_total": 499.00,
            }
        ],
        "total_price": 499.00,
        "message": "Special counteroffer: $499.00.",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is False
    assert OutputValidator.GATE_1_FLOOR in report.failed_gates

    # Test validate_and_fix fallback recovery
    fixed_response, fix_report = validator.validate_and_fix(draft)
    assert fix_report.fallback_applied is True
    # Recovered price must be >= floor (500.01)
    recovered_price = fixed_response["items"][0]["unit_price"]
    assert recovered_price >= 500.01
    # And recovered response must pass validator
    post_check = validator.validate(fixed_response)
    assert post_check.passed is True


def test_gate_2_interception_excessive_discount(validator):
    """Gate 2 must catch any discount exceeding category maximum discount."""
    # Electronics max discount is 0.14 (14%)
    # ELEC-102 list is 500. 20% discount would be $400.00 (max allowed is $430.00)
    draft = {
        "negotiation_id": "test-gate2",
        "round": 4,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-102",
                "name": "Pro ANC Earbuds",
                "qty": 1,
                "unit_price": 400.00,
                "line_total": 400.00,
            }
        ],
        "total_price": 400.00,
        "message": "Offering 20% discount at $400.00.",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is False
    assert OutputValidator.GATE_2_DISCOUNT in report.failed_gates


def test_gate_3_interception_out_of_stock_and_overflow(validator):
    """Gate 3 must catch offers selling out-of-stock items or exceeding available inventory."""
    # ELEC-OOS has stock 0
    oos_draft = {
        "negotiation_id": "test-oos",
        "round": 1,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-OOS",
                "name": "Smart Speaker",
                "qty": 1,
                "unit_price": 180.00,
                "line_total": 180.00,
            }
        ],
        "total_price": 180.00,
        "message": "Offering $180.00.",
        "is_final_offer": False,
    }
    report = validator.validate(oos_draft)
    assert report.passed is False
    assert OutputValidator.GATE_3_STOCK in report.failed_gates

    # Recovered response should switch to out_of_stock action with an alternative
    fixed, fix_report = validator.validate_and_fix(oos_draft)
    assert fixed["action"] == "out_of_stock"
    assert "out of stock" in fixed["message"].lower()

    # Inventory overflow: ELEC-101 has stock 25; offer asks for 30
    overflow_draft = {
        "negotiation_id": "test-overflow",
        "round": 1,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-101",
                "name": "Headphones",
                "qty": 30,
                "unit_price": 500.00,
                "line_total": 15000.00,
            }
        ],
        "total_price": 15000.00,
        "message": "Offering 30 units at $500.00 each for $15000.00.",
        "is_final_offer": False,
    }
    report_overflow = validator.validate(overflow_draft)
    assert report_overflow.passed is False
    assert OutputValidator.GATE_3_STOCK in report_overflow.failed_gates


def test_gate_4_interception_hallucinated_prose_numbers(validator):
    """Gate 4 must intercept hallucinated numbers in prose that are not in the allowed fact set."""
    # Stated item price is $450.00, but message hallucinates "$299.99"
    draft = {
        "negotiation_id": "test-gate4",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-102",
                "name": "Earbuds",
                "qty": 1,
                "unit_price": 450.00,
                "line_total": 450.00,
            }
        ],
        "total_price": 450.00,
        "message": "Today only, take it for $299.99 instead of $450.00!",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is False
    assert OutputValidator.GATE_4_FACT_NUMBERS in report.failed_gates
    assert any("299.99" in d for d in report.details)

    # Recovery replaces prose with fact-bound template
    fixed, fix_report = validator.validate_and_fix(draft)
    assert fix_report.fallback_applied is True
    assert "299.99" not in fixed["message"]
    post_check = validator.validate(fixed)
    assert post_check.passed is True


def test_gate_5_interception_banned_phrases(validator):
    """Gate 5 must intercept banned pressure, urgency, or scarcity phrases."""
    draft = {
        "negotiation_id": "test-gate5",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-102",
                "name": "Earbuds",
                "qty": 1,
                "unit_price": 450.00,
                "line_total": 450.00,
            }
        ],
        "total_price": 450.00,
        "message": "We have only 1 left! Act now or lose this price.",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is False
    assert OutputValidator.GATE_5_BANNED_PHRASES in report.failed_gates

    # Recovery removes banned phrases
    fixed, _ = validator.validate_and_fix(draft)
    assert "only 1 left" not in fixed["message"].lower()
    assert "act now" not in fixed["message"].lower()


def test_gate_6_interception_arithmetic_mismatch(validator):
    """Gate 6 must intercept mathematical discrepancies in line totals and totals."""
    # 2 units @ $450.00 should be $900.00, but line_total is given as $850.00
    draft = {
        "negotiation_id": "test-gate6",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-102",
                "name": "Earbuds",
                "qty": 2,
                "unit_price": 450.00,
                "line_total": 850.00,  # Math error!
            }
        ],
        "total_price": 850.00,
        "message": "Offer for 2 units at $450.00 with line total $850.00.",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is False
    assert OutputValidator.GATE_6_EXACT_MATH in report.failed_gates

    # Fallback fixes arithmetic
    fixed, _ = validator.validate_and_fix(draft)
    assert fixed["items"][0]["line_total"] == round(fixed["items"][0]["unit_price"] * 2, 2)
    assert fixed["total_price"] == fixed["items"][0]["line_total"]


def test_gate_7_interception_confidentiality_cost_leak(validator):
    """Gate 7 must intercept leaking unit cost or secret floor phrases."""
    # ELEC-101 has cost 420.00
    draft = {
        "negotiation_id": "test-gate7",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-101",
                "name": "Headphones",
                "qty": 1,
                "unit_price": 500.00,
                "line_total": 500.00,
            }
        ],
        "total_price": 500.00,
        "message": "We cannot go lower because our cost is $420.00 per unit.",
        "is_final_offer": False,
    }
    report = validator.validate(draft)
    assert report.passed is False
    assert OutputValidator.GATE_7_NO_LEAKS in report.failed_gates

    # Test floor phrase detection
    draft_floor_phrase = {
        "negotiation_id": "test-gate7-floor",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-101",
                "name": "Headphones",
                "qty": 1,
                "unit_price": 500.00,
                "line_total": 500.00,
            }
        ],
        "total_price": 500.00,
        "message": "Our floor price is set by management.",
        "is_final_offer": False,
    }
    report_phrase = validator.validate(draft_floor_phrase)
    assert report_phrase.passed is False
    assert OutputValidator.GATE_7_NO_LEAKS in report_phrase.failed_gates


def test_fallback_guarantees_zero_violations_on_all_failures(validator):
    """Any draft failing any combination of gates must be recovered to a 100% compliant response."""
    # Synthetic catastrophically corrupted payload (fails almost every gate)
    corrupted_draft = {
        "negotiation_id": "test-catastrophe",
        "round": 2,
        "action": "counter",
        "items": [
            {
                "sku": "ELEC-101",
                "name": "Headphones",
                "qty": 50,  # Exceeds stock (25)
                "unit_price": 300.00,  # Below floor ($500.01) & below cost ($420.00)
                "line_total": 1000.00,  # Math error (300 * 50 != 1000)
            }
        ],
        "total_price": 999.00,  # Total mismatch
        "message": "Hurry, only 1 left! Our unit cost is $420.00 and price is $99.99 right now!",
        "is_final_offer": False,
    }
    report = validator.validate(corrupted_draft)
    assert report.passed is False
    assert len(report.failed_gates) >= 5

    # Safe fallback recovery
    fixed, fix_report = validator.validate_and_fix(corrupted_draft)
    assert fix_report.fallback_applied is True

    # Post-check: the recovered response MUST pass all gates with 0 errors
    post_check = validator.validate(fixed)
    assert post_check.passed is True
    assert len(post_check.failed_gates) == 0
    assert fixed["items"][0]["unit_price"] >= 500.01
    assert fixed["items"][0]["qty"] <= 25
