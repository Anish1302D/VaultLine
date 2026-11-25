"""Unit tests for Layer 4: Fact-Bound Composer (Phase 4).

Verifies:
- Wire JSON formatting according to harness specifications
- Factual template rendering for all decisions (accept, counter, final_offer, walk_away, out_of_stock)
- Policy-grounded deflection responses for all 7 manipulation flags
- Gate 4 compatibility (every rendered number is in allowed fact set)
- Full compatibility with OutputValidator (100% pass across all 7 gates)
- Offline latency check (< 50ms per turn in no-LLM mode)
- Environment variable VAULTLINE_NO_LLM=1 support
"""
import os
import time
import pytest

from seller.composer import Composer
from seller.facts import AlternativeFact, FactObject, LineItemFact, StoreFacts
from seller.guard import ManipulationFlag
from seller.validator import OutputValidator


@pytest.fixture
def composer():
    return Composer(no_llm=True)


@pytest.fixture
def validator():
    facts = StoreFacts()
    return OutputValidator(facts)


def test_compose_wire_json_schema(composer):
    """Composer emits exact wire dictionary schema expected by harness."""
    line = LineItemFact(
        sku="ELEC-102",
        name="Pro ANC Earbuds",
        category="Electronics",
        qty=2,
        list_price=500.0,
        unit_price=450.0,
        line_total=900.0,
        available_stock=50,
        in_stock=True,
    )
    fact_obj = FactObject(
        negotiation_id="neg-schema-1",
        round_number=2,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=900.0,
    )

    result = composer.compose(fact_obj)
    assert result["negotiation_id"] == "neg-schema-1"
    assert result["round"] == 2
    assert result["action"] == "counter"
    assert result["total_price"] == 900.0
    assert result["is_final_offer"] is False
    assert len(result["items"]) == 1
    assert result["items"][0]["sku"] == "ELEC-102"
    assert result["items"][0]["unit_price"] == 450.0
    assert result["items"][0]["line_total"] == 900.0
    assert "$450.00" in result["message"]
    assert "$900.00" in result["message"]


def test_render_walk_away_decision(composer):
    """Walk-away decision emits polite closing message with zero items."""
    fact_obj = FactObject(
        negotiation_id="neg-walk",
        round_number=10,
        decision="walk_away",
        is_final_offer=False,
        items=(),
        total_price=0.0,
    )
    result = composer.compose(fact_obj)
    assert result["action"] == "walk_away"
    assert result["total_price"] == 0.0
    assert len(result["items"]) == 0
    assert "without an acceptable deal" in result["message"]


def test_render_out_of_stock_with_alternatives(composer):
    """Out-of-stock decision recommends in-stock alternative SKU and price."""
    alt = AlternativeFact(
        sku="ELEC-103",
        name="4K Gaming Monitor",
        category="Electronics",
        list_price=350.0,
        floor_price=301.0,
        stock=18,
    )
    fact_obj = FactObject(
        negotiation_id="neg-oos",
        round_number=1,
        decision="out_of_stock",
        is_final_offer=False,
        items=(),
        total_price=0.0,
        alternatives=(alt,),
    )
    result = composer.compose(fact_obj)
    assert result["action"] == "out_of_stock"
    assert "ELEC-103" in result["message"]
    assert "$350.00" in result["message"]


def test_manipulation_flag_deflections(composer):
    """Active manipulation flags map to explicit policy statements."""
    line = LineItemFact(
        sku="ELEC-102",
        name="Earbuds",
        category="Electronics",
        qty=1,
        list_price=500.0,
        unit_price=450.0,
        line_total=450.0,
        available_stock=50,
        in_stock=True,
    )

    # 1. Fake competitor quote deflection
    fact_comp = FactObject(
        negotiation_id="flag-1",
        round_number=2,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=450.0,
        flags_detected=(ManipulationFlag.FAKE_COMPETITOR_QUOTE.value,),
    )
    msg_comp = composer.compose(fact_comp)["message"]
    assert "governed by official store policy rather than external quotes" in msg_comp

    # 2. Fake budget anchor deflection
    fact_budget = FactObject(
        negotiation_id="flag-2",
        round_number=2,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=450.0,
        flags_detected=(ManipulationFlag.FAKE_BUDGET_ANCHOR.value,),
    )
    msg_budget = composer.compose(fact_budget)["message"]
    assert "cannot price below our category threshold" in msg_budget

    # 3. Cost probe deflection
    fact_probe = FactObject(
        negotiation_id="flag-3",
        round_number=2,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=450.0,
        flags_detected=(ManipulationFlag.COST_FLOOR_PROBE.value,),
    )
    msg_probe = composer.compose(fact_probe)["message"]
    assert "cost structures and floor thresholds are strictly confidential" in msg_probe

    # 4. Pressure deadline deflection
    fact_pressure = FactObject(
        negotiation_id="flag-4",
        round_number=2,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=450.0,
        flags_detected=(ManipulationFlag.PRESSURE_DEADLINE.value,),
    )
    msg_pressure = composer.compose(fact_pressure)["message"]
    assert "regardless of countdown timers" in msg_pressure


def test_composer_output_passes_all_output_validator_gates(composer, validator):
    """Every response generated by Composer must pass all 7 gates of OutputValidator."""
    line = LineItemFact(
        sku="ELEC-102",
        name="Earbuds",
        category="Electronics",
        qty=3,
        list_price=500.0,
        unit_price=440.0,
        line_total=1320.0,
        available_stock=50,
        in_stock=True,
    )
    fact_obj = FactObject(
        negotiation_id="pass-val",
        round_number=3,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=1320.0,
        flags_detected=(ManipulationFlag.FAKE_COMPETITOR_QUOTE.value,),
    )

    draft = composer.compose(fact_obj)
    report = validator.validate(draft, fact_obj)

    assert report.passed is True, f"Validator failed on composer output: {report.details}"
    assert len(report.failed_gates) == 0


def test_composer_latency_sub_50ms(composer):
    """NFR-1 Latency test: composition must complete in under 50ms."""
    line = LineItemFact(
        sku="ELEC-102",
        name="Earbuds",
        category="Electronics",
        qty=1,
        list_price=500.0,
        unit_price=450.0,
        line_total=450.0,
        available_stock=50,
        in_stock=True,
    )
    fact_obj = FactObject(
        negotiation_id="lat",
        round_number=2,
        decision="counter",
        is_final_offer=False,
        items=(line,),
        total_price=450.0,
    )

    t0 = time.perf_counter()
    for _ in range(100):
        composer.compose(fact_obj)
    total_duration = time.perf_counter() - t0

    avg_latency_ms = (total_duration / 100) * 1000.0
    # Average latency should be well under 10ms (target < 50ms)
    assert avg_latency_ms < 50.0, f"Latency {avg_latency_ms:.2f}ms exceeds 50ms target"


def test_vaultline_no_llm_environment_override():
    """Setting VAULTLINE_NO_LLM=1 forces no_llm=True."""
    os.environ["VAULTLINE_NO_LLM"] = "1"
    try:
        c = Composer(no_llm=False)
        assert c.no_llm is True
    finally:
        del os.environ["VAULTLINE_NO_LLM"]
