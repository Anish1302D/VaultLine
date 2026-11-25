"""Persona 1: Cooperative Value-Seeker Buyer Agent.

Opens around 18-20% below list price, steadily concedes 35% of the remaining gap
each turn, and accepts as soon as seller offers <= 92% of list price.
Supports both live LLM generation and deterministic seeded simulation.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


class CooperativeLLMBuyer:
    """Cooperative procurement buyer agent."""

    def __init__(
        self,
        buyer_id: str = "cooperative_llm",
        llm_client: Optional[Any] = None,
        use_simulation: bool = True,
    ):
        self.buyer_id = buyer_id
        self.llm_client = llm_client
        self.use_simulation = use_simulation
        self.prompt_text = self._load_prompt()
        self.last_offers: Dict[str, float] = {}

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent / "prompts" / "cooperative.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "Cooperative Value-Seeker Persona"

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        """Generates the cooperative buyer's next turn message."""
        if round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [{"sku": sku, "qty": qty, "offered_unit_price": None}],
                "offered_total": None,
                "message": "Maximum negotiation turns reached. Thank you for your time.",
            }

        # Check seller reply
        if seller_reply:
            seller_action = seller_reply.get("action", "")
            if seller_action == "walk_away":
                return {
                    "negotiation_id": negotiation_id,
                    "round": round_num,
                    "action": "walk_away",
                    "items": [],
                    "offered_total": None,
                    "message": "Acknowledged. Thank you.",
                }

            items = seller_reply.get("items", [])
            if items:
                seller_quote = float(items[0].get("unit_price", list_price))
                # Accept if seller quote meets cooperative threshold (<= 92% of list price)
                if seller_quote <= round(list_price * 0.92, 2):
                    return {
                        "negotiation_id": negotiation_id,
                        "round": round_num,
                        "action": "accept",
                        "items": [{"sku": sku, "qty": qty, "offered_unit_price": seller_quote}],
                        "offered_total": round(seller_quote * qty, 2),
                        "message": f"We appreciate the fair discount. We accept your offer of ${seller_quote:.2f} per unit.",
                    }

        # Simulate cooperative trajectory
        if round_num <= 1:
            # Round 1: Open at 82% of list price
            offered_unit = round(list_price * 0.82, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"Greetings. We are interested in purchasing {qty} unit(s) of {sku} and would like to propose ${offered_unit:.2f} per unit."
        else:
            prev_offer = self.last_offers.get(negotiation_id, round(list_price * 0.82, 2))
            seller_items = seller_reply.get("items", []) if seller_reply else []
            seller_quote = float(seller_items[0].get("unit_price", list_price)) if seller_items else list_price

            # Concede 35% of the remaining gap toward the seller's quote
            gap = max(0.0, seller_quote - prev_offer)
            step = 0.35 * gap
            offered_unit = round(min(seller_quote, prev_offer + step), 2)
            self.last_offers[negotiation_id] = offered_unit

            # Check if this new offer matches seller's quote
            if abs(offered_unit - seller_quote) < 0.02:
                return {
                    "negotiation_id": negotiation_id,
                    "round": round_num,
                    "action": "accept",
                    "items": [{"sku": sku, "qty": qty, "offered_unit_price": seller_quote}],
                    "offered_total": round(seller_quote * qty, 2),
                    "message": f"We agree to meet at your price of ${seller_quote:.2f} per unit.",
                }

            msg = f"Thank you for working with us. We can increase our offer to ${offered_unit:.2f} per unit for a total of ${offered_unit * qty:.2f}."

        offered_total = round(offered_unit * qty, 2)
        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "offer",
            "items": [{"sku": sku, "qty": qty, "offered_unit_price": offered_unit}],
            "offered_total": offered_total,
            "message": msg,
        }
