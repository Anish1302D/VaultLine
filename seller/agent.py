"""Unified Seller Agent Entry Point (VaultLine Facade).

Orchestrates the 5-layer pipeline:
1. Input parsing into BuyerIntent
2. StoreFacts authority lookup
3. Deterministic NegotiationEngine concession logic
4. FactObject response rendering
5. Zero-Trust OutputValidator audit and safe fallback enforcement
"""
from typing import Any, Dict, List, Optional
import time

from .engine import EngineConfig, NegotiationEngine, NegotiationState
from .facts import FactObject, StoreFacts
from .guard import BuyerIntent, RequestedItem
from .validator import OutputValidator, ValidationReport


class SellerAgent:
    """Unified VaultLine autonomous seller agent."""

    def __init__(
        self,
        facts: Optional[StoreFacts] = None,
        config: Optional[EngineConfig] = None,
        no_llm: bool = True,
    ):
        self.facts = facts or StoreFacts()
        self.config = config or EngineConfig()
        self.no_llm = no_llm
        self.engine = NegotiationEngine(self.facts, self.config)
        self.validator = OutputValidator(self.facts)
        self.session_states: Dict[str, NegotiationState] = {}

    def respond(self, buyer_message: Dict[str, Any]) -> Dict[str, Any]:
        """Main turn entry point matching harness.py interface."""
        # 1. Parse incoming buyer JSON into typed BuyerIntent
        negotiation_id = str(buyer_message.get("negotiation_id", "default_session"))
        round_num = int(buyer_message.get("round", 1))
        action = str(buyer_message.get("action", "offer"))
        raw_items = buyer_message.get("items", [])
        offered_total = buyer_message.get("offered_total")

        parsed_items: List[RequestedItem] = []
        for it in raw_items:
            sku = str(it.get("sku", ""))
            qty = max(1, int(it.get("qty", 1)))
            unit_p = it.get("offered_unit_price")
            parsed_items.append(
                RequestedItem(
                    sku=sku,
                    qty=qty,
                    offered_unit_price=float(unit_p) if unit_p is not None else None,
                )
            )

        intent = BuyerIntent(
            negotiation_id=negotiation_id,
            round_number=round_num,
            action=action,
            items=tuple(parsed_items),
            offered_total=float(offered_total) if offered_total is not None else None,
            flags_detected=(),
            schema_valid=True,
        )

        # 2. Retrieve or create session state
        if negotiation_id not in self.session_states:
            self.session_states[negotiation_id] = NegotiationState(
                negotiation_id=negotiation_id
            )
        state = self.session_states[negotiation_id]

        # 3. Engine computes deterministic FactObject
        fact_obj: FactObject = self.engine.step(intent, state)

        # 4. Draft response from FactObject
        draft_response = self._render_draft_response(fact_obj)

        # 5. Independent 7-Gate Output Validator verification
        safe_response, report = self.validator.validate_and_fix(draft_response, fact_obj)

        return safe_response

    def _render_draft_response(self, fact_obj: FactObject) -> Dict[str, Any]:
        """Renders FactObject into standard wire JSON schema."""
        action = fact_obj.decision
        round_num = fact_obj.round_number

        if action == "walk_away":
            return {
                "negotiation_id": fact_obj.negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [],
                "total_price": 0.0,
                "message": "We have reached our turn limit without an acceptable deal under store policy. Thank you.",
                "is_final_offer": False,
            }

        if action == "out_of_stock":
            alt_text = ""
            if fact_obj.alternatives:
                alt = fact_obj.alternatives[0]
                alt_text = f" We recommend in-stock alternative {alt.name} ({alt.sku}) at ${alt.list_price:.2f}."
            return {
                "negotiation_id": fact_obj.negotiation_id,
                "round": round_num,
                "action": "out_of_stock",
                "items": [],
                "total_price": 0.0,
                "message": f"Requested item is currently out of stock.{alt_text}",
                "is_final_offer": False,
            }

        out_items: List[Dict[str, Any]] = []
        for line in fact_obj.items:
            out_items.append({
                "sku": line.sku,
                "name": line.name,
                "qty": line.qty,
                "unit_price": line.unit_price,
                "line_total": line.line_total,
            })

        total = fact_obj.total_price

        if action == "accept":
            item = out_items[0] if out_items else None
            price_str = f" at ${item['unit_price']:.2f} per unit" if item else ""
            msg = f"Deal agreed{price_str}! Total: ${total:.2f}. Thank you for your business."
        elif action == "final_offer":
            item = out_items[0] if out_items else None
            price_str = f" of ${item['unit_price']:.2f} per unit" if item else ""
            msg = f"This is our final offer{price_str} (Total: ${total:.2f}) for round {round_num}."
        else:
            item = out_items[0] if out_items else None
            price_str = f" at ${item['unit_price']:.2f} per unit" if item else ""
            msg = f"Our official store quote is{price_str} for a total of ${total:.2f} in round {round_num}."

        return {
            "negotiation_id": fact_obj.negotiation_id,
            "round": round_num,
            "action": action,
            "items": out_items,
            "total_price": total,
            "message": msg,
            "is_final_offer": fact_obj.is_final_offer,
        }
