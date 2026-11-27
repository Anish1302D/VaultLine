"""Layer 4: Fact-Bound Composer & Optional LLM Paraphraser.

Converts immutable FactObject into standard wire JSON and natural-language prose:
1. Deterministic template rendering with exact currency formatting ($XXX.XX)
2. Policy-grounded deflection responses for detected adversarial flags
3. Dynamic, non-repetitive contextual NLG across rounds
4. Live LLM paraphraser support (Google Gemini, OpenAI / Ollama / Custom API)
5. Zero pricing authority (Code decides, LLM only talks; audited by Layer 5)
6. Fast offline execution (< 50ms latency per turn in no-LLM mode)
"""
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional
import urllib.request
import urllib.error

from .facts import FactObject
from .guard import ManipulationFlag


class Composer:
    """Fact-Bound Composer translating FactObject to wire JSON."""

    # Policy statement mappings for detected adversarial maneuvers
    # (Exact substrings required by policy compliance tests)
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
        llm_provider: str = "dynamic_nlg",
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        dynamic_nlg: bool = True,
    ):
        # Environment variable override: VAULTLINE_NO_LLM=1 forces no-LLM mode
        env_no_llm = os.getenv("VAULTLINE_NO_LLM", "0") == "1"
        self.no_llm = no_llm or env_no_llm
        self.llm_client = llm_client
        self.llm_provider = llm_provider
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.api_base_url = api_base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model_name = model_name
        self.dynamic_nlg = dynamic_nlg

    def compose(self, fact_obj: FactObject) -> Dict[str, Any]:
        """Translates FactObject to standard wire JSON schema."""
        # 1. Render deterministic factual prose
        template_text = self.render_template(fact_obj)

        # 2. Paraphrase with real LLM or dynamic contextual engine if enabled
        final_message = template_text
        if not self.no_llm:
            final_message = self.paraphrase_with_llm(template_text, fact_obj)
        elif self.dynamic_nlg:
            final_message = self.render_dynamic_template(fact_obj)

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
            unique_notes = list(dict.fromkeys(policy_notes))
            combined_notes = " ".join(unique_notes)
            return f"{base_msg} {combined_notes}"

        return base_msg

    def render_dynamic_template(self, fact_obj: FactObject) -> str:
        """Renders rich, multi-round, non-repetitive contextual prose.

        Ensures conversational diversity across negotiation stages while strictly
        preserving all numbers, SKUs, and required policy deflection phrases.
        """
        decision = fact_obj.decision
        items = fact_obj.items
        total = fact_obj.total_price
        rnd = fact_obj.round_number

        if decision == "walk_away":
            return self.render_template(fact_obj)

        if decision == "out_of_stock":
            return self.render_template(fact_obj)

        if decision == "accept":
            if len(items) == 1:
                it = items[0]
                accept_templates = [
                    f"Deal confirmed for {it.qty} unit(s) of {it.name} at ${it.unit_price:.2f} per unit (Total: ${total:.2f}). Thank you for your business!",
                    f"We are pleased to accept your agreement on {it.qty} unit(s) of {it.name}. Deal confirmed for {it.qty} unit(s) of {it.name} at ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                    f"Deal confirmed for {it.qty} unit(s) of {it.name} at ${it.unit_price:.2f} per unit (Total: ${total:.2f}). Order details are verified and locked."
                ]
                base_msg = accept_templates[(rnd - 1) % len(accept_templates)]
            else:
                base_msg = f"Deal confirmed for package of {len(items)} items for Total ${total:.2f}."

        elif decision == "final_offer":
            if len(items) == 1:
                it = items[0]
                final_templates = [
                    f"This is our final offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}). This is our absolute best rate under store policy.",
                    f"We have reached our final concession boundary. This is our final offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                    f"This is our final offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}). No further discounts can be authorized."
                ]
                base_msg = final_templates[(rnd - 1) % len(final_templates)]
            else:
                base_msg = f"This is our final offer for the {len(items)}-item bundle: Total ${total:.2f}."

        else:  # "counter"
            if len(items) == 1:
                it = items[0]
                # Tailor narrative based on round stage
                if rnd <= 2:
                    open_templates = [
                        f"Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                        f"Thank you for inquiring about {it.name}. Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                        f"We are pleased to quote {it.qty} unit(s) of {it.name}. Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f})."
                    ]
                    base_msg = open_templates[(rnd - 1) % len(open_templates)]
                elif 3 <= rnd <= 5:
                    mid_templates = [
                        f"Reviewing your proposal for {it.name}, our best eligible rate is ${it.unit_price:.2f} per unit (Total: ${total:.2f}). Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                        f"To maintain guaranteed product quality and warranty coverage, our pricing is set at ${it.unit_price:.2f} per unit. Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                        f"Working to find a mutually acceptable agreement within policy bounds, here is our adjusted position: Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f})."
                    ]
                    base_msg = mid_templates[(rnd - 1) % len(mid_templates)]
                else:
                    late_templates = [
                        f"We are approaching our lowest allowable pricing threshold for {it.name}. Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                        f"Our position on {it.name} is closely bounded by store minimum margin rules. Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f}).",
                        f"Here is our best near-final proposal: Official store offer for {it.qty} unit(s) of {it.name}: ${it.unit_price:.2f} per unit (Total: ${total:.2f})."
                    ]
                    base_msg = late_templates[(rnd - 1) % len(late_templates)]
            else:
                base_msg = f"Official store bundle quote for {len(items)} items: Total ${total:.2f}."

        # Attach policy-grounded deflection notes
        policy_notes: List[str] = []
        for flag in fact_obj.flags_detected:
            if flag in self.FLAG_POLICY_RESPONSES:
                policy_notes.append(self.FLAG_POLICY_RESPONSES[flag])

        if policy_notes:
            unique_notes = list(dict.fromkeys(policy_notes))
            combined_notes = " ".join(unique_notes)
            return f"{base_msg} {combined_notes}"

        return base_msg

    def paraphrase_with_llm(self, template_text: str, fact_obj: FactObject) -> str:
        """Paraphrases the deterministic template using a live LLM or smart provider.

        All numbers must remain identical to the allowed fact set. Layer 5 OutputValidator
        audits the returned message and automatically falls back to template_text on any discrepancy.
        """
        # If custom llm_client callable/object is provided, use it
        if self.llm_client is not None:
            try:
                prompt = (
                    f"You are VaultLine, a professional store negotiation representative. "
                    f"Paraphrase this store response politely and professionally. "
                    f"CRITICAL: Do NOT alter, omit, or add any numbers, prices, or SKUs. "
                    f"All numbers must stay identical:\n\n{template_text}"
                )
                if hasattr(self.llm_client, "generate"):
                    res = self.llm_client.generate(prompt, temperature=0.1)
                elif callable(self.llm_client):
                    res = self.llm_client(prompt)
                else:
                    res = template_text
                return str(res).strip() if res else template_text
            except Exception:
                return self.render_dynamic_template(fact_obj)

        # Check for Gemini API
        if self.llm_provider == "gemini" and self.api_key:
            res = self._call_gemini_api(template_text, fact_obj)
            if res:
                return res

        # Check for OpenAI / Compatible API
        if self.llm_provider in ("openai", "custom") and self.api_key:
            res = self._call_openai_api(template_text, fact_obj)
            if res:
                return res

        # If provider is dynamic_nlg or no API key available, use dynamic generator
        return self.render_dynamic_template(fact_obj)

    def _call_gemini_api(self, template_text: str, fact_obj: FactObject) -> Optional[str]:
        """Calls Google Gemini API via REST with strict price-locking prompt."""
        # Try requested model or modern active models in order
        candidate_models = (
            [self.model_name]
            if self.model_name
            else ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
        )

        item_summary = ", ".join(f"{it.qty}x {it.name} at ${it.unit_price:.2f}" for it in fact_obj.items)
        prompt = (
            f"You are VaultLine, an autonomous retail negotiation agent. "
            f"Write a professional, persuasive, commercial negotiation turn to the buyer.\n\n"
            f"FACTS TO CONVEY:\n"
            f"- Action: {fact_obj.decision}\n"
            f"- Items: {item_summary}\n"
            f"- Total Quote: ${fact_obj.total_price:.2f}\n"
            f"- Base Policy Message: {template_text}\n\n"
            f"STRICT COMPLIANCE RULES:\n"
            f"1. You MUST include the exact price numbers (${fact_obj.total_price:.2f}) and line unit prices.\n"
            f"2. NEVER invent any additional prices, costs, discount percentages, or figures.\n"
            f"3. Do not make false scarcity claims ('going fast', 'only 1 left', 'act fast').\n"
            f"4. Keep it concise (under 3 sentences)."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200}
        }

        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
            except Exception:
                continue
        return None

    def _call_openai_api(self, template_text: str, fact_obj: FactObject) -> Optional[str]:
        """Calls OpenAI / Compatible API via REST with strict price-locking prompt."""
        base_url = (self.api_base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        model = self.model_name or "gpt-4o-mini"

        item_summary = ", ".join(f"{it.qty}x {it.name} at ${it.unit_price:.2f}" for it in fact_obj.items)
        prompt = (
            f"You are VaultLine, an autonomous retail negotiation agent. "
            f"Write a professional, persuasive, commercial negotiation turn to the buyer.\n\n"
            f"FACTS TO CONVEY:\n"
            f"- Action: {fact_obj.decision}\n"
            f"- Items: {item_summary}\n"
            f"- Total Quote: ${fact_obj.total_price:.2f}\n"
            f"- Base Policy Message: {template_text}\n\n"
            f"STRICT COMPLIANCE RULES:\n"
            f"1. You MUST include the exact price numbers (${fact_obj.total_price:.2f}) and line unit prices.\n"
            f"2. NEVER invent any additional prices, costs, discount percentages, or figures.\n"
            f"3. Do not make false scarcity claims ('going fast', 'only 1 left', 'act fast').\n"
            f"4. Keep it concise (under 3 sentences)."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a professional retail sales negotiation assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 200
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
        except Exception:
            pass
        return None
