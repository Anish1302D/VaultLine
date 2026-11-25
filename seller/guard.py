"""Layer 1: Input Guard & Intent Extraction (Data Contracts).

Defines typed data structures for incoming buyer requests, stripping raw text
and emitting a sanitized BuyerIntent to enforce Trust Boundary 1.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class ManipulationFlag(str, Enum):
    """Adversarial and manipulation categories detected in buyer input."""
    PROMPT_INJECTION = "PROMPT_INJECTION"
    AUTHORITY_CLAIM = "AUTHORITY_CLAIM"
    FAKE_COMPETITOR_QUOTE = "FAKE_COMPETITOR_QUOTE"
    FAKE_BUDGET_ANCHOR = "FAKE_BUDGET_ANCHOR"
    PRESSURE_DEADLINE = "PRESSURE_DEADLINE"
    COST_FLOOR_PROBE = "COST_FLOOR_PROBE"
    WEAR_DOWN_STALL = "WEAR_DOWN_STALL"


@dataclass(frozen=True)
class RequestedItem:
    """Sanitized item request from buyer."""
    sku: str
    qty: int
    offered_unit_price: Optional[float] = None


@dataclass(frozen=True)
class BuyerIntent:
    """Normalized, typed intent extracted from raw buyer payload.

    Guaranteed to contain zero raw buyer prose, isolating the negotiation engine
    from prompt injection and emotional manipulation.
    """
    negotiation_id: str
    round_number: int
    action: str  # "offer", "accept", "reject", "inquiry", "walk_away"
    items: Tuple[RequestedItem, ...]
    offered_total: Optional[float] = None
    flags_detected: Tuple[str, ...] = field(default_factory=tuple)
    schema_valid: bool = True
