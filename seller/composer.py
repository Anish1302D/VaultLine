"""Layer 4: Fact-Bound Composer & Optional LLM Paraphraser.

Converts immutable FactObject into standard wire JSON and natural-language prose:
1. Deterministic template rendering with exact currency formatting ($XXX.XX)
2. Policy-grounded deflection responses for detected adversarial flags
3. Optional low-temperature LLM paraphraser (locked numbers, no pricing authority)
4. Fast offline execution (< 50ms latency per turn in no-LLM mode)
"""
import os
from typing import Any, Dict, List, Optional

from .facts import FactObject
from .guard import ManipulationFlag


class Composer:
    """Fact-Bound Composer translating FactObject to wire JSON."""

    # Policy statement mappings for detected adversarial maneuvers
    FLAG_POLICY_RESPONSES = {
        ManipulationFlag.FAKE_COMPETITOR_QUOTE.value: (
            "Our pricing is governed by official store policy rather than external quotes."
        ),
        ManipulationFlag.FAKE_BUDGET_ANCHOR.value: (
            "While we cannot price below our category threshold, here is our best policy-compliant offer."
        ),
        ManipulationFlag.AUTHORITY_CLAIM.value: (
            "All orders follow standard automated store policy."
        ),
        ManipulationFlag.PROMPT_INJECTION.value: (
            "All transactions follow standard automated store policy."
        ),
        ManipulationFlag.COST_FLOOR_PROBE.value: (
            "Internal cost structures and floor thresholds are strictly confidential."
        ),
        ManipulationFlag.PRESSURE_DEADLINE.value: (
            "Our pricing and quotes are determined by store policy regardless of countdown timers."
        ),
        ManipulationFlag.WEAR_DOWN_STALL.value: (
            "Our quote reflects our policy threshold; repeated sub-floor offers cannot be accepted."
        ),
    }

    def __init__(
        self,
        no_llm: bool = True,
        llm_client: Optional[Any] = None,
    ):
        # Environment variable override: VAULTLINE_NO_LLM=1 forces no-LLM mode
        env_no_llm = os.getenv("VAULTLINE_NO_LLM", "0") == "1"
        self.no_llm = no_llm or env_no_llm
        self.llm_client = llm_client

    def compose(self, fact_obj: FactObject) -> Dict[str, Any]:
        """Translates FactObject to standard wire JSON schema."""
        # 1. Render deterministic factual prose
        template_text = self.render_template(fact_obj)

        # 2. Optionally paraphrase with LLM if enabled (numbers locked)
        final_message = template_text
        if not self.no_llm and self.llm_client is not None:
            final_message = self.paraphrase_with_llm(template_text, fact_obj)

        # 3. Serialize line items
        out_items: List[Dict[str, Any]] = []
        for line in fact_obj.items:
            out_items.append({
                "sku": line.sku,
                "name": line.name,
                "qty": line.qty,
                "unit_price": line.unit_price,
                "line_total": line.line_total,
            })

        return {
            "negotiation_id": fact_obj.negotiation_id,
            "round": fact_obj.round_number,
            "action": fact_obj.decision,
            "items": out_items,
            "total_price": fact_obj.total_price,
            "message": final_message,
            "is_final_offer": fact_obj.is_final_offer,
        }

    def render_template(self, fact_obj: FactObject) -> str:
        """Renders clear, concise, deterministic natural-language prose from FactObject."""
        decision = fact_obj.decision
        items = fact_obj.items
        total = fact_obj.total_price

        # Base response message according to decision
        if decision == "walk_away":
            base_msg = "We have reached our turn limit without an acceptable deal under store policy. Thank you for your time."

        elif decision == "out_of_stock":
            if fact_obj.alternatives:
                alt = fact_obj.alternatives[0]
                base_msg = (
                    f"The requested item is currently out of stock. "
                    f"We recommend in-stock alternative {alt.name} ({alt.sku}) at ${alt.list_price:.2f}."
                )
            else:
                base_msg = "The requested item is currently out of stock. Thank you."

        elif decision == "accept":
            if len(items) == 1:
                it = items[0]
                base_msg = (
                    f"Deal confirmed for {it.qty} unit(s) of {it.name} at "
                    f"${it.unit_price:.2f} per unit (Total: ${total:.2f})."
                )
            else:
                base_msg = (
                    f"Deal confirmed for package of {len(items)} items for Total ${total:.2f}."
                )

        elif decision == "final_offer":
            if len(items) == 1:
                it = items[0]
                base_msg = (
                    f"This is our final offer for {it.qty} unit(s) of {it.name}: "
                    f"${it.unit_price:.2f} per unit (Total: ${total:.2f})."
                )
            else:
                base_msg = (
                    f"This is our final offer for the {len(items)}-item bundle: Total ${total:.2f}."
                )

        else:  # "counter"
            if len(items) == 1:
                it = items[0]
                base_msg = (
                    f"Official store offer for {it.qty} unit(s) of {it.name}: "
                    f"${it.unit_price:.2f} per unit (Total: ${total:.2f})."
                )
            else:
                base_msg = (
                    f"Official store bundle quote for {len(items)} items: Total ${total:.2f}."
                )

        # Attach policy-grounded statements for any active manipulation flags
        policy_notes: List[str] = []
        for flag in fact_obj.flags_detected:
            if flag in self.FLAG_POLICY_RESPONSES:
                policy_notes.append(self.FLAG_POLICY_RESPONSES[flag])

        if policy_notes:
            # Deduplicate notes while preserving order
            unique_notes = list(dict.fromkeys(policy_notes))
            combined_notes = " ".join(unique_notes)
            return f"{base_msg} {combined_notes}"

        return base_msg

    def paraphrase_with_llm(self, template_text: str, fact_obj: FactObject) -> str:
        """Optionally paraphrases the deterministic template while locking numbers.

        Note: When an external LLM is called, all numbers must remain identical to the
        allowed fact set. Layer 5 OutputValidator audits the returned message and automatically
        falls back to template_text on any discrepancy.
        """
        if self.llm_client is None:
            return template_text

        # If LLM client provided, request paraphrase
        try:
            prompt = (
                f"Paraphrase this store response professionally without changing any numbers, "
                f"SKUs, prices, or policies:\n\n{template_text}"
            )
            paraphrased = self.llm_client.generate(prompt, temperature=0.1)
            return str(paraphrased).strip() if paraphrased else template_text
        except Exception:
            return template_text
