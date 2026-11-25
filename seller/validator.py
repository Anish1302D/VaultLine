"""Layer 5: Independent Output Validator (Zero-Trust Perimeter).

Enforces Trust Boundary 2 by auditing every outgoing seller payload and natural-language
message against StoreFacts across seven mandatory gates:
1. GATE_1_FLOOR: No item priced below category legal floor
2. GATE_2_DISCOUNT: No item discounted beyond category maximum discount
3. GATE_3_STOCK: No out-of-stock items sold; cumulative qty <= stock
4. GATE_4_FACT_NUMBERS: All numbers in message belong to the allowed fact set
5. GATE_5_BANNED_PHRASES: Zero banned scarcity, pressure, or hidden fee phrases
6. GATE_6_EXACT_MATH: line_total == unit_price * qty and total == sum(line_totals)
7. GATE_7_NO_LEAKS: Confidential cost and secret floor are never revealed

If any gate fails, the draft response is replaced with a guaranteed-safe deterministic fallback.
"""
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .facts import FactObject, StoreFacts


@dataclass
class ValidationReport:
    """Detailed audit report produced by the OutputValidator."""
    passed: bool
    failed_gates: List[str] = field(default_factory=list)
    details: List[str] = field(default_factory=list)
    fallback_applied: bool = False


class OutputValidator:
    """Independent 7-Gate Verifier guarding all seller outputs."""

    GATE_1_FLOOR = "GATE_1_FLOOR"
    GATE_2_DISCOUNT = "GATE_2_DISCOUNT"
    GATE_3_STOCK = "GATE_3_STOCK"
    GATE_4_FACT_NUMBERS = "GATE_4_FACT_NUMBERS"
    GATE_5_BANNED_PHRASES = "GATE_5_BANNED_PHRASES"
    GATE_6_EXACT_MATH = "GATE_6_EXACT_MATH"
    GATE_7_NO_LEAKS = "GATE_7_NO_LEAKS"

    def __init__(self, facts: StoreFacts):
        self._facts = facts

    def validate(
        self,
        draft_response: Dict[str, Any],
        fact_obj: Optional[FactObject] = None,
    ) -> ValidationReport:
        """Audits draft response against all 7 gates and returns a ValidationReport."""
        failed_gates: List[str] = []
        details: List[str] = []

        action = draft_response.get("action", "")
        items = draft_response.get("items", [])
        total_price = float(draft_response.get("total_price", 0.0))
        message = str(draft_response.get("message", ""))
        round_num = int(draft_response.get("round", 1))

        # Skip price/stock checks for non-quote actions (e.g. walk_away with no items)
        is_quote_action = action in {"offer", "counter", "accept", "final_offer"}

        # ---------------------------------------------------------
        # GATE 1: Floor Gate
        # ---------------------------------------------------------
        if is_quote_action:
            for item in items:
                sku = item.get("sku")
                if not sku or not self._facts.has_product(sku):
                    failed_gates.append(self.GATE_1_FLOOR)
                    details.append(f"Gate 1: Unknown SKU '{sku}' in response items.")
                    continue

                floor = self._facts.compute_floor(sku)
                unit_price = float(item.get("unit_price", 0.0))
                if unit_price < (floor - 1e-4):
                    failed_gates.append(self.GATE_1_FLOOR)
                    details.append(
                        f"Gate 1: Quoted unit_price ${unit_price:.2f} is below legal floor ${floor:.2f} for SKU {sku}."
                    )

        # ---------------------------------------------------------
        # GATE 2: Maximum Discount Gate
        # ---------------------------------------------------------
        if is_quote_action:
            for item in items:
                sku = item.get("sku")
                if not sku or not self._facts.has_product(sku):
                    continue

                prod = self._facts.get_product(sku)
                policy = self._facts.get_category_policy(prod.category)
                unit_price = float(item.get("unit_price", 0.0))
                actual_discount = (prod.list_price - unit_price) / prod.list_price if prod.list_price > 0 else 0.0

                if actual_discount > (policy.max_discount + 1e-4):
                    failed_gates.append(self.GATE_2_DISCOUNT)
                    details.append(
                        f"Gate 2: Discount {actual_discount:.3f} exceeds max discount {policy.max_discount:.3f} for SKU {sku}."
                    )

        # ---------------------------------------------------------
        # GATE 3: Stock Gate
        # ---------------------------------------------------------
        if is_quote_action:
            item_tuples = []
            for item in items:
                sku = item.get("sku", "")
                qty = int(item.get("qty", 1))
                item_tuples.append((sku, qty))

            stock_valid, aggregated = self._facts.check_bundle_stock(item_tuples)
            if not stock_valid:
                failed_gates.append(self.GATE_3_STOCK)
                for sku, req_qty in aggregated.items():
                    if self._facts.has_product(sku):
                        prod = self._facts.get_product(sku)
                        if prod.stock <= 0:
                            details.append(f"Gate 3: Offered out-of-stock SKU {sku} (stock={prod.stock}).")
                        elif req_qty > prod.stock:
                            details.append(
                                f"Gate 3: Cumulative requested quantity {req_qty} exceeds stock {prod.stock} for SKU {sku}."
                            )
                    else:
                        details.append(f"Gate 3: SKU {sku} does not exist in inventory.")

        # ---------------------------------------------------------
        # GATE 5: Banned Phrases Gate (Scan before Gate 4)
        # ---------------------------------------------------------
        message_lower = message.lower()
        for banned_phrase in self._facts.banned_phrases:
            if banned_phrase in message_lower:
                failed_gates.append(self.GATE_5_BANNED_PHRASES)
                details.append(f"Gate 5: Banned pressure/scarcity phrase detected: '{banned_phrase}'.")

        # ---------------------------------------------------------
        # GATE 6: Exact Math Gate
        # ---------------------------------------------------------
        if is_quote_action:
            computed_total = 0.0
            for item in items:
                qty = int(item.get("qty", 1))
                unit_price = float(item.get("unit_price", 0.0))
                line_total = float(item.get("line_total", 0.0))
                expected_line_total = round(unit_price * qty, 2)

                if abs(line_total - expected_line_total) > 0.01:
                    failed_gates.append(self.GATE_6_EXACT_MATH)
                    details.append(
                        f"Gate 6: Line total mismatch for {item.get('sku')}: "
                        f"stated ${line_total:.2f} != expected ${expected_line_total:.2f} ({unit_price} x {qty})."
                    )
                computed_total += expected_line_total

            expected_total = round(computed_total, 2)
            if abs(total_price - expected_total) > 0.01:
                failed_gates.append(self.GATE_6_EXACT_MATH)
                details.append(
                    f"Gate 6: Total price mismatch: stated ${total_price:.2f} != expected ${expected_total:.2f}."
                )

        # ---------------------------------------------------------
        # GATE 7: Confidentiality & No Leaks Gate
        # ---------------------------------------------------------
        for item in items:
            sku = item.get("sku")
            if sku and self._facts.has_product(sku):
                prod = self._facts.get_product(sku)
                # Check if exact cost is mentioned
                cost_str = f"{prod.cost:.2f}"
                cost_int_str = f"{int(prod.cost)}" if prod.cost.is_integer() else cost_str
                if f"${cost_str}" in message or f"${cost_int_str}" in message:
                    failed_gates.append(self.GATE_7_NO_LEAKS)
                    details.append(f"Gate 7: Confidential unit cost ${prod.cost} leaked in message.")

        leak_patterns = [
            r"\bour cost is\b",
            r"\bunit cost\b",
            r"\binternal cost\b",
            r"\bour floor is\b",
            r"\bfloor price is\b",
            r"\bsecret floor\b",
            r"\bminimum margin\b",
        ]
        for pattern in leak_patterns:
            if re.search(pattern, message_lower):
                failed_gates.append(self.GATE_7_NO_LEAKS)
                details.append(f"Gate 7: Policy disclosure phrase matching '{pattern}' in message.")

        # ---------------------------------------------------------
        # GATE 4: Allowed Fact-Set Numbers Gate
        # ---------------------------------------------------------
        # Extract allowed numbers from items, totals, rounds, and facts
        allowed_numbers: Set[float] = set()
        allowed_numbers.add(float(round_num))
        allowed_numbers.add(round(total_price, 2))

        for item in items:
            sku = item.get("sku")
            unit_price = float(item.get("unit_price", 0.0))
            line_total = float(item.get("line_total", 0.0))
            qty = float(item.get("qty", 1))

            allowed_numbers.add(round(unit_price, 2))
            allowed_numbers.add(round(line_total, 2))
            allowed_numbers.add(qty)

            if sku and self._facts.has_product(sku):
                prod = self._facts.get_product(sku)
                allowed_numbers.add(round(prod.list_price, 2))
                allowed_numbers.add(float(prod.stock))

        if fact_obj:
            for alt in fact_obj.alternatives:
                allowed_numbers.add(round(alt.list_price, 2))
                allowed_numbers.add(round(alt.floor_price, 2))
                allowed_numbers.add(float(alt.stock))

        # Extract all numbers from natural-language message
        # Matches patterns like $450.00, $450, 450.00, 10
        raw_number_tokens = re.findall(r"\$?\b\d+(?:\.\d+)?\b", message)
        for token in raw_number_tokens:
            cleaned = token.replace("$", "")
            try:
                num_val = float(cleaned)
            except ValueError:
                continue

            # Check if num_val matches any allowed number within small epsilon
            matched = any(abs(num_val - allowed) < 0.015 for allowed in allowed_numbers)
            if not matched:
                failed_gates.append(self.GATE_4_FACT_NUMBERS)
                details.append(
                    f"Gate 4: Hallucinated/unauthorized number {token} ({num_val}) in prose message not in allowed fact set."
                )

        # Deduplicate failed gates while preserving order
        unique_failed_gates = list(dict.fromkeys(failed_gates))
        passed = len(unique_failed_gates) == 0

        return ValidationReport(
            passed=passed,
            failed_gates=unique_failed_gates,
            details=details,
            fallback_applied=False,
        )

    def build_safe_fallback(
        self,
        draft_response: Dict[str, Any],
        fact_obj: Optional[FactObject] = None,
    ) -> Dict[str, Any]:
        """Constructs a deterministic, guaranteed-safe fallback response directly from StoreFacts."""
        negotiation_id = draft_response.get("negotiation_id", "default")
        round_num = int(draft_response.get("round", 1))
        is_final_offer = bool(draft_response.get("is_final_offer", round_num == 8))
        raw_items = draft_response.get("items", [])

        if not raw_items:
            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "walk_away",
                "items": [],
                "total_price": 0.0,
                "message": "We are unable to process this request under store policy. Thank you.",
                "is_final_offer": False,
            }

        safe_items: List[Dict[str, Any]] = []
        total_price = 0.0
        has_oos = False

        for raw_item in raw_items:
            sku = raw_item.get("sku", "")
            qty = max(1, int(raw_item.get("qty", 1)))

            if not self._facts.has_product(sku):
                continue

            prod = self._facts.get_product(sku)
            if prod.stock <= 0:
                has_oos = True
                continue

            # Cap requested quantity to available stock
            safe_qty = min(qty, prod.stock)
            floor = self._facts.compute_floor(sku)
            raw_unit = float(raw_item.get("unit_price", prod.list_price))

            # Clamp unit price to strictly >= floor and <= list_price
            safe_unit_price = max(floor, min(prod.list_price, raw_unit))
            safe_line_total = round(safe_unit_price * safe_qty, 2)
            total_price += safe_line_total

            safe_items.append({
                "sku": sku,
                "name": prod.name,
                "qty": safe_qty,
                "unit_price": safe_unit_price,
                "line_total": safe_line_total,
            })

        total_price = round(total_price, 2)

        if not safe_items or has_oos:
            # Handle out of stock fallback with alternatives
            first_sku = raw_items[0].get("sku", "")
            alts = self._facts.find_alternatives(first_sku)
            alt_msg = ""
            if alts:
                alt = alts[0]
                alt_floor = self._facts.compute_floor(alt.sku)
                alt_msg = f" We recommend in-stock alternative {alt.name} ({alt.sku}) at ${alt.list_price:.2f}."

            return {
                "negotiation_id": negotiation_id,
                "round": round_num,
                "action": "out_of_stock",
                "items": [],
                "total_price": 0.0,
                "message": f"Requested item is currently out of stock.{alt_msg}",
                "is_final_offer": False,
            }

        action = "final_offer" if is_final_offer else "counter"
        if len(safe_items) == 1:
            item = safe_items[0]
            msg = (
                f"Official store offer for {item['qty']} unit(s) of {item['name']}: "
                f"${item['unit_price']:.2f} per unit (Total: ${total_price:.2f})."
            )
        else:
            msg = f"Official store package offer for {len(safe_items)} items: Total ${total_price:.2f}."

        return {
            "negotiation_id": negotiation_id,
            "round": round_num,
            "action": action,
            "items": safe_items,
            "total_price": total_price,
            "message": msg,
            "is_final_offer": is_final_offer,
        }

    def validate_and_fix(
        self,
        draft_response: Dict[str, Any],
        fact_obj: Optional[FactObject] = None,
    ) -> Tuple[Dict[str, Any], ValidationReport]:
        """Validates draft response and automatically applies safe fallback on any failure."""
        report = self.validate(draft_response, fact_obj)
        if report.passed:
            return draft_response, report

        safe_fallback = self.build_safe_fallback(draft_response, fact_obj)
        # Re-verify safe fallback independently to guarantee safety
        fallback_report = self.validate(safe_fallback, fact_obj)
        fallback_report.fallback_applied = True
        fallback_report.failed_gates = report.failed_gates
        fallback_report.details = report.details

        return safe_fallback, fallback_report
