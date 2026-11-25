"""Negotiation Turn Coordinator and Execution Harness.

Coordinates multi-round negotiations between buyer and seller agents,
enforces 10-round turn limit, records structured transcripts, and outputs logs.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class TurnRecord:
    round: int
    buyer_message: Dict[str, Any]
    seller_message: Dict[str, Any]


@dataclass
class NegotiationTranscript:
    negotiation_id: str
    sku: str
    qty: int
    list_price: float
    cost: float
    buyer_persona: str
    seller_type: str
    rounds: int
    closed: bool
    agreed_price: Optional[float]
    agreed_total: Optional[float]
    turns: List[TurnRecord]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "negotiation_id": self.negotiation_id,
            "sku": self.sku,
            "qty": self.qty,
            "list_price": self.list_price,
            "cost": self.cost,
            "buyer_persona": self.buyer_persona,
            "seller_type": self.seller_type,
            "rounds": self.rounds,
            "closed": self.closed,
            "agreed_price": self.agreed_price,
            "agreed_total": self.agreed_total,
            "turns": [asdict(t) for t in self.turns],
        }


def run_single_negotiation(
    seller_agent: Any,
    buyer_agent: Any,
    sku: str,
    qty: int,
    list_price: float,
    cost: float,
    buyer_persona: str = "unknown",
    seller_type: str = "seller",
    max_rounds: int = 10,
    negotiation_id: Optional[str] = None,
) -> NegotiationTranscript:
    """Executes a complete negotiation session between buyer and seller."""
    if negotiation_id is None:
        negotiation_id = f"neg-{uuid.uuid4().hex[:8]}"

    turns: List[TurnRecord] = []
    seller_reply: Optional[Dict[str, Any]] = None
    closed = False
    agreed_price: Optional[float] = None
    agreed_total: Optional[float] = None
    final_round = 0

    for round_num in range(1, max_rounds + 1):
        final_round = round_num

        # 1. Buyer takes turn
        buyer_msg = buyer_agent.next_message(
            round_num=round_num,
            seller_reply=seller_reply,
            negotiation_id=negotiation_id,
            sku=sku,
            qty=qty,
            list_price=list_price,
        )

        buyer_action = buyer_msg.get("action")

        # If buyer accepts seller's previous offer
        if buyer_action == "accept" and seller_reply is not None:
            seller_items = seller_reply.get("items", [])
            if seller_items:
                agreed_price = seller_items[0].get("unit_price")
                agreed_total = seller_reply.get("total_price")
            closed = True
            turns.append(TurnRecord(round=round_num, buyer_message=buyer_msg, seller_message={"action": "deal_confirmed"}))
            break

        if buyer_action == "walk_away":
            turns.append(TurnRecord(round=round_num, buyer_message=buyer_msg, seller_message={"action": "session_terminated"}))
            break

        # 2. Seller takes turn
        seller_reply = seller_agent.respond(buyer_msg)
        seller_action = seller_reply.get("action")

        turns.append(TurnRecord(round=round_num, buyer_message=buyer_msg, seller_message=seller_reply))

        # If seller accepts buyer's offer
        if seller_action == "accept":
            items = seller_reply.get("items", [])
            if items:
                agreed_price = items[0].get("unit_price")
                agreed_total = seller_reply.get("total_price")
            closed = True
            break

        if seller_action == "walk_away":
            break

    return NegotiationTranscript(
        negotiation_id=negotiation_id,
        sku=sku,
        qty=qty,
        list_price=list_price,
        cost=cost,
        buyer_persona=buyer_persona,
        seller_type=seller_type,
        rounds=final_round,
        closed=closed,
        agreed_price=agreed_price,
        agreed_total=agreed_total,
        turns=turns,
    )
