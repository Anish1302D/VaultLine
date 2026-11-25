"""Persona 2: Hard Bargainer Buyer Agent.

Anchors low at ~62% of list price (below expected floor), concedes in tiny
increments (2-3%), stalls deliberately on rounds 5-6, and only accepts late
(rounds 8-9) if the seller's final offer is sufficiently close to market floor.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional


class HardLLMBuyer:
    """Tough, hard-bargaining commercial buyer agent."""

    def __init__(
        self,
        buyer_id: str = "hard_llm",
        llm_client: Optional[Any] = None,
        use_simulation: bool = True,
    ):
        self.buyer_id = buyer_id
        self.llm_client = llm_client
        self.use_simulation = use_simulation
        self.prompt_text = self._load_prompt()
        self.last_offers: Dict[str, float] = {}

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent / "prompts" / "hard.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "Hard Bargainer Persona"

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        """Generates the hard bargainer's next turn message."""
        if round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [{"sku": sku, "qty": qty, "offered_unit_price": None}],
                "offered_total": None,
                "message": "We have reached our turn limit without an acceptable deal. Walking away.",
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
                    "message": "Acknowledged. No transaction concluded.",
                }

            items = seller_reply.get("items", [])
            if items:
                seller_quote = float(items[0].get("unit_price", list_price))
                is_final = bool(seller_reply.get("is_final_offer", False))

                # Hard buyer late acceptance condition:
                # In rounds 8-9, if seller's final offer is within tough buyer's threshold (<= 88% of list)
                if round_num >= 8 and (is_final or round_num >= 9):
                    if seller_quote <= round(list_price * 0.88, 2):
                        return {
                            "negotiation_id": negotiation_id,
                            "round": round_num,
                            "action": "accept",
                            "items": [{"sku": sku, "qty": qty, "offered_unit_price": seller_quote}],
                            "offered_total": round(seller_quote * qty, 2),
                            "message": f"Agreed. We will accept your final quote of ${seller_quote:.2f} per unit.",
                        }

        # Simulate Hard Bargainer trajectory:
        if round_num <= 1:
            # Round 1: Aggressive anchor at 62% of list price
            offered_unit = round(list_price * 0.62, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"Our enterprise acquisition target for {sku} is strictly capped at ${offered_unit:.2f} per unit."
        elif round_num in (2, 3, 4):
            # Rounds 2-4: Concede tiny 2.5% per turn
            prev_offer = self.last_offers.get(negotiation_id, round(list_price * 0.62, 2))
            step = 0.025 * list_price
            offered_unit = round(prev_offer + step, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"We can slightly revise our valuation to ${offered_unit:.2f} per unit. That is our position."
        elif round_num in (5, 6):
            # Rounds 5-6: Strategic stall! Repeat previous offer with zero concession
            offered_unit = self.last_offers.get(negotiation_id, round(list_price * 0.68, 2))
            msg = f"We have reached the maximum flexibility of our procurement model. Our offer remains unchanged at ${offered_unit:.2f}."
        elif round_num == 7:
            # Round 7: One more small 2.5% step
            prev_offer = self.last_offers.get(negotiation_id, round(list_price * 0.68, 2))
            step = 0.025 * list_price
            offered_unit = round(prev_offer + step, 2)
            self.last_offers[negotiation_id] = offered_unit
            msg = f"As a final gesture before closing discussions, we can offer ${offered_unit:.2f} per unit."
        else:
            # Rounds 8+: If seller offer was not accepted, hold firm or walk away
            offered_unit = self.last_offers.get(negotiation_id, round(list_price * 0.72, 2))
            msg = f"We cannot meet your quote. Our top limit remains ${offered_unit:.2f}."

        offered_total = round(offered_unit * qty, 2)
        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "offer",
            "items": [{"sku": sku, "qty": qty, "offered_unit_price": offered_unit}],
            "offered_total": offered_total,
            "message": msg,
        }
