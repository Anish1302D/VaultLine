# VaultLine: Executive Architecture Note
**Techfest 2026-27 (IIT Bombay) · AgentX Challenge 2 – "Selling to Machines"**  
*Team:* Member A (Engine & Lead) · Member B (Safety & Validation) · Member C (Buyers & Benchmarks)  
*Core Axiom:* **"Code decides, the LLM only talks."** The LLM has zero pricing authority.

---

### 1. Architectural System Blueprint (5-Layer Pipeline)

VaultLine enforces an inside-out defense-in-depth model where autonomous concessions and legal floor constraints are computed deterministically. The natural language layer is strictly decoupled from commercial authority:

```
[ Incoming Untrusted Buyer Message ]
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│ Layer 1: Input Guard (seller/guard.py)                 │
│ • Schema sanitization, type coercion & clamp negative  │
│ • 7-Class Adversarial Detector (Jailbreak, Spoof, etc) │
│ • Emits clean, prose-free BuyerIntent                  │
└────────────────────────┬───────────────────────────────┘
                         │ Trust Boundary 1 (Zero Buyer Prose)
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2: StoreFacts Authority (seller/facts.py)        │
│ • Immutable catalog store.csv & policy.json            │
│ • Dual-constraint Floor Calculator:                   │
│   Floor(p) = ceil(max(C/(1-m), L*(1-d))*100)/100 + 0.01│
│ • Bundle stock deduplication & alternative search      │
└────────────────────────┬───────────────────────────────┘
                         │ Verified Product Facts & Floors
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3: Deterministic Negotiation Engine (engine.py)  │
│ • Per-session state machine tracking rounds 1..10      │
│ • Convex Boulware Concession (beta=1.2, gamma=0.15)    │
│ • Stall freeze detector & late-round reservation       │
│ • Volume tiers (>=3, 5, 10) & independent line clamps │
└────────────────────────┬───────────────────────────────┘
                         │ FactObject (Approved Prices & Actions)
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 4: Fact-Bound Composer (seller/composer.py)      │
│ • Wire JSON serialization & policy-grounded deflections│
│ • Optional low-temp LLM paraphraser (temperature=0.1)  │
│ • Offline sub-10ms deterministic execution default     │
└────────────────────────┬───────────────────────────────┘
                         │ Draft Response
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 5: Output Validator Gatekeeper (validator.py)    │
│ • 7 Mandatory Pre-Wire Gates:                          │
│   G1: Floor | G2: Discount | G3: Stock | G4: Fact Nums │
│   G5: Banned Phrases | G6: Exact Math | G7: Cost Leak  │
│ • Intercepts ANY violation -> Deterministic Fallback   │
└────────────────────────┬───────────────────────────────┘
                         │ Trust Boundary 2 (Pre-Wire Gate)
                         ▼
[ Verified Safe Wire Response (Zero Violations Guaranteed) ]
```

---

### 2. Dual Trust Boundaries & Mathematical Invariants

1. **Trust Boundary 1 (Input Isolation):** Raw buyer text is stripped at Layer 1. The Negotiation Engine receives only structured numerical signals (`sku`, `quantity`, `price_offer`, `round_number`). Social engineering, CEO impersonation, and prompt injections are rendered mathematically incapable of shifting concession curves.
2. **Trust Boundary 2 (Pre-Wire Interception):** Layer 5 re-computes all policies independently from `StoreFacts`. If an upstream model hallucinated a price, included a hidden fee, or breached category discounts, the payload is destroyed and replaced with a deterministic fallback.
3. **Floor Price Guarantee:** To eliminate floating-point precision underflow, the floor is computed with upward ceiling rounding and an epsilon buffer:
   $$\text{Floor}(p) = \frac{\lceil \max\left(\frac{C_p}{1 - m_c},\ L_p(1 - d_c)\right) \times 100 \rceil}{100} + 0.01$$
4. **No Cross-Subsidies in Bundles:** Multi-item bundles receive volume discounts, but every SKU is clamped independently to its individual legal floor. High-margin items never subsidize low-margin items.

---

### 3. Empirical Results Across 2,100 Negotiations (300 Runs/Persona)

Evaluated across 3 starter rule bots and 4 adversarial LLM personas (Seed 42, 10 rounds max):

| Buyer Persona | Strategy / Attack Vector | Runs | Deals Closed | Deal Rate % | Avg Margin Kept % | Avg Rounds | Policy Violations |
|---|---|---|---|---|---|---|---|
| `cooperative_starter` | Predictable upward concessions | 300 | 275 | 91.7% | 33.17% | 6.1 | **0** |
| `linear_starter` | Fixed linear price increment | 300 | 225 | 75.0% | 32.58% | 7.7 | **0** |
| `tough_starter` | Holds below-floor price | 300 | 50 | 16.7% | 35.21% | 8.8 | **0** |
| `cooperative_llm` | Value-seeking natural language | 300 | 275 | 91.7% | 34.43% | 5.2 | **0** |
| `hard_llm` | Aggressive low-balling & holdout | 300 | 197 | 65.7% | 29.87% | 9.0 | **0** |
| `manipulator_llm` | Fake competitor quotes & fake budgets | 300 | 253 | 84.3% | 32.74% | 7.3 | **0** |
| `injector_llm` | Jailbreaks, authority claims & cost probes | 300 | 253 | 84.3% | 32.03% | 7.4 | **0** |
| **Overall Benchmark** | **Comprehensive Evaluation** | **2,100** | **1,528** | **72.8%** | **32.87%** | **7.3** | **0 (Zero)** |

- **Total Net Profit Generated:** **$256,221.27**
- **Metamorphic Fairness (ST-1):** 100% cent-for-cent identical quotes regardless of buyer tone or status claims.
- **Production Efficiency:** `< 10ms` latency per turn in offline mode; zero API tokens required for commercial safety.
