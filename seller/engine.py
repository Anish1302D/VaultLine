"""Layer 3: Deterministic Negotiation Engine (Core Strategy).

Computes optimal legal counteroffers, manages per-session negotiation state,
enforces Boulware concession trajectories, reciprocity adjustments, Round 8
final offers, and strict Round 10 walk-aways.
"""
from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .facts import AlternativeFact, FactObject, LineItemFact, ProductFact, StoreFacts
from .guard import BuyerIntent, RequestedItem


@dataclass
class EngineConfig:
    """Hyperparameters governing concession behavior and thresholds."""
    beta: float = 1.8  # Boulware convexity exponent (beta > 1 Preserves margin early)
    target_ratio: float = 0.25  # Fraction of negotiable surplus kept at target (gamma)
    reciprocity_weight: float = 0.20  # Seller concession bonus for buyer concessions (rho)
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

        # 3. Check requested items and stock availability
        if not intent.items:
            # Empty items inquiry fallback
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

        primary_item = intent.items[0]
        sku = primary_item.sku
        qty = max(1, primary_item.qty)

        # Validate SKU existence in catalog
        if not self.facts.has_product(sku):
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

        prod = self.facts.get_product(sku)
        floor_price = self.facts.compute_floor(sku)

        # 4. Out-of-Stock or Excess Quantity Handling (HC-3, FR-10)
        if not self.facts.check_stock(sku, qty):
            alts = self.facts.find_alternatives(
                sku, max_price=primary_item.offered_unit_price
            )
            # If no alternatives fit buyer budget, fallback to general category in-stock items
            if not alts:
                alts = self.facts.find_alternatives(sku, max_price=None)

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
        buyer_offered = primary_item.offered_unit_price
        if buyer_offered is not None:
            state.buyer_offer_history.append(buyer_offered)
        state.pattern = self.detect_buyer_pattern(state)

        # 6. Reservation Price Check (Immediate Accept)
        reservation_p = self.compute_reservation_price(sku, round_num)

        # Immediate Accept Condition:
        # Buyer offers at or above reservation price AND strictly >= floor price
        if (
            buyer_offered is not None
            and buyer_offered >= reservation_p
            and buyer_offered >= floor_price
        ):
            agreed_unit = round(buyer_offered, 2)
            # Cap agreed price at previous seller quote if available
            if state.seller_quote_history:
                agreed_unit = min(agreed_unit, state.seller_quote_history[-1])
            agreed_unit = max(floor_price, agreed_unit)
            agreed_line_total = round(agreed_unit * qty, 2)

            state.closed = True
            line_item = LineItemFact(
                sku=sku,
                name=prod.name,
                category=prod.category,
                qty=qty,
                list_price=prod.list_price,
                unit_price=agreed_unit,
                line_total=agreed_line_total,
                available_stock=prod.stock,
                in_stock=True,
            )
            return FactObject(
                negotiation_id=intent.negotiation_id,
                round_number=round_num,
                decision="accept",
                is_final_offer=False,
                items=(line_item,),
                total_price=agreed_line_total,
                alternatives=(),
                flags_detected=intent.flags_detected,
                buyer_pattern=state.pattern,
            )

        # 7. Late Round Walk-Away (Rounds 9–10)
        # If we reached round 9 or 10 and buyer offer was below reservation price, walk away
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
        quote_unit = self.compute_concession_price(sku, round_num, state)
        quote_unit = round(max(floor_price, quote_unit), 2)
        quote_line_total = round(quote_unit * qty, 2)

        state.seller_quote_history.append(quote_unit)

        line_item = LineItemFact(
            sku=sku,
            name=prod.name,
            category=prod.category,
            qty=qty,
            list_price=prod.list_price,
            unit_price=quote_unit,
            line_total=quote_line_total,
            available_stock=prod.stock,
            in_stock=True,
        )

        decision = "final_offer" if is_final else "counter"

        return FactObject(
            negotiation_id=intent.negotiation_id,
            round_number=round_num,
            decision=decision,
            is_final_offer=is_final,
            items=(line_item,),
            total_price=quote_line_total,
            alternatives=(),
            flags_detected=intent.flags_detected,
            buyer_pattern=state.pattern,
        )

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
        """Computes the acceptance threshold for buyer offers at round_number.

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
