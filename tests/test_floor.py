"""Unit tests for StoreFacts, floor calculations, stock checks, and alternatives.

Verifies:
- Dual-constraint floor calculation (margin-on-price vs discount ceiling)
- Upward ceiling rounding and epsilon safety buffer
- Margin-dominated vs discount-dominated SKU behavior
- Boundary cases: min_margin=0, max_discount=0, stock=0
- Single item and bundle stock aggregation
- Alternative product lookup and budget filtering
- Immutability of fact objects
"""
import math
from pathlib import Path
import pytest

from seller.facts import (
    AlternativeFact,
    CategoryPolicy,
    ProductFact,
    StoreFacts,
)


@pytest.fixture
def store_facts():
    return StoreFacts()


def test_immutable_data_models():
    """Verify that ProductFact and CategoryPolicy are frozen dataclasses."""
    prod = ProductFact(
        sku="TEST-1",
        name="Test",
        category="Electronics",
        cost=100.0,
        list_price=150.0,
        stock=10,
    )
    with pytest.raises(Exception):
        prod.cost = 90.0  # type: ignore

    policy = CategoryPolicy(
        category="Electronics",
        min_margin=0.15,
        max_discount=0.10,
    )
    with pytest.raises(Exception):
        policy.min_margin = 0.20  # type: ignore


def test_every_catalog_sku_floor_satisfies_policy(store_facts):
    """Every SKU's computed floor must satisfy both min_margin and max_discount."""
    for sku in store_facts.get_all_skus():
        prod = store_facts.get_product(sku)
        policy = store_facts.get_category_policy(prod.category)
        floor = store_facts.compute_floor(sku)

        # 1. Floor must be strictly positive
        assert floor > 0, f"Floor must be positive for {sku}"

        # 2. Floor must be >= cost
        assert floor >= prod.cost, f"Floor {floor} must be >= cost {prod.cost} for {sku}"

        # 3. Margin check: (floor - cost) / floor >= min_margin
        actual_margin = (floor - prod.cost) / floor
        assert actual_margin >= (policy.min_margin - 1e-4), (
            f"Floor {floor} violates min_margin {policy.min_margin} for {sku} (margin={actual_margin})"
        )

        # 4. Discount check: (list_price - floor) / list_price <= max_discount
        actual_discount = (prod.list_price - floor) / prod.list_price
        assert actual_discount <= (policy.max_discount + 1e-4), (
            f"Floor {floor} violates max_discount {policy.max_discount} for {sku} (discount={actual_discount})"
        )


def test_margin_dominated_sku(store_facts):
    """ELEC-101: Cost=420, List=500, min_margin=0.16, max_discount=0.14.

    Margin floor = 420 / 0.84 = 500.00
    Discount floor = 500 * (1 - 0.14) = 430.00
    Raw floor = 500.00 (margin dominated).
    Safe floor = 500.00 + 0.01 = 500.01
    """
    prod = store_facts.get_product("ELEC-101")
    assert prod.cost == 420.0
    assert prod.list_price == 500.0

    floor = store_facts.compute_floor("ELEC-101")
    # Because margin floor is 500.00 and epsilon is 0.01, floor must be 500.01
    assert floor == 500.01


def test_discount_dominated_sku(store_facts):
    """ELEC-102: Cost=300, List=500, min_margin=0.16, max_discount=0.14.

    Margin floor = 300 / 0.84 = 357.1428...
    Discount floor = 500 * 0.86 = 430.00
    Raw floor = 430.00 (discount dominated).
    Safe floor = 430.00 + 0.01 = 430.01
    """
    prod = store_facts.get_product("ELEC-102")
    assert prod.cost == 300.0
    assert prod.list_price == 500.0

    floor = store_facts.compute_floor("ELEC-102")
    assert floor == 430.01


def test_upward_ceiling_rounding_and_epsilon(store_facts):
    """Verify that ceiling rounding never drops below theoretical raw floor."""
    for sku in store_facts.get_all_skus():
        prod = store_facts.get_product(sku)
        policy = store_facts.get_category_policy(prod.category)

        margin_floor = prod.cost / (1.0 - policy.min_margin)
        discount_floor = prod.list_price * (1.0 - policy.max_discount)
        raw_floor = max(margin_floor, discount_floor)

        computed_floor = store_facts.compute_floor(sku)
        # Computed floor must be strictly greater than raw_floor due to epsilon buffer
        assert computed_floor > raw_floor, (
            f"Computed floor {computed_floor} must be > raw_floor {raw_floor} for {sku}"
        )


def test_stock_checking_logic(store_facts):
    """Test stock checking with valid, invalid, and boundary quantities."""
    # ELEC-101 has stock 25
    assert store_facts.check_stock("ELEC-101", 1) is True
    assert store_facts.check_stock("ELEC-101", 25) is True
    assert store_facts.check_stock("ELEC-101", 26) is False

    # Zero and negative quantities
    assert store_facts.check_stock("ELEC-101", 0) is False
    assert store_facts.check_stock("ELEC-101", -5) is False

    # Out of stock item ELEC-OOS (stock 0)
    assert store_facts.check_stock("ELEC-OOS", 1) is False

    # Non-existent SKU
    assert store_facts.check_stock("NON-EXISTENT", 1) is False


def test_bundle_stock_aggregation(store_facts):
    """Test bundle stock aggregation across multiple line items including duplicate SKUs."""
    # ELEC-101 has 25 in stock
    # Line 1: ELEC-101 qty 10, Line 2: ELEC-101 qty 12 -> total 22 <= 25 (valid)
    valid_bundle = [("ELEC-101", 10), ("ELEC-101", 12), ("ELEC-102", 5)]
    is_valid, aggregated = store_facts.check_bundle_stock(valid_bundle)
    assert is_valid is True
    assert aggregated["ELEC-101"] == 22
    assert aggregated["ELEC-102"] == 5

    # Line 1: ELEC-101 qty 15, Line 2: ELEC-101 qty 12 -> total 27 > 25 (overflow)
    overflow_bundle = [("ELEC-101", 15), ("ELEC-101", 12)]
    is_valid_overflow, _ = store_facts.check_bundle_stock(overflow_bundle)
    assert is_valid_overflow is False

    # Bundle with an out-of-stock item
    oos_bundle = [("ELEC-101", 1), ("ELEC-OOS", 1)]
    is_valid_oos, _ = store_facts.check_bundle_stock(oos_bundle)
    assert is_valid_oos is False

    # Bundle with invalid quantity (<= 0)
    invalid_qty_bundle = [("ELEC-101", -2)]
    is_valid_bad, _ = store_facts.check_bundle_stock(invalid_qty_bundle)
    assert is_valid_bad is False


def test_alternative_finder(store_facts):
    """Test finding in-stock alternatives when an item is out of stock."""
    # ELEC-OOS is out of stock in category Electronics (list_price=200)
    # Alternatives should be in-stock items in Electronics
    alts = store_facts.find_alternatives("ELEC-OOS")
    assert len(alts) > 0

    for alt in alts:
        assert alt.category == "Electronics"
        assert alt.sku != "ELEC-OOS"
        assert alt.stock > 0

    # Sorted by list price proximity to 200
    # ELEC-103 has list_price 350 (diff 150), ELEC-101 & ELEC-102 have 500 (diff 300)
    assert alts[0].sku == "ELEC-103"


def test_alternative_finder_with_budget(store_facts):
    """Test alternative finder filtered by maximum buyer budget."""
    # Target: HOME-202 (list 450, category Home_Appliances)
    # Other items in Home_Appliances:
    # HOME-201 (cost 210, list 320): floor ~ 269.24
    # HOME-203 (cost 140, list 220): floor ~ 179.50
    # If budget is $200, only HOME-203 should qualify
    budget_alts = store_facts.find_alternatives("HOME-202", max_price=200.0)
    assert len(budget_alts) == 1
    assert budget_alts[0].sku == "HOME-203"

    # If budget is too low ($50), no alternatives should match
    empty_alts = store_facts.find_alternatives("HOME-202", max_price=50.0)
    assert len(empty_alts) == 0


def test_banned_phrases_loaded(store_facts):
    """Verify that banned phrases from policy.json are loaded."""
    banned = store_facts.banned_phrases
    assert "only 1 left" in banned
    assert "act now" in banned
    assert "hidden fee" in banned


def test_quantity_tiers_loaded(store_facts):
    """Verify that quantity tiers are sorted descending by min_qty."""
    tiers = store_facts.qty_tiers
    assert len(tiers) >= 2
    for i in range(len(tiers) - 1):
        assert tiers[i].min_qty > tiers[i + 1].min_qty
