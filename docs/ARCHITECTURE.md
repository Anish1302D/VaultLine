# VaultLine: Start-to-End System & Software Architecture
**Event:** Techfest 2026-27 (IIT Bombay) · AgentX Challenge 2 – Selling to Machines  
**Project:** VaultLine Autonomous Guardrail-First Seller Agent

> **Architectural Axiom:** *Code decides, the LLM only talks.*  
> In machine-to-machine commerce, buyer agents are adversarial optimizers: they probe for cost structures, anchor with fabricated competitor quotes, inject system-override prompts, and grind down naive chatbots over repeated turns. VaultLine eliminates LLM pricing authority entirely. A deterministic engine computes every number from an immutable policy store, and an independent zero-trust validator audits every outgoing message before it crosses the wire.

---

## Table of Contents
1. [End-to-End Architectural Topology](#1-end-to-end-architectural-topology)
2. [Trust Boundaries & Zero-Trust Data Flow](#2-trust-boundaries--zero-trust-data-flow)
3. [Five-Layer Seller Agent Architecture](#3-five-layer-seller-agent-architecture)
4. [Mathematical Models & Negotiation Mechanics](#4-mathematical-models--negotiation-mechanics)
5. [Data Contracts & Message Schemas](#5-data-contracts--message-schemas)
6. [Adversarial Buyer Ecosystem & Evaluation Architecture](#6-adversarial-buyer-ecosystem--evaluation-architecture)
7. [Production Serving, Demo & Finals Resilience Architecture](#7-production-serving-demo--finals-resilience-architecture)
8. [Requirements-to-Architecture Traceability Matrix](#8-requirements-to-architecture-traceability-matrix)

---

## 1. End-to-End Architectural Topology

The diagram below illustrates the complete start-to-end project architecture across four subsystems:
1. **External Interaction & Harness Layer** (Starter kit harness, buyer bots, Streamlit workbench, FastAPI endpoint)
2. **Five-Layer Seller Core** (`guard.py` → `facts.py` → `engine.py` → `composer.py` → `validator.py`)
3. **Immutable Single Source of Truth** (`store.csv` and `policy.json`)
4. **Verification, Experimentation & Red-Team Pipeline** (`run_batch.py`, `tune.py`, `evaluate.py`, `pytest` + `hypothesis`)

```mermaid
flowchart TB
    subgraph External["1. Interaction & Execution Surfaces"]
        BUY["Buyer Agent<br/>(Starter Bots / 4 Persona LLMs / Hidden Judges)"]
        HAR["Negotiation Harness (harness.py)<br/>Turn coordinator, max 10-round cap, transcript logger"]
        DEMO["Interactive Demo UI (demo/app.py)<br/>Live chat + real-time Policy & Guardrail Inspector"]
        API["Production API (FastAPI container)<br/>Stateless /negotiate endpoint + Redis/Memory state"]
    end

    subgraph SellerCore["2. VaultLine Seller Agent (seller/agent.py)"]
        direction TB
        L1["Layer 1: Input Guard (seller/guard.py)<br/>• Schema validation & safe defaults<br/>• 7-class manipulation & prompt-injection scanner<br/>• Untrusted prose -> typed BuyerIntent extraction"]
        L2["Layer 2: Store Facts Authority (seller/facts.py)<br/>• Read-only loader for store.csv & policy.json<br/>• Dual-constraint floor calculator (margin vs discount)<br/>• Bundle-aware stock & alternative SKU lookup"]
        L3["Layer 3: Deterministic Negotiation Engine (seller/engine.py)<br/>• Session state & buyer concession pattern detector<br/>• Boulware concession curve + reciprocity step<br/>• Volume tiers, multi-SKU bundles, round-8 final offer<br/>• Fairness by construction (tone/identity blind)"]
        L4["Layer 4: Composer (seller/composer.py)<br/>• Deterministic fact-bound templates<br/>• Optional low-temp LLM paraphraser (numbers locked)"]
        L5["Layer 5: Independent Output Validator (seller/validator.py)<br/>• 7-gate independent audit against StoreFacts<br/>• Floor, discount, stock, number set, banned phrases, math, leaks<br/>• Automatic deterministic fallback on any failure"]
    end

    subgraph TruthStore["3. Single Source of Truth (data/)"]
        CSV[("data/store.csv<br/>SKU, Category, Cost,<br/>List Price, Stock")]
        POL[("data/policy.json<br/>Category min_margin,<br/>max_discount, rules")]
    end

    subgraph LLMOpt["Optional Language Model"]
        LLM["Low-Temperature LLM<br/>(Paraphrase only — zero pricing authority)"]
    end

    subgraph Verification["4. Batch Evaluation, Tuning & Verification Suite"]
        BATCH["Batch Runner (experiments/run_batch.py)<br/>300+ runs per buyer persona"]
        TUNE["Grid Search Tuner (experiments/tune.py)<br/>Optimizes beta, target, reservation curve"]
        AUDIT["Truthfulness & Policy Auditor (evaluate.py)<br/>100% fact match & 0 violation gate"]
        TESTS["Automated Test Suite (tests/)<br/>Unit + 30+ Red-Team + Metamorphic Fairness + 10k Hypothesis"]
    end

    BUY <-->|JSON Turn Message| HAR
    DEMO <-->|Live Simulation| HAR
    BUY <-->|HTTP POST JSON| API
    HAR -->|Raw Buyer JSON| L1
    API -->|Raw Buyer JSON| L1

    L1 -->|Sanitized BuyerIntent| L3
    CSV --> L2
    POL --> L2
    L2 -->|Immutable ProductFacts & Floors| L3
    L3 -->|Strict FactObject| L4
    L4 -.->|Template Text + Locked Numbers| LLM
    LLM -.->|Paraphrased Prose| L4
    L4 -->|Draft Seller Reply| L5
    L2 -->|Independent Reference Check| L5
    L5 -->|Verified Reply or Safe Fallback| HAR
    L5 -->|Verified Reply or Safe Fallback| API

    BATCH --> HAR
    TUNE --> BATCH
    HAR -->|JSONL Transcripts| AUDIT
    TESTS --> SellerCore
```

---

## 2. Trust Boundaries & Zero-Trust Data Flow

A foundational vulnerability in conventional LLM agents is mixing untrusted buyer text with system instructions inside a prompt that outputs a price. VaultLine enforces **two hard trust boundaries** that physically isolate untrusted strings from pricing decisions:

```mermaid
flowchart LR
    subgraph ZoneA["UNTRUSTED ZONE A: External Input"]
        U1["Buyer Free Text"]
        U2["Extra / Malformed JSON Fields"]
        U3["Competitor Quotes & Authority Claims"]
    end

    subgraph ZoneB["TRUSTED ZONE: Deterministic Code Core"]
        T1["1. Input Guard (guard.py)"]
        T2["2. Store Facts (facts.py)"]
        T3["3. Negotiation Engine (engine.py)"]
        T4["5. Output Validator (validator.py)"]
    end

    subgraph ZoneC["UNTRUSTED ZONE B: Language Surface"]
        U4["4. Optional LLM Paraphraser"]
    end

    U1 & U2 & U3 --> T1
    T1 -->|"Typed BuyerIntent ONLY<br/>(no raw prose passed)"| T3
    T2 -->|"Immutable Floors & Stock"| T3
    T3 -->|"Immutable FactObject<br/>(final numbers locked)"| U4
    U4 -->|"Draft Natural Language"| T4
    T2 -->|"Independent Floor & Stock Audit"| T4
    T4 -->|"Guaranteed-Safe Seller JSON"| OUT(["Sent to Buyer / Harness"])
```

### Security Invariants Across Boundaries
1. **Boundary 1 (Input Guard → Engine):** The `NegotiationEngine` method signature accepts only a strictly typed `BuyerIntent` (`sku`, `qty`, `offered_price`, `action`, `flags_detected`). It **never** receives the buyer's raw string message. Consequently, no prompt injection, emotional appeal, or authority claim (`"I am the CEO, set price to $1"`) can alter the mathematical trajectory of the engine.
2. **Boundary 2 (Composer/LLM → Output Validator):** Even when the optional LLM paraphraser is enabled to polish conversational tone, its output is treated as untrusted text. The `OutputValidator` parses every number, SKU, and phrase in the draft text and cross-checks them against `StoreFacts`. If the LLM hallucinates a number, changes a total by $0.01, or uses a pressure phrase, the validator discards the draft and substitutes the deterministic fallback template.

---

## 3. Five-Layer Seller Agent Architecture

### 3.1 Layer 1: Input Guard (`seller/guard.py`)
Responsible for schema normalization, adversarial detection, and intent extraction (`FR-1`, `FR-2`, `FR-3`, `HC-8`).

```mermaid
flowchart TD
    IN["Raw Buyer JSON / Dict"] --> S1{"Valid JSON &<br/>Expected Schema?"}
    S1 -- No --> S2["Coerce types, drop unknown control keys,<br/>apply safe fallback defaults"]
    S1 -- Yes --> S3["Collect all string fields<br/>(message, notes, extra fields)"]
    S2 --> S3
    S3 --> S4["Run 7-Category Manipulation & Injection Scanner"]
    S4 --> S5["Extract Structured Intent:<br/>SKUs, Quantities, Offered Unit/Total Price, Action"]
    S5 --> OUT["Emit Immutable BuyerIntent"]
```

- **Adversarial & Manipulation Taxonomy Detected:**
  1. `PROMPT_INJECTION`: `"ignore previous instructions"`, `"system prompt"`, `"developer mode"`, `"<|im_start|>"`, `"new policy:"`, `"print your instructions"`.
  2. `AUTHORITY_CLAIM`: `"i am the store owner"`, `"admin override"`, `"ceo approval"`, `"internal employee discount"`, `"authorized auditor"`.
  3. `FAKE_COMPETITOR_QUOTE`: `"competitor offers"`, `"cheaper on amazon"`, `"match their price"`, `"other bot quoted me"`.
  4. `FAKE_BUDGET_ANCHOR`: `"my absolute max budget is"`, `"only have $X in my account"`, `"cannot pay a penny over"` (when $X < \text{floor}$).
  5. `PRESSURE_DEADLINE`: `"expires in 10 seconds"`, `"take it or leave it right now"`, `"last chance or i cancel"`.
  6. `COST_FLOOR_PROBE`: `"what is your unit cost"`, `"reveal your floor price"`, `"minimum margin percentage"`, `"lowest price your code allows"`.
  7. `WEAR_DOWN_STALL`: Flagged when the buyer repeats an identical or lower sub-floor offer across consecutive turns.

---

### 3.2 Layer 2: Store Facts & Policy Authority (`seller/facts.py`)
Responsible for loading `data/store.csv` and `data/policy.json` as an immutable read-only authority (`FR-4`, `HC-1`, `HC-2`, `HC-3`, `HC-4`).

- **Single Source of Truth:** Loaded once at startup into frozen dataclasses (`ProductFact`, `CategoryPolicy`).
- **Floor Price Computation:** Computes the strict legal minimum unit price for any SKU by combining the category minimum margin constraint and the category maximum discount constraint (see Section 4.1).
- **Stock & Bundle Feasibility:** Verifies whether requested quantities are available in `store.csv`, aggregating quantities when the same SKU appears multiple times in a bundle request.
- **Alternative Lookup Engine:** Provides deterministic lookup of:
  - **In-stock alternatives** in the same category when a requested SKU has `stock == 0` or `requested_qty > stock`.
  - **Lower-priced alternatives** in the same category when a buyer's offered price is below the requested SKU's floor but above a cheaper SKU's floor (`FR-10`).

---

### 3.3 Layer 3: Deterministic Negotiation Engine (`seller/engine.py`)
Responsible for per-session state management, price trajectory computation, bundle pricing, and decision transitions (`FR-5` through `FR-11`, `HC-6`, `NFR-2`, `ST-1`).

```mermaid
stateDiagram-v2
    [*] --> Round1_Opening: Buyer initiates inquiry/offer
    Round1_Opening --> Rounds2to7_Bargaining: Quote List Price (or Accept if offer >= List)
    Rounds2to7_Bargaining --> Rounds2to7_Bargaining: Counter via Boulware Curve + Reciprocity + Tiers
    Rounds2to7_Bargaining --> DealAccepted: Buyer Offer >= Round Reservation Price (>= Floor)
    Rounds2to7_Bargaining --> OutOfStock_Alternative: Stock == 0 or Qty > Stock
    OutOfStock_Alternative --> Rounds2to7_Bargaining: Buyer switches to alternative SKU
    Rounds2to7_Bargaining --> Round8_FinalOffer: Round reaches 8 without agreement
    Round8_FinalOffer --> DealAccepted: Buyer accepts Final Offer (Rounds 8-10)
    Round8_FinalOffer --> PoliteWalkAway: Buyer rejects Final Offer or Round > 10
    DealAccepted --> [*]
    PoliteWalkAway --> [*]
```

- **Buyer Pattern Classification:** Classifies the counterpart dynamically from offer history into:
  - `COOPERATIVE`: Meaningful upward concessions each turn ($\Delta \text{offer} > 0$).
  - `HARD_BARGAINER`: Small increments near a fixed threshold.
  - `STALLING / WEAR_DOWN`: Zero or negative concession across $\ge 2$ consecutive turns (`offer[t] <= offer[t-1]`).
- **Decision Precedence per Turn:**
  1. **Round Limit Check (`HC-6`):** If `round > 10`, immediately emit `WALK_AWAY`.
  2. **Inventory Check (`HC-3`, `FR-10`):** If any requested item is out of stock or exceeds available stock, do not quote a price for the unavailable quantity; offer the available stock cap or an in-stock category alternative.
  3. **Acceptance Check:** If the buyer's offered price meets or exceeds the round's reservation price (which is always $\ge \text{floor}$), emit `ACCEPT` at the buyer's offered price (or the seller's previous counteroffer if the buyer sent an explicit `accept` action).
  4. **Round 8+ Endgame (`FR-11`):** At Round 8, issue an explicit `FINAL_OFFER` at the seller's reservation floor buffer. In Rounds 9–10, accept only if the buyer meets that final offer; otherwise emit a polite `WALK_AWAY`.
  5. **Rounds 1–7 Counteroffer (`FR-5..FR-9`):** Compute the counteroffer using the Boulware concession curve, reciprocity adjustment, volume tiers, and bundle rules, strictly clamped to $\ge \text{floor}$ for every line item.

---

### 3.4 Layer 4: Composer (`seller/composer.py`)
Responsible for rendering the engine's `FactObject` into a structured reply dictionary and clear natural-language explanation (`FR-12`, `FR-13`, `FR-16`).

- **Fact-Bound Templates:** Every sentence fragment is parameterized strictly by fields in `FactObject`:
  - Manipulation rebuttal preamble (e.g., if `FAKE_COMPETITOR_QUOTE` is flagged: *"Our pricing follows official store policy rather than external third-party quotes."*).
  - Line-item breakdown stating exact `sku`, `name`, `qty`, `list_price`, `unit_price`, `line_total`, and `available_stock`.
  - Bundle/volume tier notice if applicable.
  - Alternative product recommendation if the primary item is out of stock or above the buyer's budget.
  - Explicit final offer notice when `round >= 8`.
- **Optional Low-Temperature LLM Paraphraser:**
  - Enabled only when `USE_LLM_PARAPHRASE=true` and an API key is present; otherwise runs in deterministic `no_llm` mode (`< 5 ms` per turn).
  - Prompt instructs the LLM to rephrase the template concisely without adding claims or altering any numeric values.

---

### 3.5 Layer 5: Independent Output Validator (`seller/validator.py`)
The final zero-trust gate before any response leaves the seller (`FR-14`, `HC-1..HC-7`).

```mermaid
flowchart TD
    IN["Draft Seller Response + FactObject"] --> G1{"Gate 1: Floor Check<br/>Every unit_price >= floor(sku)?"}
    G1 -- Pass --> G2{"Gate 2: Discount Check<br/>Discount <= max_discount(cat)?"}
    G2 -- Pass --> G3{"Gate 3: Stock Check<br/>stock > 0 and cumulative qty <= stock?"}
    G3 -- Pass --> G4{"Gate 4: Fact-Set Number Audit<br/>Every number in text exists in allowed FactObject set?"}
    G4 -- Pass --> G5{"Gate 5: Banned Phrase Scan<br/>Zero fake scarcity, pressure, or hidden fees?"}
    G5 -- Pass --> G6{"Gate 6: Exact Arithmetic<br/>line_total == unit_price * qty<br/>and total == sum(line_totals)?"}
    G6 -- Pass --> G7{"Gate 7: Confidentiality Check<br/>No unit cost or secret floor leaked?"}
    G7 -- Pass --> PASS(["VALIDATED: Send JSON Reply"])

    G1 -- Fail --> FB["INTERCEPT: Log violation reason &<br/>Replace with Deterministic Safe Fallback Template"]
    G2 -- Fail --> FB
    G3 -- Fail --> FB
    G4 -- Fail --> FB
    G5 -- Fail --> FB
    G6 -- Fail --> FB
    G7 -- Fail --> FB
    FB --> PASS
```

---

## 4. Mathematical Models & Negotiation Mechanics

### 4.1 Dual-Constraint Floor Calculation
For each product $p$ in category $c$, let:
- $C_p$ = unit cost from `store.csv`
- $L_p$ = unit list price from `store.csv`
- $m_c$ = category minimum margin from `policy.json`
- $d_c$ = category maximum discount from `policy.json`

Depending on the starter kit's margin definition in `evaluate.py` (**VERIFY on Day 1**), the margin floor is:
$$\text{floor}_{\text{margin}}(p) = \begin{cases} \dfrac{C_p}{1 - m_c} & \text{if margin-on-price } \left(\dfrac{P - C_p}{P} \ge m_c\right) \\[10pt] C_p \times (1 + m_c) & \text{if markup-on-cost } \left(\dfrac{P - C_p}{C_p} \ge m_c\right) \end{cases}$$

*(Note: For any $0 < m_c < 1$, $\frac{C_p}{1 - m_c} > C_p(1 + m_c)$, so margin-on-price is strictly higher and safe under both definitions.)*

The discount floor is:
$$\text{floor}_{\text{discount}}(p) = L_p \times (1 - d_c)$$

Combining both constraints with upward ceiling rounding and safety buffer $\epsilon$:
$$\text{Floor}(p) = \text{ceil}_{\text{unit}}\!\left(\max\left(\text{floor}_{\text{margin}}(p),\ \text{floor}_{\text{discount}}(p)\right)\right) + \epsilon$$

### 4.2 Boulware Concession Curve & Target Price
Let the negotiable range be $\Delta_p = L_p - \text{Floor}(p)$. We set a target price $T_p$ comfortably above the floor using target retention ratio $\gamma \in [0.15, 0.35]$:
$$T_p = \text{Floor}(p) + \gamma \cdot \Delta_p$$

At round $t \in \{1, \dots, R_{\text{final}}\}$ (where $R_{\text{final}} = 8$), the base Boulware curve price with convexity exponent $\beta > 1$ (default $\beta = 1.8$) is:
$$P_{\text{curve}}(p, t) = L_p - (L_p - T_p) \times \left(\frac{t - 1}{R_{\text{final}} - 1}\right)^\beta$$

- At $t = 1$: $P_{\text{curve}}(p, 1) = L_p$ (opens at list price).
- At $t = 2 \dots 4$: Because $\beta > 1$, $\left(\frac{t-1}{7}\right)^\beta$ grows slowly, preserving high margin against early-agreeing buyers.
- At $t = 5 \dots 7$: Concession accelerates toward $T_p$ to prevent deadlock against patient buyers.

### 4.3 Reciprocity, Stall Penalty & Reservation Price
- **Reciprocity Adjustment:** If the buyer increased their offer by $\Delta B_t = B_t - B_{t-1} > 0$, the seller grants a reciprocal discount $\rho \cdot \min(\Delta B_t, 0.15 \Delta_p)$ (with $\rho \approx 0.20$), bounded below by $T_p$.
- **Stall / Wear-Down Freeze:** If $B_t \le B_{t-1}$ and $B_t < \text{Floor}(p)$, the buyer is stalling. The seller sets $P(p, t) = P(p, t-1)$ (zero unilateral concession).
- **Round-Dependent Reservation Price $R(p, t)$:** The threshold at which the seller immediately `ACCEPT`s a buyer's offer $B_t$:
  $$R(p, t) = \max\left(\text{Floor}(p),\ P_{\text{curve}}(p, t) - \alpha_t \cdot \Delta_p\right)$$
  By Rounds 8–10, $R(p, t)$ converges to $\text{Floor}(p) + \delta_{\text{min}}$ (a tiny positive margin buffer above the hard floor) so any profitable deal closes before Round 10 expires.

### 4.4 Quantity Tiers & Multi-Item Bundle Clamping
For a bundle of items $\{(p_1, q_1), \dots, (p_k, q_k)\}$:
1. Compute each line item's volume tier discount $\tau(q_i)$ and multi-item bundle discount $\delta_{\text{bundle}}$.
2. Clamp **every single line item independently** against its product floor:
   $$P_{\text{final}}(p_i, q_i, t) = \max\left(\text{Floor}(p_i),\ \text{round}\!\left(P(p_i, t) \times (1 - \tau(q_i) - \delta_{\text{bundle}}),\ 2\right)\right)$$
3. Compute exact line and bundle totals:
   $$\text{LineTotal}_i = P_{\text{final}}(p_i, q_i, t) \times q_i, \qquad \text{Total} = \sum_{i=1}^k \text{LineTotal}_i$$
This guarantees that a discount on one high-margin item can never subsidize a below-floor price on a low-margin item (`FR-9`, `HC-1`).

### 4.5 Fairness by Construction (`ST-1`)
The engine's pricing function has the exact mathematical signature:
$$f_{\text{engine}}(\text{sku}, \text{qty}, t, \langle B_1, \dots, B_t \rangle, \text{StoreFacts}) \longrightarrow \text{FactObject}$$
Because buyer persona attributes, politeness markers, demographic tokens, urgency claims, and message lengths are stripped at Layer 1 (`InputGuard`), two buyers who make the exact same sequence of numerical offers $\langle B_1, \dots, B_t \rangle$ for $(\text{sku}, \text{qty})$ are **mathematically guaranteed** to receive identical prices down to the cent.

---

## 5. Data Contracts & Message Schemas

### 5.1 Store Inventory (`data/store.csv`)
| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `sku` | `str` | Primary Key, non-empty | Unique product identifier |
| `name` | `str` | Non-empty | Human-readable product name |
| `category` | `str` | Foreign Key → `policy.json` | Product category governing margin & discount rules |
| `cost` | `float` | $> 0$ | Confidential unit acquisition cost (never disclosed) |
| `list_price` | `float` | $> \text{cost}$ | Published catalog retail price |
| `stock` | `int` | $\ge 0$ | Current available inventory units |

### 5.2 Policy Configuration (`data/policy.json`)
```json
{
  "max_rounds": 10,
  "final_offer_round": 8,
  "margin_mode": "margin_on_price",
  "floor_epsilon": 0.01,
  "categories": {
    "Electronics": { "min_margin": 0.16, "max_discount": 0.14 },
    "Home_Appliances": { "min_margin": 0.22, "max_discount": 0.20 }
  },
  "qty_tiers": [
    { "min_qty": 3, "tier_discount_pct": 0.02 },
    { "min_qty": 5, "tier_discount_pct": 0.04 }
  ],
  "banned_phrases": ["only 1 left", "going fast", "hidden fee", "act now or lose"]
}
```

### 5.3 Internal `BuyerIntent` Contract (`guard.py` → `engine.py`)
```python
@dataclass(frozen=True)
class RequestedItem:
    sku: str
    qty: int
    offered_unit_price: Optional[float]

@dataclass(frozen=True)
class BuyerIntent:
    negotiation_id: str
    round_number: int
    action: Literal["offer", "accept", "reject", "inquiry", "walk_away"]
    items: Tuple[RequestedItem, ...]
    offered_total: Optional[float]
    flags_detected: Tuple[str, ...]
    schema_valid: bool
```

### 5.4 Internal `FactObject` Contract (`engine.py` → `composer.py` & `validator.py`)
```python
@dataclass(frozen=True)
class LineItemFact:
    sku: str
    name: str
    category: str
    qty: int
    list_price: float
    unit_price: float
    line_total: float
    available_stock: int
    in_stock: bool

@dataclass(frozen=True)
class FactObject:
    negotiation_id: str
    round_number: int
    decision: Literal["accept", "counter", "final_offer", "walk_away", "out_of_stock"]
    is_final_offer: bool
    items: Tuple[LineItemFact, ...]
    total_price: float
    alternatives: Tuple[AlternativeFact, ...]
    flags_detected: Tuple[str, ...]
    buyer_pattern: str
```

### 5.5 Agent Capability Declaration (`AGENT_CARD.json` — `ST-2`)
Machine-readable manifest declaring the seller agent's protocol version, supported actions, negotiable parameters (unit price within policy bounds, volume tiers, multi-SKU bundles, in-stock alternatives), and non-negotiable invariants (minimum category margin, maximum category discount, real-time stock limits, zero hidden fees, 10-round cap).

---

## 6. Adversarial Buyer Ecosystem & Evaluation Architecture

To prevent overfitting to the starter kit's 3 rule-based bots, VaultLine includes a full benchmarking and red-teaming architecture (`buyers/`, `experiments/`, `tests/`):

```mermaid
flowchart LR
    subgraph Personas["7 Distinct Buyer Counterparts"]
        B1["Starter Bot 1: Cooperative Rule Bot"]
        B2["Starter Bot 2: Linear Concession Bot"]
        B3["Starter Bot 3: Tough Threshold Bot"]
        L1["LLM Buyer 1: Cooperative Value Seeker<br/>(Reasonable concessions, bundle-friendly)"]
        L2["LLM Buyer 2: Hard Bargainer<br/>(Anchors below floor, stalls until round 8-9)"]
        L3["LLM Buyer 3: Manipulator<br/>(Fake competitor quotes, fake low budget, urgency pressure)"]
        L4["LLM Buyer 4: Prompt Injector & Probe<br/>(System overrides, CEO authority claims, cost/floor probes)"]
    end

    subgraph Batch["Batch & Tuning Engine"]
        RUN["run_batch.py<br/>≥ 300 negotiations per buyer type<br/>(2,100+ total runs, multi-seed)"]
        GRID["tune.py<br/>Grid search over (beta, gamma, rho)<br/>Maximizes Deal_Rate x Margin_Kept<br/>Subject to Violations == 0"]
    end

    subgraph AuditGates["Automated Quality Gates"]
        A1["Policy Violation Auditor<br/>Target: 0 / 2,100+ runs"]
        A2["Truthfulness Auditor<br/>Target: 100.0% match vs store.csv"]
        A3["Hypothesis Property Suite<br/>10,000+ randomized offer sequences"]
        A4["Metamorphic Fairness Suite<br/>Polite vs Rude vs Executive pairs -> identical prices"]
    end

    Personas --> RUN
    GRID --> RUN
    RUN --> A1 & A2
    A3 & A4 --> A1
```

### Provider Separation Principle
When running LLM buyers (`L1..L4`), the buyer bots use a different model family/provider or isolated persona prompt from the seller's optional paraphraser so the benchmark reflects genuine cross-agent generalization rather than homogeneous self-play.

---

## 7. Production Serving, Demo & Finals Resilience Architecture

### 7.1 Interactive Streamlit Workbench (`demo/app.py` — `ST-3`)
Split into two synchronized panels for the 3-minute demo video and live finals Q&A:
- **Left Panel (Live Negotiation Arena):** Turn-by-turn chat between the buyer (either an automated persona bot or live judge manual input) and the VaultLine seller, showing round indicator ($1 \dots 10$), action badges (`COUNTER`, `FINAL_OFFER`, `ACCEPT`, `WALK_AWAY`), and bundle breakdown.
- **Right Panel (Internal Guardrail & Policy Telemetry):**
  - Live product card from `store.csv` (`list_price`, `stock`, and the confidential computed `floor_price`).
  - Live Concession Curve Chart plotting `List Price`, `Seller Counter`, `Buyer Offer`, and the red `Policy Floor Line` across rounds $1 \dots 10$.
  - **7-Gate Validator Scorecard:** Visual green checkmarks for all 7 output validator gates plus active alerts whenever `InputGuard` blocks a prompt injection or fake competitor quote.

### 7.2 Containerized FastAPI Production Story (`ST-4`)
- Exposes `POST /v1/negotiate` accepting the standard buyer turn JSON and returning the validated seller JSON in `< 5 ms` (deterministic mode) or `< 1.5 s` (LLM paraphrase mode).
- Policy hot-reload: Updating `policy.json` takes effect immediately on the next turn without retraining or prompt engineering because floors are computed dynamically in `facts.py`.

### 7.3 Finals Venue Wi-Fi Backup Strategy
- The entire seller pipeline supports `VAULTLINE_NO_LLM=1` (default), running 100% locally with zero external network calls, `< 5 ms` turn latency, and identical mathematical pricing behavior inside a pre-built Docker image.

---

## 8. Requirements-to-Architecture Traceability Matrix

| Req ID | Requirement Summary | Owning Architectural Layer / Module | Verification Mechanism |
|--------|---------------------|-------------------------------------|------------------------|
| **HC-1** | Zero below-margin deals | `seller/facts.py`, `seller/engine.py`, `seller/validator.py` (Gate 1) | `tests/test_floor.py`, `tests/test_properties.py` (10k cases), CI Gate |
| **HC-2** | Zero above-max-discount deals | `seller/facts.py`, `seller/validator.py` (Gate 2) | `tests/test_floor.py`, `tests/test_validator.py` |
| **HC-3** | Zero out-of-stock offers; bundle stock tracked | `seller/facts.py`, `seller/engine.py`, `seller/validator.py` (Gate 3) | `tests/test_validator.py`, `tests/test_properties.py` |
| **HC-4** | Zero false claims (100% match to `store.csv`) | `seller/composer.py`, `seller/validator.py` (Gate 4) | Truthfulness Auditor in `evaluate.py` |
| **HC-5** | No hidden fees, fake scarcity, or math errors | `seller/validator.py` (Gates 5 & 6) | `tests/test_validator.py`, batch audit |
| **HC-6** | Never exceed 10 rounds | `seller/engine.py`, `harness.py` | Engine state tests & batch transcript audit |
| **HC-7** | Never reveal cost or exact floor price | `seller/guard.py`, `seller/validator.py` (Gate 7) | Red-team cost probe tests in `tests/test_guard.py` |
| **HC-8** | Buyer text never alters pricing authority | Trust Boundary 1 (`seller/guard.py` → `seller/engine.py`) | 30+ injection & manipulation tests in `tests/test_guard.py` |
| **FR-1..3** | Schema validation, injection flags, intent extraction | Layer 1 (`seller/guard.py`) | `tests/test_guard.py` |
| **FR-4** | Load store/policy; compute floors & stock | Layer 2 (`seller/facts.py`) | `tests/test_floor.py` |
| **FR-5..11** | Opening, curve, reservation, reciprocity, bundles, alternatives, R8 final offer | Layer 3 (`seller/engine.py`) | `tests/test_properties.py`, batch evaluation |
| **FR-12..13** | Fact-bound templates + optional re-validated LLM | Layer 4 (`seller/composer.py`) | `tests/test_validator.py` |
| **FR-14** | Independent 7-gate output validator & fallback | Layer 5 (`seller/validator.py`) | `tests/test_validator.py` |
| **FR-15..16** | Harness-compatible entry point + no-LLM mode | Facade (`seller/agent.py`) | Smoke tests & Docker offline check |
| **ST-1** | Fairness by construction (tone/identity blind) | `BuyerIntent` signature + `seller/engine.py` | `tests/test_fairness.py` (metamorphic paired tests) |
| **ST-2** | Machine-readable capability manifest | `AGENT_CARD.json` | Schema validation test |
| **ST-3** | Live interactive demo with policy inspector | `demo/app.py` (Streamlit) | Manual & demo video walkthrough |
| **ST-4** | Containerized FastAPI endpoint | `Dockerfile`, FastAPI service | Container health & latency check |
