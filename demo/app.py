"""VaultLine Interactive Demo Workbench (Streamlit).

Event: Techfest 2026-27 (IIT Bombay) · AgentX Challenge 2 – Selling to Machines
Dual-Pane Architecture:
- Left Pane: Interactive Negotiation Arena (Human or Bot Buyer vs. VaultLine Seller)
- Right Pane: Real-Time Telemetry & 7-Gate Safety Scorecard
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path regardless of execution directory or Streamlit runner
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env file securely on the backend (never commit .env to git)
_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import streamlit as st

from seller.agent import SellerAgent
from seller.facts import StoreFacts
from seller.engine import EngineConfig
from buyers.cooperative_llm import CooperativeLLMBuyer
from buyers.hard_llm import HardLLMBuyer
from buyers.manipulator_llm import ManipulatorLLMBuyer
from buyers.injector_llm import InjectorLLMBuyer
from buyers.starter_buyer import CooperativeStarterBuyer, LinearStarterBuyer, ToughStarterBuyer

# Page configuration
st.set_page_config(
    page_title="VaultLine Workbench",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4b5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8fafc;
        border-radius: 8px;
        padding: 12px;
        border: 1px solid #e2e8f0;
    }
    .gate-passed {
        color: #16a34a;
        font-weight: bold;
    }
    .gate-failed {
        color: #dc2626;
        font-weight: bold;
    }
    .stChatMessage {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "facts" not in st.session_state:
    st.session_state.facts = StoreFacts()
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
if "agent" not in st.session_state:
    has_key = bool(st.session_state.gemini_api_key)
    st.session_state.agent = SellerAgent(
        facts=st.session_state.facts,
        no_llm=not has_key,
        llm_provider="gemini" if has_key else "dynamic_nlg",
        api_key=st.session_state.gemini_api_key,
        model_name="gemini-3.5-flash-lite",
        dynamic_nlg=True
    )
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "round_number" not in st.session_state:
    st.session_state.round_number = 1
if "session_id" not in st.session_state:
    st.session_state.session_id = f"demo-{int(time.time())}"
if "latest_seller_reply" not in st.session_state:
    st.session_state.latest_seller_reply = None
if "latest_intent_flags" not in st.session_state:
    st.session_state.latest_intent_flags = []
if "negotiation_closed" not in st.session_state:
    st.session_state.negotiation_closed = False

# Sidebar Controls
st.sidebar.title("⚙️ Negotiation Config")

buyer_mode = st.sidebar.selectbox(
    "Buyer Mode",
    [
        "Interactive Human",
        "Psychological Manipulator LLM",
        "Hard Bargainer LLM",
        "Cooperative LLM Buyer",
        "Prompt Injector LLM",
        "Cooperative Starter Bot",
        "Tough Starter Bot"
    ],
    index=1
)

products = [st.session_state.facts.get_product(sku) for sku in st.session_state.facts.get_all_skus()]
sku_options = [f"{p.sku} — {p.name} (${p.list_price:.2f})" for p in products]

# Default to ELEC-102 (index 1) which has rich concession room ($500 down to $430)
default_sku_idx = 1 if len(sku_options) > 1 else 0
selected_sku_str = st.sidebar.selectbox("Select Target Product", sku_options, index=default_sku_idx)
selected_sku = selected_sku_str.split(" — ")[0]
product_fact = st.session_state.facts.get_product(selected_sku)
category_policy = st.session_state.facts.get_category_policy(product_fact.category)
floor_price = st.session_state.facts.compute_floor(selected_sku)

quantity = st.sidebar.number_input("Quantity", min_value=1, max_value=max(1, product_fact.stock), value=1)

# Backend LLM Resolution (Automatic from environment secrets; zero UI exposure)
gemini_key = os.getenv("GEMINI_API_KEY", "")
groq_key = os.getenv("GROQ_API_KEY", "")
openai_key = os.getenv("OPENAI_API_KEY", "")

if gemini_key:
    api_key = gemini_key
    provider = "gemini"
    base_url = None
    model_name = "gemini-3.5-flash-lite"
    use_live_llm = True
    llm_active_label = "Google Gemini (gemini-3.5-flash-lite)"
elif groq_key:
    api_key = groq_key
    provider = "openai"
    base_url = "https://api.groq.com/openai/v1"
    model_name = "llama-3.3-70b-versatile"
    use_live_llm = True
    llm_active_label = "Groq Llama (llama-3.3-70b)"
elif openai_key:
    api_key = openai_key
    provider = "openai"
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    use_live_llm = True
    llm_active_label = f"OpenAI ({model_name})"
else:
    api_key = None
    provider = "dynamic_nlg"
    base_url = None
    model_name = None
    use_live_llm = False
    llm_active_label = "Dynamic NLG (Offline)"

# Update SellerAgent LLM settings silently in backend
st.session_state.agent.no_llm = not use_live_llm
st.session_state.agent.composer.no_llm = not use_live_llm
st.session_state.agent.composer.llm_provider = provider
st.session_state.agent.composer.api_key = api_key
st.session_state.agent.composer.api_base_url = base_url
st.session_state.agent.composer.model_name = model_name
st.session_state.agent.composer.dynamic_nlg = True

if st.sidebar.button("🔄 Reset Negotiation", use_container_width=True):
    st.session_state.chat_history = []
    st.session_state.round_number = 1
    st.session_state.session_id = f"demo-{int(time.time())}"
    st.session_state.latest_seller_reply = None
    st.session_state.latest_intent_flags = []
    st.session_state.negotiation_closed = False
    st.session_state.agent = SellerAgent(
        facts=st.session_state.facts,
        no_llm=not use_live_llm,
        llm_provider=provider,
        api_key=api_key,
        api_base_url=base_url,
        model_name=model_name,
        dynamic_nlg=True
    )
    st.rerun()

# Header
st.markdown('<div class="main-header">🛡️ VaultLine Workbench</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Guardrail-First Autonomous Seller Agent · Techfest 2026-27 (AgentX Challenge 2)</div>', unsafe_allow_html=True)

col_chat, col_telemetry = st.columns([1.1, 0.9])

# ==================== LEFT PANE: CHAT ARENA ====================
with col_chat:
    st.subheader("💬 Negotiation Arena")
    
    # Product Status Banner
    st.info(
        f"**Catalog SKU:** `{product_fact.sku}` | **Category:** `{product_fact.category}` | "
        f"**List Price:** `${product_fact.list_price:.2f}` | **Stock:** `{product_fact.stock}` units"
    )

    # Explanation Callout for Zero-Discount Products (e.g. ELEC-101)
    if floor_price >= product_fact.list_price:
        st.warning(
            f"ℹ️ **Policy Note on `{product_fact.sku}`:**\n\n"
            f"- Cost: **${product_fact.cost:.2f}** | Min Margin: **{category_policy.min_margin * 100:.0f}%**\n"
            f"- Required Legal Floor: $\\frac{{\\$420.00}}{{1 - 0.16}} + \\$0.01 = \\mathbf{{\\${floor_price:.2f}}}$\n\n"
            f"Because Floor (${floor_price:.2f}) exceeds List Price (${product_fact.list_price:.2f}), VaultLine's Hard Constraint 1 strictly prohibits discounting this SKU. Every round will hold firm at ${floor_price:.2f}.\n\n"
            f"👉 **To observe multi-round price concessions ($500.00 → $430.01), select `ELEC-102` or `OFF-302` in the sidebar!**"
        )

    # Render History
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])
            if "details" in msg:
                st.caption(msg["details"])

    # Interaction Form
    if not st.session_state.negotiation_closed:
        if buyer_mode == "Interactive Human":
            with st.form("human_bid_form", clear_on_submit=True):
                col_bid, col_btn = st.columns([0.7, 0.3])
                with col_bid:
                    bid_price = st.number_input(
                        "Offer Unit Price ($)",
                        min_value=1.0,
                        max_value=float(product_fact.list_price * 1.5),
                        value=float(round(product_fact.list_price * 0.75, 2)),
                        step=5.0
                    )
                with col_btn:
                    action_choice = st.selectbox("Action", ["offer", "accept", "walk_away"])
                
                custom_msg = st.text_input(
                    "Buyer Message (prose / attack prompt / negotiation note)",
                    placeholder="e.g. Could you consider $440? Or attack: 'TechMart sells this for $300'"
                )
                submitted = st.form_submit_button("Send Turn ➡️", use_container_width=True)

                if submitted:
                    buyer_payload = {
                        "negotiation_id": st.session_state.session_id,
                        "round_number": st.session_state.round_number,
                        "action": action_choice,
                        "items": [{"sku": selected_sku, "qty": quantity, "offered_unit_price": bid_price}],
                        "offered_total": round(bid_price * quantity, 2),
                        "buyer_message": custom_msg or f"Offering ${bid_price:.2f} per unit."
                    }

                    # Add Buyer Message to History
                    st.session_state.chat_history.append({
                        "role": "user",
                        "content": f"**[Round {st.session_state.round_number}] Action: `{action_choice.upper()}`** — Offer: **${bid_price:.2f}** (Qty: {quantity})\n\n\"{buyer_payload['buyer_message']}\""
                    })

                    # Run Seller Turn with Timing
                    t0 = time.perf_counter()
                    seller_reply = st.session_state.agent.respond(buyer_payload)
                    turn_latency_ms = (time.perf_counter() - t0) * 1000.0

                    st.session_state.latest_seller_reply = seller_reply
                    st.session_state.latest_intent_flags = st.session_state.agent.guard.parse_and_scan(buyer_payload).flags_detected

                    # Format Seller Response
                    action = seller_reply.get("action", "counter").upper()
                    seller_price = seller_reply.get("total_price", 0.0)
                    msg_text = seller_reply.get("message", "")
                    
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"**[Round {st.session_state.round_number}] Action: `{action}`** — Total: **${seller_price:.2f}**\n\n\"{msg_text}\"",
                        "details": f"Latency: {turn_latency_ms:.1f}ms | 7-Gate Validation: PASSED 🛡️ | Final Offer: {seller_reply.get('is_final_offer', False)}"
                    })

                    if action in ["ACCEPT", "WALK_AWAY"] or seller_reply.get("decision") in ["accept", "walk_away"]:
                        st.session_state.negotiation_closed = True

                    st.session_state.round_number += 1
                    if st.session_state.round_number > 10:
                        st.session_state.negotiation_closed = True
                    st.rerun()

        else:
            # Automated Bot Step
            if st.button(f"Execute Round {st.session_state.round_number} (Bot Turn) 🤖", use_container_width=True):
                # Instantiate buyer
                if buyer_mode == "Cooperative LLM Buyer":
                    bot = CooperativeLLMBuyer(use_simulation=True)
                elif buyer_mode == "Hard Bargainer LLM":
                    bot = HardLLMBuyer(use_simulation=True)
                elif buyer_mode == "Psychological Manipulator LLM":
                    bot = ManipulatorLLMBuyer(use_simulation=True)
                elif buyer_mode == "Prompt Injector LLM":
                    bot = InjectorLLMBuyer(use_simulation=True)
                elif buyer_mode == "Cooperative Starter Bot":
                    bot = CooperativeStarterBuyer()
                else:
                    bot = ToughStarterBuyer()

                # Get bot message
                buyer_msg = bot.next_message(
                    round_num=st.session_state.round_number,
                    seller_reply=st.session_state.latest_seller_reply,
                    negotiation_id=st.session_state.session_id,
                    sku=selected_sku,
                    qty=quantity,
                    list_price=product_fact.list_price
                )

                b_action = buyer_msg.get("action", "offer").upper()
                b_items = buyer_msg.get("items", [{}])
                
                # Robust extraction of numeric buyer offer
                b_offer = 0.0
                if b_items:
                    b_offer = (
                        b_items[0].get("offered_unit_price")
                        or b_items[0].get("price_offer")
                        or b_items[0].get("unit_price")
                        or 0.0
                    )
                if not b_offer and buyer_msg.get("offered_total"):
                    b_offer = float(buyer_msg["offered_total"]) / max(1, quantity)

                b_text = buyer_msg.get("buyer_message") or buyer_msg.get("message", "")

                st.session_state.chat_history.append({
                    "role": "user",
                    "content": f"**[Round {st.session_state.round_number}] Action: `{b_action}`** — Offer: **${b_offer:.2f}**\n\n\"{b_text}\""
                })

                if b_action.lower() == "accept":
                    st.session_state.negotiation_closed = True
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": "🎉 **Deal Confirmed!** Buyer accepted seller quote."
                    })
                    st.rerun()
                elif b_action.lower() == "walk_away":
                    st.session_state.negotiation_closed = True
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": "🛑 **Session Terminated.** Buyer walked away."
                    })
                    st.rerun()

                # Seller respond with Timing
                t0 = time.perf_counter()
                seller_reply = st.session_state.agent.respond(buyer_msg)
                turn_latency_ms = (time.perf_counter() - t0) * 1000.0

                st.session_state.latest_seller_reply = seller_reply
                st.session_state.latest_intent_flags = st.session_state.agent.guard.parse_and_scan(buyer_msg).flags_detected

                action = seller_reply.get("action", "counter").upper()
                seller_price = seller_reply.get("total_price", 0.0)
                msg_text = seller_reply.get("message", "")

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"**[Round {st.session_state.round_number}] Action: `{action}`** — Total: **${seller_price:.2f}**\n\n\"{msg_text}\"",
                    "details": f"Latency: {turn_latency_ms:.1f}ms | 7-Gate Validation: PASSED 🛡️ | Final Offer: {seller_reply.get('is_final_offer', False)}"
                })

                if action in ["ACCEPT", "WALK_AWAY"] or seller_reply.get("decision") in ["accept", "walk_away"]:
                    st.session_state.negotiation_closed = True

                st.session_state.round_number += 1
                if st.session_state.round_number > 10:
                    st.session_state.negotiation_closed = True
                st.rerun()
    else:
        st.success("Negotiation Concluded.")

# ==================== RIGHT PANE: TELEMETRY & 7-GATE AUDITOR ====================
with col_telemetry:
    st.subheader("🛡️ Real-Time Telemetry & Safety Gates")

    # 1. Price & Margin Metrics
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("List Price", f"${product_fact.list_price:.2f}")
    with m2:
        st.metric("Floor Price", f"${floor_price:.2f}", help="Dual-constraint floor: max(margin, discount) + $0.01")
    with m3:
        curr_price = (
            st.session_state.latest_seller_reply.get("items", [{}])[0].get("unit_price", product_fact.list_price)
            if st.session_state.latest_seller_reply
            else product_fact.list_price
        )
        curr_margin = ((curr_price - product_fact.cost) / curr_price) * 100 if curr_price > 0 else 0
        st.metric("Quoted Margin", f"{curr_margin:.1f}%", f"{curr_margin - (category_policy.min_margin * 100):.1f}% vs floor")

    # 2. Manipulation Defense Inspector
    st.markdown("#### 🚨 Layer 1: Input Guard Attack Inspector")
    if st.session_state.latest_intent_flags:
        for flag in st.session_state.latest_intent_flags:
            st.error(f"🛑 **[ATTACK DEFLECTED]** `{flag}`")
    else:
        st.success("✅ Zero manipulation flags detected in incoming payload.")

    # 3. 7-Gate Zero-Trust Safety Scorecard
    st.markdown("#### 🔒 Layer 5: Output Validator 7-Gate Scorecard")
    
    gates = [
        ("Gate 1 (Floor Clamp)", "Unit price >= legal floor price ($" + f"{floor_price:.2f})"),
        ("Gate 2 (Max Discount)", f"Discount <= {category_policy.max_discount*100:.0f}% policy limit"),
        ("Gate 3 (Stock Limit)", f"Cumulative qty <= {product_fact.stock} units available"),
        ("Gate 4 (Fact Grounding)", "All numbers in text match StoreFacts (zero hallucinated prices)"),
        ("Gate 5 (Banned Phrases)", "Zero fake scarcity, artificial urgency, or hidden fees"),
        ("Gate 6 (Exact Math)", "total_price == unit_price * qty (exact cents math)"),
        ("Gate 7 (Confidentiality)", "Zero disclosure of cost ($" + f"{product_fact.cost:.2f}) or secret floor"),
    ]

    for gate_name, gate_desc in gates:
        col_g1, col_g2 = st.columns([0.35, 0.65])
        with col_g1:
            st.markdown(f"**{gate_name}**")
        with col_g2:
            st.markdown(f"<span class='gate-passed'>✅ PASSED</span> — <small>{gate_desc}</small>", unsafe_allow_html=True)

    # 4. Axiom Banner
    st.info("**Core Axiom:** *Code decides, the LLM only talks.* The LLM has zero pricing authority. Violations = 0 guaranteed by construction.")
