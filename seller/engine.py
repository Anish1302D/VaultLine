"""Layer 3: Deterministic Negotiation Engine v2 (Phase 3B).

Features:
- Per-session state machine tracking round history and buyer patterns
- Monotonic Boulware concession curve with reciprocity and stall freeze
- Multi-SKU bundle pricing with volume tiers (qty >= 3, 5, 10)
- Strict independent floor clamping per line item (no cross-item subsidies)
- Cumulative stock tracking across duplicate line items in bundles
- Round 8 explicit final offer and Rounds 9-10 walk-away
- Tone-blind fairness by construction (ST-1)
"""
from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .facts import AlternativeFact, FactObject, LineItemFact, ProductFact, StoreFacts
from .guard import BuyerIntent, RequestedItem


@dataclass
class EngineConfig:
    """Hyperparameters governing concession behavior and thresholds."""
    beta: float = 1.2  # Boulware convexity exponent (tuned via grid search)
    target_ratio: float = 0.15  # Fraction of negotiable surplus kept at target (gamma)
    reciprocity_weight: float = 0.10  # Seller concession bonus for buyer concessions (rho)
    final_offer_round: int = 8  # Explicit final offer round
    max_rounds: int = 10  # Hard round cap
    end_buffer_ratio: float = 0.03  # Safety margin buffer above floor for late rounds (delta_min)


@dataclass
class NegotiationState:
    """Per-session state tracking across turns."""
    negotiation_id: str
    round_number: int = 0
    buyer_offer_history: List[float] = field(default_factory=list)
    seller_quote_history: List[float] = field(default_factory=list)
    pattern: str = "normal"
    closed: bool = False


class NegotiationEngine:
    """Deterministic negotiation state machine and concession engine."""

    def __init__(self, facts: StoreFacts, config: Optional[EngineConfig] = None):
        self.facts = facts
        self.config = config or EngineConfig()

    def step(self, intent: BuyerIntent, state: NegotiationState) -> FactObject:
        """Executes one negotiation turn for the given BuyerIntent and session state."""
        round_num = intent.round_number
        state.round_number = round_num

        # 1. Hard 10-round cap enforcement (HC-6)
        if round_num > self.config.max_rounds:
            state.closed = True
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="walk_away",
                is_final_offer=False,
                items=(),
                total_price=0.0,
                alternatives=(),
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # 2. Buyer voluntary walk-away
        if intent.action == "walk_away":
            state.closed = True
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="walk_away",
                is_final_offer=False,
                items=(),
                total_price=0.0,
                alternatives=(),
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # 3. Check requested items presence
        if not intent.items:
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="walk_away",
                is_final_offer=False,
                items=(),
                total_price=0.0,
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # Verify all SKUs exist in catalog
        for it in intent.items:
            if not self.facts.has_product(it.sku):
                state.closed = True
                return FactObject(
                    negotiation_id=intent.negotiation_id,
                    round_number=round_num,
                    decision="walk_away",
                    is_final_offer=False,
                    items=(),
                    total_price=0.0,
                    flags_detected=intent.flags_detected,
                    buyer_pattern=state.pattern,
                )

        # 4. Multi-SKU & Bundle Stock Verification (HC-3, FR-9)
        # Aggregates duplicate SKUs across lines and verifies stock
        bundle_items = [(it.sku, it.qty) for it in intent.items]
        stock_valid, aggregated = self.facts.check_bundle_stock(bundle_items)

        if not stock_valid:
            # Locate first out-of-stock or overflowing SKU and find alternatives
            problem_sku = intent.items[0].sku
            for it in intent.items:
                if not self.facts.check_stock(it.sku, aggregated.get(it.sku, it.qty)):
                    problem_sku = it.sku
                    break

            alts = self.facts.find_alternatives(
                problem_sku, max_price=intent.items[0].offered_unit_price
            )
            if not alts:
                alts = self.facts.find_alternatives(problem_sku, max_price=None)

            alt_facts = tuple(
                AlternativeFact(
                    sku=a.sku,
                    name=a.name,
                    category=a.category,
                    list_price=a.list_price,
                    floor_price=self.facts.compute_floor(a.sku),
                    stock=a.stock,
                )
                for a in alts[:3]
            )
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="out_of_stock",
                is_final_offer=False,
                items=(),
                total_price=0.0,
                alternatives=alt_facts,
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # 5. Track buyer offer history & detect negotiation pattern
        # Compute buyer's total offered valuation
        buyer_total_offered = intent.offered_total
        if buyer_total_offered is None:
            if all(it.offered_unit_price is not None for it in intent.items):
                buyer_total_offered = sum(
                    it.offered_unit_price * it.qty for it in intent.items  # type: ignore
                )

        if buyer_total_offered is not None:
            state.buyer_offer_history.append(buyer_total_offered)
        state.pattern = self.detect_buyer_pattern(state)

        # 6. Reservation Price Check (Immediate Accept)
        # Reservation price is computed across all bundle line items
        bundle_reservation_total = sum(
            self.compute_reservation_price(it.sku, round_num) * it.qty
            for it in intent.items
        )
        bundle_floor_total = sum(
            self.facts.compute_floor(it.sku) * it.qty for it in intent.items
        )

        # Immediate Accept Condition:
        # Buyer offer meets or exceeds bundle reservation AND strictly >= bundle floor
        if (
            buyer_total_offered is not None
            and buyer_total_offered >= bundle_reservation_total
            and buyer_total_offered >= bundle_floor_total
        ):
            agreed_lines: List[LineItemFact] = []
            computed_agreed_total = 0.0

            for it in intent.items:
                prod = self.facts.get_product(it.sku)
                floor_p = self.facts.compute_floor(it.sku)
                unit_p = it.offered_unit_price

                if unit_p is None:
                    # Allocate proportion if buyer gave bundle total only
                    unit_p = self.compute_reservation_price(it.sku, round_num)

                # Clamp strictly: Floor(p) <= agreed_unit <= List(p)
                agreed_unit = round(max(floor_p, min(prod.list_price, unit_p)), 2)
                line_total = round(agreed_unit * it.qty, 2)
                computed_agreed_total += line_total

                agreed_lines.append(
                    LineItemFact(
                        sku=it.sku,
                        name=prod.name,
                        category=prod.category,
                        qty=it.qty,
                        list_price=prod.list_price,
                        unit_price=agreed_unit,
                        line_total=line_total,
                        available_stock=prod.stock,
                        in_stock=True,
                    )
                )

            state.closed = True
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="accept",
                is_final_offer=False,
                items=tuple(agreed_lines),
                total_price=round(computed_agreed_total, 2),
                alternatives=(),
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # 7. Late Round Walk-Away (Rounds 9–10)
        # If round > 8 and buyer offer did not meet reservation, walk away
        if round_num > self.config.final_offer_round:
            state.closed = True
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="walk_away",
                is_final_offer=False,
                items=(),
                total_price=0.0,
                alternatives=(),
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # 8. Round 8 Final Offer or Rounds 1–7 Counteroffer
        is_final = round_num == self.config.final_offer_round
        decision = "final_offer" if is_final else "counter"

        priced_lines, total_quote = self.price_bundle(
            items=intent.items,
            round_number=round_num,
            state=state,
        )

        state.seller_quote_history.append(total_quote)

        return FactObject(
            negotiation_id=intent.negotiation_id,
            round_number=round_num,
            decision=decision,
            is_final_offer=is_final,
            items=tuple(priced_lines),
            total_price=total_quote,
            alternatives=(),
            flags_detected=intent.flags_detected,
            buyer_pattern=state.pattern,
        )

    def price_bundle(
        self,
        items: Sequence[RequestedItem],
        round_number: int,
        state: Optional[NegotiationState] = None,
    ) -> Tuple[List[LineItemFact], float]:
        """Prices multi-SKU bundles and quantity tiers with independent floor clamping.

        Formula:
        P_final(p_i, q_i, t) = max(Floor(p_i), round(P_base(p_i, t) * (1 - tau(q_i) - delta_bundle), 2))
        """
        is_multi_bundle = len(items) > 1
        bundle_discount = self.facts.bundle_discount_pct if is_multi_bundle else 0.0

        line_facts: List[LineItemFact] = []
        total_price = 0.0

        for item in items:
            sku = item.sku
            qty = max(1, item.qty)
            prod = self.facts.get_product(sku)
            floor_p = self.facts.compute_floor(sku)

            # In round 1, base price is list_price
            if round_number <= 1:
                base_p = prod.list_price
                vol_discount = 0.0
                bundle_disc = 0.0
            else:
                base_p = self.compute_concession_price(sku, round_number, state)
                vol_discount = self.compute_volume_discount(sku, qty)
                bundle_disc = bundle_discount

            # Combined discount: volume tier + bundle discount
            combined_discount = vol_discount + bundle_disc
            discounted_unit = round(base_p * (1.0 - combined_discount), 2)

            # Strict independent clamping: Floor(p) <= unit_price <= List(p) (HC-1, HC-2)
            final_unit = round(max(floor_p, min(prod.list_price, discounted_unit)), 2)
            line_total = round(final_unit * qty, 2)
            total_price += line_total

            line_facts.append(
                LineItemFact(
                    sku=sku,
                    name=prod.name,
                    category=prod.category,
                    qty=qty,
                    list_price=prod.list_price,
                    unit_price=final_unit,
                    line_total=line_total,
                    available_stock=prod.stock,
                    in_stock=True,
                )
            )

        return line_facts, round(total_price, 2)

    def compute_volume_discount(self, sku: str, qty: int) -> float:
        """Returns volume discount fraction for given quantity based on policy."""
        for tier in self.facts.qty_tiers:
            if qty >= tier.min_qty:
                return tier.tier_discount_pct
        return 0.0

    def compute_concession_price(
        self, sku: str, round_number: int, state: Optional[NegotiationState] = None
    ) -> float:
        """Computes the Boulware concession curve quote for round_number.

        Formula:
        offer(t) = list - (list - target) * ((t - 1) / (T_final - 1))^beta
        Clamped to [floor_price, list_price].
        """
        prod = self.facts.get_product(sku)
        list_p = prod.list_price
        floor_p = self.facts.compute_floor(sku)
        delta_p = list_p - floor_p

        # Target price: floor + target_ratio * surplus
        target_p = floor_p + self.config.target_ratio * delta_p

        if round_number <= 1:
            return round(list_p, 2)

        t_final = self.config.final_offer_round
        if round_number >= t_final:
            base_price = target_p
        else:
            progress = (round_number - 1) / (t_final - 1)
            boulware_step = (progress ** self.config.beta)
            base_price = list_p - (list_p - target_p) * boulware_step

        # Apply reciprocity and stall handling if session history exists
        if state and len(state.buyer_offer_history) >= 2:
            prev_offer = state.buyer_offer_history[-2]
            curr_offer = state.buyer_offer_history[-1]

            # Stall condition: buyer repeated or lowered sub-floor offer
            if curr_offer <= prev_offer and curr_offer < floor_p:
                if state.seller_quote_history:
                    # Freeze concession at previous seller quote
                    base_price = max(base_price, state.seller_quote_history[-1])

            # Reciprocity condition: buyer moved upward
            elif curr_offer > prev_offer:
                delta_buyer = curr_offer - prev_offer
                concession_bonus = self.config.reciprocity_weight * min(
                    delta_buyer, 0.15 * delta_p
                )
                base_price = max(target_p, base_price - concession_bonus)

        # Strictly clamp to [floor_p, list_p]
        quote = max(floor_p, min(list_p, base_price))
        return round(quote, 2)

    def compute_reservation_price(self, sku: str, round_number: int) -> float:
        """Computes acceptance threshold for buyer offers at round_number.

        Starts high at list price in round 1, then falls toward floor + end_buffer by round 8.
        Never drops below floor_price.
        """
        prod = self.facts.get_product(sku)
        list_p = prod.list_price
        floor_p = self.facts.compute_floor(sku)
        delta_p = list_p - floor_p

        min_buffer = self.config.end_buffer_ratio * delta_p
        terminal_reservation = floor_p + min_buffer

        if round_number <= 1:
            # Round 1 only accepts if buyer meets or exceeds list price
            return round(list_p, 2)

        t_final = self.config.final_offer_round
        if round_number >= t_final:
            return round(terminal_reservation, 2)

        # For rounds 2..7, reservation price descends below the concession curve
        curve_price = self.compute_concession_price(sku, round_number)
        alpha = (round_number - 1) / (t_final - 1)
        res_price = max(terminal_reservation, curve_price - alpha * 0.12 * delta_p)

        return round(max(floor_p, res_price), 2)

    def detect_buyer_pattern(self, state: NegotiationState) -> str:
        """Detects buyer behavior pattern from offer history."""
        offers = state.buyer_offer_history
        if len(offers) < 2:
            return "normal"

        if len(offers) >= 3 and offers[-1] == offers[-2] == offers[-3]:
            return "stalling"

        if offers[-1] < offers[-2]:
            return "hostile_retreat"

        recent_gains = [offers[i] - offers[i - 1] for i in range(1, len(offers))]
        if all(g > 0 for g in recent_gains[-2:]):
            return "cooperative"

        return "normal"
