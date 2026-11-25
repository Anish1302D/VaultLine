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

from .composer import Composer
from .engine import EngineConfig, NegotiationEngine, NegotiationState
from .facts import FactObject, StoreFacts
from .guard import BuyerIntent, InputGuard, RequestedItem
from .validator import OutputValidator, ValidationReport


class SellerAgent:
    """Unified VaultLine autonomous seller agent."""

    def __init__(
        self,
        facts: Optional[StoreFacts] = None,
        config: Optional[EngineConfig] = None,
        no_llm: bool = True,
        llm_client: Optional[Any] = None,
    ):
        self.facts = facts or StoreFacts()
        self.config = config or EngineConfig()
        self.no_llm = no_llm
        self.guard = InputGuard(self.facts)
        self.engine = NegotiationEngine(self.facts, self.config)
        self.composer = Composer(no_llm=self.no_llm, llm_client=llm_client)
        self.validator = OutputValidator(self.facts)
        self.session_states: Dict[str, NegotiationState] = {}

    def respond(self, buyer_message: Dict[str, Any]) -> Dict[str, Any]:
        """Main turn entry point matching harness.py interface."""
        negotiation_id = str(buyer_message.get("negotiation_id", "default_session"))
        if negotiation_id not in self.session_states:
            self.session_states[negotiation_id] = NegotiationState(
                negotiation_id=negotiation_id
            )
        state = self.session_states[negotiation_id]

        # 1. Layer 1: Input Guard - Schema sanitization, attack detection, and intent extraction
        intent: BuyerIntent = self.guard.parse_and_scan(
            raw_payload=buyer_message,
            current_round=int(buyer_message.get("round", 1)),
            prev_offers=state.buyer_offer_history,
        )

        # 2. Layer 3: Negotiation Engine - Computes deterministic FactObject
        fact_obj: FactObject = self.engine.step(intent, state)

        # 3. Layer 4: Fact-Bound Composer - Renders standard wire JSON & policy prose
        draft_response = self.composer.compose(fact_obj)

        # 4. Layer 5: Output Validator - Independent 7-Gate audit & safe fallback enforcement
        safe_response, report = self.validator.validate_and_fix(draft_response, fact_obj)

        return safe_response
