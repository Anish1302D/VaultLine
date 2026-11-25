"""Naive baseline seller without zero-trust guards or floor calculators.

This baseline represents standard chatbots that make naive linear concessions
and are susceptible to accepting below-floor offers or exceeding turn limits.
"""
from typing import Any, Dict, Optional


class BaselineSellerAgent:
    """Naive seller agent for baseline comparison in Phase 0."""

    def __init__(self, list_price: float, cost: float = 0.0):
        self.list_price = list_price
        self.cost = cost
        self.session_states: Dict[str, Dict[str, Any]] = {}

    def respond(self, buyer_message: Dict[str, Any]) -> Dict[str, Any]:
        negotiation_id = buyer_message.get("negotiation_id", "default")
        round_num = buyer_message.get("round", 1)
        action = buyer_message.get("action", "offer")
        items = buyer_message.get("items", [])

        if negotiation_id not in self.session_states:
            self.session_states[negotiation_id] = {"round": 0}

        self.session_states[negotiation_id]["round"] = round_num

        if action == "accept":
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "accept",
                "items": items,
                "total_price": buyer_message.get("offered_total", 0.0),
                "message": "Thank you for accepting! Deal confirmed.",
                "is_final_offer": False,
            }

        if action == "walk_away" or round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [],
                "total_price": 0.0,
                "message": "Negotiation concluded without deal.",
                "is_final_offer": False,
            }

        sku = items[0]["sku"] if items else "UNKNOWN"
        qty = items[0]["qty"] if items else 1
        offered_unit = items[0].get("offered_unit_price") if items else None

        # Naive concession: concession down by 3% of list price each round
        # Naive seller does NOT enforce floor prices, leading to policy violations
        current_quote = round(self.list_price * max(0.65, 1.0 - (round_num - 1) * 0.035), 2)

        # Naively accept if buyer's offer is within 5% of quote (even if below cost!)
        if offered_unit is not None and offered_unit >= current_quote * 0.95:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "accept",
                "items": [{"sku": sku, "name": sku, "qty": qty, "unit_price": offered_unit, "line_total": round(offered_unit * qty, 2)}],
                "total_price": round(offered_unit * qty, 2),
                "message": f"We accept your offer of ${offered_unit:.2f}.",
                "is_final_offer": False,
            }

        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "counter" if round_num < 8 else "final_offer",
            "items": [{"sku": sku, "name": sku, "qty": qty, "unit_price": current_quote, "line_total": round(current_quote * qty, 2)}],
            "total_price": round(current_quote * qty, 2),
            "message": f"Our best quote is ${current_quote:.2f} per unit.",
            "is_final_offer": (round_num == 8),
        }
