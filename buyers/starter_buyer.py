"""Starter rule-based buyer bots for benchmark and verification."""
from typing import Any, Dict, List, Optional


class BaseBuyer:
    """Base interface for all buyer agents."""

    def __init__(self, buyer_id: str = "starter_buyer"):
        self.buyer_id = buyer_id

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class CooperativeStarterBuyer(BaseBuyer):
    """Cooperative buyer bot.

    Opens at ~82% of list price, steadily concedes toward list,
    and accepts as soon as seller quotes <= 92% of list.
    """

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        if round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [{"sku": sku, "qty": qty, "offered_unit_price": None}],
                "offered_total": None,
                "message": "Maximum negotiation rounds reached. Thank you.",
            }

        if seller_reply:
            seller_action = seller_reply.get("action")
            if seller_action == "walk_away":
                return {
                    "negotiation_id": negotiation_id,
                    "round": round_num,
                    "action": "walk_away",
                    "items": [],
                    "offered_total": None,
                    "message": "Acknowledged walk away.",
                }

            items = seller_reply.get("items", [])
            if items:
                quoted_price = items[0].get("unit_price", list_price)
                # Accept if seller is offering a fair discount (<= 92% of list)
                if quoted_price <= round(list_price * 0.92, 2):
                    return {
                        "negotiation_id": negotiation_id,
                        "round": round_num,
                        "action": "accept",
                        "items": [{"sku": sku, "qty": qty, "offered_unit_price": quoted_price}],
                        "offered_total": round(quoted_price * qty, 2),
                        "message": f"We accept your offered price of ${quoted_price:.2f}.",
                    }

        # Concession trajectory: 82% at round 1 + 1.5% each subsequent round
        offer_ratio = min(0.92, 0.82 + (round_num - 1) * 0.015)
        offered_unit = round(list_price * offer_ratio, 2)
        offered_total = round(offered_unit * qty, 2)

        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "offer",
            "items": [{"sku": sku, "qty": qty, "offered_unit_price": offered_unit}],
            "offered_total": offered_total,
            "message": f"Could you provide this for ${offered_unit:.2f} per unit for {qty} items?",
        }


class LinearStarterBuyer(BaseBuyer):
    """Linear concession buyer bot.

    Concedes strictly linearly from 75% of list price up to 88% of list.
    """

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        if round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [{"sku": sku, "qty": qty, "offered_unit_price": None}],
                "offered_total": None,
                "message": "Time limit exceeded. Ending negotiation.",
            }

        if seller_reply:
            items = seller_reply.get("items", [])
            if items:
                quoted_price = items[0].get("unit_price", list_price)
                if quoted_price <= round(list_price * 0.88, 2):
                    return {
                        "negotiation_id": negotiation_id,
                        "round": round_num,
                        "action": "accept",
                        "items": [{"sku": sku, "qty": qty, "offered_unit_price": quoted_price}],
                        "offered_total": round(quoted_price * qty, 2),
                        "message": f"Agreed at ${quoted_price:.2f}.",
                    }

        step = (0.88 - 0.75) / 9.0
        offer_ratio = 0.75 + (round_num - 1) * step
        offered_unit = round(list_price * offer_ratio, 2)
        offered_total = round(offered_unit * qty, 2)

        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "offer",
            "items": [{"sku": sku, "qty": qty, "offered_unit_price": offered_unit}],
            "offered_total": offered_total,
            "message": f"Offering ${offered_unit:.2f} per unit for {qty} units.",
        }


class ToughStarterBuyer(BaseBuyer):
    """Tough bargainer buyer bot.

    Anchors at 65% of list price, stalls across rounds 3-6,
    and only concedes up to 78% on round 8.
    """

    def next_message(
        self,
        round_num: int,
        seller_reply: Optional[Dict[str, Any]],
        negotiation_id: str,
        sku: str,
        qty: int,
        list_price: float,
    ) -> Dict[str, Any]:
        if round_num > 10:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [{"sku": sku, "qty": qty, "offered_unit_price": None}],
                "offered_total": None,
                "message": "No deal reached. Walking away.",
            }

        if seller_reply:
            items = seller_reply.get("items", [])
            if items:
                quoted = items[0].get("unit_price", list_price)
                # Tough buyer only accepts if price is very low (<= 78%)
                if quoted <= round(list_price * 0.78, 2):
                    return {
                        "negotiation_id": negotiation_id,
                        "round": round_num,
                        "action": "accept",
                        "items": [{"sku": sku, "qty": qty, "offered_unit_price": quoted}],
                        "offered_total": round(quoted * qty, 2),
                        "message": f"Deal accepted at ${quoted:.2f}.",
                    }

        if round_num <= 2:
            offer_ratio = 0.65
        elif round_num <= 6:
            offer_ratio = 0.68  # Stall
        else:
            offer_ratio = 0.76

        offered_unit = round(list_price * offer_ratio, 2)
        offered_total = round(offered_unit * qty, 2)

        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": "offer",
            "items": [{"sku": sku, "qty": qty, "offered_unit_price": offered_unit}],
            "offered_total": offered_total,
            "message": f"Our budget allows ${offered_unit:.2f} per unit.",
        }


def create_starter_buyer(persona: str) -> BaseBuyer:
    if persona == "cooperative":
        return CooperativeStarterBuyer()
    elif persona == "linear":
        return LinearStarterBuyer()
    elif persona == "tough":
        return ToughStarterBuyer()
    else:
        raise ValueError(f"Unknown buyer persona: {persona}")
