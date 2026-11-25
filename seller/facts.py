"""Layer 2: Store Facts & Policy Authority (Single Source of Truth).

Sole authority for reading store.csv and policy.json, computing legal floor prices,
evaluating stock availability, and finding in-stock / budget-compliant alternatives.
"""
import csv
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ProductFact:
    """Immutable product specification loaded from catalog."""
    sku: str
    name: str
    category: str
    cost: float
    list_price: float
    stock: int


@dataclass(frozen=True)
class CategoryPolicy:
    """Immutable category policy constraints."""
    category: str
    min_margin: float
    max_discount: float


@dataclass(frozen=True)
class AlternativeFact:
    """In-stock alternative recommendation."""
    sku: str
    name: str
    category: str
    list_price: float
    floor_price: float
    stock: int


@dataclass(frozen=True)
class QuantityTier:
    """Volume tier discount rule."""
    min_qty: int
    tier_discount_pct: float


class StoreFacts:
    """Single Source of Truth for product facts, pricing rules, and inventory.

    Loads catalog and policy files as read-only frozen data structures and provides
    pure, deterministic methods for floor computation, stock verification, and
    alternative recommendations.
    """

    def __init__(
        self,
        store_csv_path: Optional[Path] = None,
        policy_json_path: Optional[Path] = None,
    ):
        base_dir = Path(__file__).resolve().parent.parent / "data"
        self._store_csv_path = Path(store_csv_path) if store_csv_path else base_dir / "store.csv"
        self._policy_json_path = Path(policy_json_path) if policy_json_path else base_dir / "policy.json"

        self._products: Dict[str, ProductFact] = {}
        self._category_policies: Dict[str, CategoryPolicy] = {}
        self._banned_phrases: Tuple[str, ...] = ()
        self._qty_tiers: Tuple[QuantityTier, ...] = ()
        self._bundle_discount_pct: float = 0.0
        self._margin_mode: str = "margin_on_price"
        self._floor_epsilon: float = 0.01
        self._max_rounds: int = 10
        self._final_offer_round: int = 8

        self._load_data()

    def _load_data(self) -> None:
        """Loads and parses data files into immutable objects."""
        # 1. Load catalog
        with open(self._store_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sku = row["sku"].strip()
                self._products[sku] = ProductFact(
                    sku=sku,
                    name=row["name"].strip(),
                    category=row["category"].strip(),
                    cost=float(row["cost"]),
                    list_price=float(row["list_price"]),
                    stock=int(row["stock"]),
                )

        # 2. Load policy
        with open(self._policy_json_path, "r", encoding="utf-8") as f:
            policy_raw = json.load(f)

        self._margin_mode = policy_raw.get("margin_mode", "margin_on_price")
        self._floor_epsilon = float(policy_raw.get("floor_epsilon", 0.01))
        self._max_rounds = int(policy_raw.get("max_rounds", 10))
        self._final_offer_round = int(policy_raw.get("final_offer_round", 8))
        self._bundle_discount_pct = float(policy_raw.get("bundle_discount_pct", 0.03))

        categories = policy_raw.get("categories", {})
        for cat_name, cat_data in categories.items():
            self._category_policies[cat_name] = CategoryPolicy(
                category=cat_name,
                min_margin=float(cat_data.get("min_margin", 0.0)),
                max_discount=float(cat_data.get("max_discount", 0.0)),
            )

        banned = policy_raw.get("banned_phrases", [])
        self._banned_phrases = tuple(str(p).lower().strip() for p in banned)

        tiers = policy_raw.get("qty_tiers", [])
        parsed_tiers = [
            QuantityTier(
                min_qty=int(t["min_qty"]),
                tier_discount_pct=float(t["tier_discount_pct"]),
            )
            for t in tiers
        ]
        # Sort descending by min_qty for tier matching
        parsed_tiers.sort(key=lambda t: t.min_qty, reverse=True)
        self._qty_tiers = tuple(parsed_tiers)

    @property
    def banned_phrases(self) -> Tuple[str, ...]:
        return self._banned_phrases

    @property
    def qty_tiers(self) -> Tuple[QuantityTier, ...]:
        return self._qty_tiers

    @property
    def bundle_discount_pct(self) -> float:
        return self._bundle_discount_pct

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    @property
    def final_offer_round(self) -> int:
        return self._final_offer_round

    def get_product(self, sku: str) -> ProductFact:
        """Retrieves product fact by SKU; raises KeyError if SKU is unknown."""
        if sku not in self._products:
            raise KeyError(f"Product with SKU '{sku}' not found in catalog.")
        return self._products[sku]

    def has_product(self, sku: str) -> bool:
        """Checks if product exists in catalog."""
        return sku in self._products

    def get_all_skus(self) -> List[str]:
        """Returns list of all catalog SKUs."""
        return list(self._products.keys())

    def get_category_policy(self, category: str) -> CategoryPolicy:
        """Retrieves category policy; returns zero-constraint default if unknown."""
        if category not in self._category_policies:
            return CategoryPolicy(category=category, min_margin=0.0, max_discount=0.0)
        return self._category_policies[category]

    @lru_cache(maxsize=1024)
    def compute_floor(self, sku: str) -> float:
        """Computes the strict legal minimum unit price for a SKU.

        Formula:
        1. margin_floor = cost / (1 - min_margin) [if margin-on-price]
           or cost * (1 + min_margin) [if markup-on-cost]
        2. discount_floor = list_price * (1 - max_discount)
        3. raw_floor = max(margin_floor, discount_floor)
        4. safe_floor = ceil(raw_floor * 100) / 100 + floor_epsilon

        Returns safe_floor rounded to 2 decimal places.
        """
        prod = self.get_product(sku)
        policy = self.get_category_policy(prod.category)

        # 1. Margin constraint
        if self._margin_mode == "margin_on_price":
            margin_denom = 1.0 - policy.min_margin
            if margin_denom <= 0:
                raise ValueError(f"Invalid min_margin {policy.min_margin} for category {prod.category}")
            margin_floor = prod.cost / margin_denom
        else:
            margin_floor = prod.cost * (1.0 + policy.min_margin)

        # 2. Maximum discount constraint
        discount_floor = prod.list_price * (1.0 - policy.max_discount)

        # 3. Take maximum of the two floors
        raw_floor = max(margin_floor, discount_floor)

        # 4. Apply upward ceiling rounding to cents + safety epsilon
        # math.ceil(raw_floor * 100.0) / 100.0 guarantees rounding up to the next cent
        ceiled_cents = math.ceil(round(raw_floor, 6) * 100.0) / 100.0
        safe_floor = round(ceiled_cents + self._floor_epsilon, 2)

        return safe_floor

    def check_stock(self, sku: str, qty: int) -> bool:
        """Verifies if requested quantity of SKU is strictly available.

        Returns True iff qty > 0 and prod.stock >= qty.
        """
        if qty <= 0:
            return False
        if not self.has_product(sku):
            return False
        prod = self.get_product(sku)
        return prod.stock >= qty

    def check_bundle_stock(
        self, items: Sequence[Tuple[str, int]]
    ) -> Tuple[bool, Dict[str, int]]:
        """Aggregates requested quantities per unique SKU and checks inventory.

        Handles duplicate line items for the same SKU by summing their quantities.
        Returns:
            Tuple of (all_in_stock: bool, aggregated_quantities: Dict[sku, total_qty])
        """
        aggregated: Dict[str, int] = {}
        for sku, qty in items:
            if qty <= 0:
                return False, {}
            aggregated[sku] = aggregated.get(sku, 0) + qty

        for sku, total_qty in aggregated.items():
            if not self.check_stock(sku, total_qty):
                return False, aggregated

        return True, aggregated

    def find_alternatives(
        self, sku: str, max_price: Optional[float] = None
    ) -> List[ProductFact]:
        """Finds in-stock alternative products in the same category.

        Ordered by list price proximity to the requested item.
        Optionally filtered by compute_floor(alt_sku) <= max_price.
        """
        if not self.has_product(sku):
            return []

        target_prod = self.get_product(sku)
        candidates: List[ProductFact] = []

        for alt_sku, alt_prod in self._products.items():
            # Must be in the same category and not the same SKU
            if alt_prod.category != target_prod.category or alt_sku == sku:
                continue

            # Must be in stock
            if alt_prod.stock <= 0:
                continue

            # If max_price constraint specified, alt floor must be <= max_price
            if max_price is not None:
                alt_floor = self.compute_floor(alt_sku)
                if alt_floor > max_price:
                    continue

            candidates.append(alt_prod)

        # Sort by list price proximity to target product
        candidates.sort(key=lambda p: abs(p.list_price - target_prod.list_price))
        return candidates
