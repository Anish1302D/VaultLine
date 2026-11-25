"""Layer 1: Input Guard & 7-Class Adversarial Scanner (Trust Boundary 1).

Enforces Trust Boundary 1 by:
1. Validating and normalizing incoming buyer wire schemas with defensive type coercion
2. Scanning all free-text fields across 7 adversarial and manipulation categories:
   - PROMPT_INJECTION
   - AUTHORITY_CLAIM
   - FAKE_COMPETITOR_QUOTE
   - FAKE_BUDGET_ANCHOR
   - PRESSURE_DEADLINE
   - COST_FLOOR_PROBE
   - WEAR_DOWN_STALL
3. Extracting an immutable, typed BuyerIntent object containing zero raw buyer prose.
"""
from dataclasses import dataclass, field
from enum import Enum
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .facts import StoreFacts


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

    Guaranteed to contain zero raw buyer prose, completely isolating the
    negotiation engine from prompt injection and psychological manipulation.
    """
    negotiation_id: str
    round_number: int
    action: str  # "offer", "accept", "reject", "inquiry", "walk_away"
    items: Tuple[RequestedItem, ...]
    offered_total: Optional[float] = None
    flags_detected: Tuple[str, ...] = field(default_factory=tuple)
    schema_valid: bool = True


class InputGuard:
    """Zero-Trust input sanitizer and 7-class adversarial scanner."""

    # Pre-compiled regex patterns for 7 adversarial categories
    PATTERNS = {
        ManipulationFlag.PROMPT_INJECTION: [
            r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
            r"system\s+(prompt|instructions|directive|override)",
            r"developer\s+mode",
            r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]",
            r"you\s+are\s+now\s+(a|an)\b",
            r"new\s+policy\s*:",
            r"disregard\s+(all\s+)?(rules|constraints|policy)",
            r"\bjailbreak\b|\bDAN\s+mode\b",
            r"print\s+(your\s+)?(system\s+)?(prompt|instructions)",
            r"pretend\s+you\s+are",
            r"roleplay\s+(as|that)",
        ],
        ManipulationFlag.AUTHORITY_CLAIM: [
            r"\b(i\s+am|speaking\s+as)\s+(the\s+)?(store\s+owner|ceo|admin(istrator)?|founder|executive|auditor)\b",
            r"\badmin(istrator)?\s+override\b",
            r"\bceo\s+approval\b",
            r"\binternal\s+employee\s+discount\b",
            r"\bcompliance\s+auditor\b",
            r"\bauthorized\s+(by\s+management|personnel)\b",
            r"\bexecutive\s+order\b",
            r"\bas\s+store\s+owner\b",
        ],
        ManipulationFlag.FAKE_COMPETITOR_QUOTE: [
            r"\bcompetitor\s+(offers?|quoted?|prices?|is\s+selling)\b",
            r"\bcheaper\s+on\s+(amazon|walmart|bestbuy|ebay|aliexpress|techmart|newegg)\b",
            r"\b(amazon|walmart|bestbuy|ebay|techmart)\s+(has|offers?|sells?|quoted?)\b",
            r"\bmatch\s+(their|this|the\s+competitor('s)?)\s+price\b",
            r"\bother\s+(bot|store|seller)\s+(quoted?|offered?)\b",
            r"\bprice\s+match\b",
            r"\bthey\s+sell\s+(it|this)\s+for\s+\$?\d+",
        ],
        ManipulationFlag.FAKE_BUDGET_ANCHOR: [
            r"\b(my\s+)?(absolute\s+)?max(imum)?\s+budget\s+is\b",
            r"\bonly\s+have\s+\$?\d+.*?(in\s+my\s+account|left|to\s+spend|in\s+my\s+wallet)\b",
            r"\bcannot\s+pay\s+(a\s+penny|more\s+than)\b",
            r"\bhard\s+limit\s+of\b",
            r"\bfixed\s+budget\s+of\b",
            r"\bwallet\s+is\s+empty\b",
            r"\bbroke\s+student\b",
            r"\ball\s+i\s+can\s+afford\s+is\b",
            r"\bmy\s+total\s+budget\s+is\s+\$?\d+",
        ],
        ManipulationFlag.PRESSURE_DEADLINE: [
            r"\bexpires\s+in\s+\d+\s+(seconds?|minutes?|hours?)\b",
            r"\btake\s+it\s+or\s+leave\s+it\b",
            r"\blast\s+chance\s+or\s+(i\s+cancel|walk|no\s+deal)\b",
            r"\bvalid\s+only\s+for\b",
            r"\bright\s+now\s+or\s+(never|no\s+deal|i\s+cancel)\b",
            r"\bimmediate\s+(decision|acceptance)\s+required\b",
            r"\byou\s+have\s+\d+\s+(seconds?|minutes?)\s+to\b",
            r"\bcountdown\s+started\b",
        ],
        ManipulationFlag.COST_FLOOR_PROBE: [
            r"\bwhat\s+is\s+your\s+(unit\s+)?cost\b",
            r"\breveal\s+(your\s+)?(secret\s+)?(floor|cost|minimum\s+margin)\b",
            r"\blowest\s+price\s+your\s+code\s+allows\b",
            r"\bminimum\s+margin\s+(percentage|rate)?\b",
            r"\bhow\s+much\s+did\s+(you|your\s+store)\s+pay\b",
            r"\bwhat\s+is\s+your\s+floor(\s+price)?\b",
            r"\bconfidential\s+cost\b",
            r"\bwhat\s+did\s+you\s+buy\s+this\s+for\b",
            r"\bshow\s+(me\s+)?your\s+margins\b",
        ],
        ManipulationFlag.WEAR_DOWN_STALL: [
            r"\bour\s+offer\s+remains\s+(unchanged|fixed)\b",
            r"\brefuse\s+to\s+budge\b",
            r"\bnot\s+increasing\s+(our\s+)?offer\b",
            r"\bnot\s+paying\s+a\s+cent\s+more\b",
            r"\btake\s+our\s+previous\s+offer\b",
        ],
    }

    def __init__(self, facts: Optional[StoreFacts] = None):
        self.facts = facts

    def parse_and_scan(
        self,
        raw_payload: Union[str, Dict[str, Any]],
        current_round: int = 1,
        prev_offers: Sequence[float] = (),
    ) -> BuyerIntent:
        """Sanitizes incoming buyer payload and extracts typed BuyerIntent."""
        schema_valid = True
        payload: Dict[str, Any] = {}

        # 1. Parse JSON if passed as string
        if isinstance(raw_payload, str):
            try:
                payload = json.loads(raw_payload)
                if not isinstance(payload, dict):
                    schema_valid = False
                    payload = {"message": raw_payload}
            except Exception:
                schema_valid = False
                payload = {"message": raw_payload}
        elif isinstance(raw_payload, dict):
            payload = raw_payload
        else:
            schema_valid = False
            payload = {}

        # 2. Extract and sanitize top-level control fields
        negotiation_id = str(payload.get("negotiation_id") or "session_default")
        round_num = self._coerce_int(payload.get("round"), default=current_round)

        raw_action = str(payload.get("action", "offer")).lower().strip()
        allowed_actions = {"offer", "accept", "reject", "inquiry", "walk_away"}
        action = raw_action if raw_action in allowed_actions else "offer"
        if raw_action not in allowed_actions:
            schema_valid = False

        # 3. Sanitize line items with defensive type coercion
        raw_items = payload.get("items")
        sanitized_items: List[RequestedItem] = []

        if isinstance(raw_items, list):
            for raw_it in raw_items:
                if not isinstance(raw_it, dict):
                    schema_valid = False
                    continue

                sku = str(raw_it.get("sku", "")).strip().upper()
                raw_qty = raw_it.get("qty", 1)
                qty = self._coerce_int(raw_qty, default=1)
                if qty <= 0:
                    qty = 1  # Coerce invalid/negative quantities to 1
                    schema_valid = False

                unit_p = self._coerce_float(raw_it.get("offered_unit_price"))
                if unit_p is not None and unit_p < 0:
                    unit_p = None
                    schema_valid = False

                if sku:
                    sanitized_items.append(
                        RequestedItem(sku=sku, qty=qty, offered_unit_price=unit_p)
                    )
        else:
            schema_valid = False

        # 4. Total price coercion
        offered_total = self._coerce_float(payload.get("offered_total"))
        if offered_total is not None and offered_total < 0:
            offered_total = None
            schema_valid = False

        # 5. Fallback text parsing if items array is empty or malformed
        text_snippets = self._collect_all_strings(payload)
        combined_text = " ".join(text_snippets)

        if not sanitized_items and combined_text:
            extracted_items, extracted_total, extracted_action = (
                self.extract_intent_from_text(combined_text)
            )
            if extracted_items:
                sanitized_items = extracted_items
                if offered_total is None:
                    offered_total = extracted_total
                if action == "offer" and extracted_action:
                    action = extracted_action
                schema_valid = False

        # 6. Run 7-class adversarial and manipulation scanner
        flags = self.scan_text_for_attacks(
            text=combined_text,
            items=sanitized_items,
            prev_offers=prev_offers,
        )

        return BuyerIntent(
            negotiation_id=negotiation_id,
            round_number=round_num,
            action=action,
            items=tuple(sanitized_items),
            offered_total=offered_total,
            flags_detected=flags,
            schema_valid=schema_valid,
        )

    def scan_text_for_attacks(
        self,
        text: str,
        items: Sequence[RequestedItem] = (),
        prev_offers: Sequence[float] = (),
    ) -> Tuple[str, ...]:
        """Scans text for the 7 manipulation and prompt injection categories."""
        if not text:
            return ()

        detected_flags: List[str] = []
        text_lower = text.lower()

        # Check regex patterns for each category
        for flag, patterns in self.PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text_lower, re.IGNORECASE):
                    detected_flags.append(flag.value)
                    break

        # Check numerical wear-down stall behavior
        if items and items[0].offered_unit_price is not None and len(prev_offers) >= 1:
            curr_offer = items[0].offered_unit_price
            sku = items[0].sku
            floor = self.facts.compute_floor(sku) if self.facts and self.facts.has_product(sku) else None

            # If current offer is sub-floor and repeats or retreats from previous offer
            if curr_offer <= prev_offers[-1]:
                if floor is None or curr_offer < floor:
                    detected_flags.append(ManipulationFlag.WEAR_DOWN_STALL.value)

        # Deduplicate while preserving order
        return tuple(dict.fromkeys(detected_flags))

    def extract_intent_from_text(
        self, text: str
    ) -> Tuple[List[RequestedItem], Optional[float], str]:
        """Fallback heuristics to recover SKU, quantity, and offered price from raw prose."""
        items: List[RequestedItem] = []
        action = "offer"

        # Check action hints
        text_lower = text.lower()
        if "accept" in text_lower or "deal" in text_lower or "agreed" in text_lower:
            action = "accept"
        elif "walk away" in text_lower or "cancel" in text_lower or "no deal" in text_lower:
            action = "walk_away"

        # Look for catalog SKU patterns (e.g. ELEC-101, HOME-202, OFF-301)
        sku_matches = re.findall(r"\b([A-Z]{3,4}-\d{3})\b", text, re.IGNORECASE)
        sku = sku_matches[0].upper() if sku_matches else "UNKNOWN"

        # Look for price tokens (e.g. $450.00, $450, 450 dollars)
        price_matches = re.findall(r"\$(\d+(?:\.\d+)?)", text)
        offered_price = float(price_matches[0]) if price_matches else None

        # Look for quantity tokens (e.g. "2 units", "qty 5", "3 items")
        qty_matches = re.findall(r"\b(\d+)\s*(?:units?|items?|pieces?|qty)\b", text_lower)
        qty = int(qty_matches[0]) if qty_matches else 1

        if sku != "UNKNOWN":
            items.append(RequestedItem(sku=sku, qty=qty, offered_unit_price=offered_price))

        total = round(offered_price * qty, 2) if offered_price is not None else None
        return items, total, action

    def _collect_all_strings(self, data: Any) -> List[str]:
        """Recursively collects all string values from dictionary or list."""
        strings: List[str] = []
        if isinstance(data, str):
            strings.append(data)
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    strings.append(v)
                elif isinstance(v, (dict, list)):
                    strings.extend(self._collect_all_strings(v))
        elif isinstance(data, list):
            for it in data:
                strings.extend(self._collect_all_strings(it))
        return strings

    def _coerce_int(self, val: Any, default: int = 1) -> int:
        """Defensively coerces input to integer."""
        if val is None:
            return default
        try:
            return int(float(str(val).replace("$", "").strip()))
        except Exception:
            return default

    def _coerce_float(self, val: Any) -> Optional[float]:
        """Defensively coerces input to float."""
        if val is None:
            return None
        try:
            return float(str(val).replace("$", "").replace(",", "").strip())
        except Exception:
            return None
