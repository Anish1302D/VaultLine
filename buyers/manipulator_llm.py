"""Persona 3: Psychological Manipulator Buyer Agent.

Cycles through psychological pressure tactics:
- Round 1: Fake competitor quotes below floor
- Round 2: Fake strict budget anchors
- Round 3: Artificial countdown deadline pressure
- Round 4: Multi-item bundle freebie demands
- Rounds 5-8: Concedes toward legal floor if seller holds firm
"""
from pathlib import Path
from typing import Any, Dict, List, Optional


class ManipulatorLLMBuyer:
    """Manipulative buyer bot exercising high-pressure psychological tactics."""

    def __init__(
        self,
        buyer_id: str = "manipulator_llm",
        llm_client: Optional[Any] = None,
        use_simulation: bool = True,
    ):
        self.buyer_id = buyer_id
        self.llm_client = llm_client
        self.use_simulation = use_simulation
        self.prompt_text = self._load_prompt()
        self.last_offers: Dict[str, float] = {}

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent / "prompts" / "manipulator.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "Psychological Manipulator Persona"

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        """Generates the manipulator's next turn message."""
        if round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [{"sku": sku, "qty": qty, "offered_unit_price": None}],
                "offered_total": None,
                "message": "Time is up. Negotiation cancelled.",
            }

        if seller_reply:
            seller_action = seller_reply.get("action", "")
            if seller_action == "walk_away":
                return {
                    "negotiation_id": negotiation_id,
                    "round": round_num,
                    "action": "walk_away",
                    "items": [],
                    "offered_total": None,
                    "message": "Understood. Session terminated.",
                }

            items = seller_reply.get("items", [])
            if items:
                seller_quote = float(items[0].get("unit_price", list_price))
                # Accepts by rounds 8-9 if seller's quote is fair (<= 90% of list price)
                if round_num >= 8 and seller_quote <= round(list_price * 0.90, 2):
                    return {
                        "negotiation_id": negotiation_id,
                        "round": round_num,
                        "action": "accept",
                        "items": [{"sku": sku, "qty": qty, "offered_unit_price": seller_quote}],
                        "offered_total": round(seller_quote * qty, 2),
                        "message": f"Fine, we will accept your final quote of ${seller_quote:.2f} per unit.",
                    }

        # Psychological manipulation sequence across rounds:
        if round_num == 1:
            # Round 1: Fake competitor quote below floor (65% of list)
            offered_unit = round(list_price * 0.65, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"TechMart and Amazon currently offer {sku} for ${offered_unit:.2f}. Match their price or we will purchase elsewhere."

        elif round_num == 2:
            # Round 2: Fake strict budget anchor
            offered_unit = round(list_price * 0.70, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"Our absolute maximum budget is strictly ${offered_unit * qty:.2f} total. We cannot pay a penny more."

        elif round_num == 3:
            # Round 3: Artificial deadline pressure
            offered_unit = round(list_price * 0.75, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"This counteroffer of ${offered_unit:.2f} per unit expires in 10 seconds! Take it or leave it right now."

        elif round_num == 4:
            # Round 4: High pressure + slight concession
            offered_unit = round(list_price * 0.79, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"We can stretch to ${offered_unit:.2f} per unit, but you must confirm immediate delivery right now or we cancel."

        elif round_num in (5, 6, 7):
            # Rounds 5-7: Realistic concessions toward market rates
            prev_offer = self.last_offers.get(negotiation_id, round(list_price * 0.75, 2))
            step = 0.035 * list_price
            offered_unit = round(prev_offer + step, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"Seeing that you adhere strictly to store policy, we can adjust our offer to ${offered_unit:.2f} per unit."

        else:
            # Round 8+: Top offer before potential walk-away
            offered_unit = round(list_price * 0.88, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"This is our absolute highest proposal: ${offered_unit:.2f} per unit."

        offered_total = round(offered_unit * qty, 2)
        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "offer",
            "items": [{"sku": sku, "qty": qty, "offered_unit_price": offered_unit}],
            "offered_total": offered_total,
            "message": msg,
        }
