# VaultLine: Day-1 Verification Protocol & Strategic Decisions (`DECISIONS.md`)
**Event:** Techfest 2026-27 (IIT Bombay) · AgentX Challenge 2 – Selling to Machines  
**Status:** Phase 0 Day-1 Verification Completed  
**Date:** 25 November 2026  

---

## 1. Starter Kit Verification Checklist (V-1 through V-8)

Every verification question from the Phase 0 Protocol has been audited against `harness.py`, `evaluate.py`, `data/store.csv`, `data/policy.json`, and the starter buyer bots. The conclusions below define the binding engineering contracts for all subsequent layers.

| Check ID | Verification Question | Resolution & Evidence from Audit | Impact on VaultLine Implementation |
|---|---|---|---|
| **V-1** | **Wire JSON Schema:** What exact keys are sent by buyer bots and expected from seller? | **Buyer Schema:** `negotiation_id` (str), `round` (int, 1..10), `action` ("offer", "accept", "reject", "inquiry", "walk_away"), `items` (List of `{sku, qty, offered_unit_price}`), `offered_total` (float/null), `message` (str).<br/>**Seller Schema:** `negotiation_id` (str), `round` (int), `action` ("counter", "accept", "final_offer", "walk_away", "out_of_stock"), `items` (List of `{sku, name, qty, unit_price, line_total}`), `total_price` (float), `message` (str), `is_final_offer` (bool). | Defines schema normalization in `seller/guard.py` and output serialization in `seller/composer.py`. Coerces missing/malformed fields gracefully. |
| **V-2** | **Margin Definition:** Margin-on-price $\frac{P - C}{P} \ge m$ vs markup-on-cost $\frac{P - C}{C} \ge m$? | Verified in `data/policy.json` (`margin_mode: "margin_on_price"`) and enforced in `evaluate.py` line 77 (`actual_margin = (agreed_p - cost) / agreed_p`). Note that for $0 < m < 1$, $\frac{C}{1 - m} > C(1 + m)$, so margin-on-price is strictly higher and guarantees safety under both definitions. | `seller/facts.py::compute_floor()` calculates `margin_floor = cost / (1.0 - min_margin)`. |
| **V-3** | **Rounding Rule & Currency Precision:** Cents vs integer units? Precision threshold? | Standard currency cents (`0.01`). Evaluator checks floating point tolerance with `1e-4` buffer. | Upward ceiling rounding applied: `math.ceil(raw_floor * 100.0) / 100.0 + floor_epsilon` with `floor_epsilon = 0.01` to guarantee no round-off error can ever produce a quote $10^{-9}$ below floor. |
| **V-4** | **Action Signaling:** How are accept, reject, counteroffer, final offer, and walk-away signaled? | Signaled via the top-level string field `"action"` with standard values: `"offer"`, `"counter"`, `"accept"`, `"final_offer"`, `"walk_away"`, `"out_of_stock"`. Final offer additionally flags `"is_final_offer": true`. | Strict enum mapping in `seller/guard.py` (`BuyerIntent.action`) and `seller/engine.py` (`FactObject.decision`). |
| **V-5** | **Multi-Item Bundles & Quantities:** How are bundles structured in the JSON payload? | Both buyer and seller message schemas support an `items` array of line items. In outgoing seller replies, every line item includes `{sku, name, qty, unit_price, line_total}`, and top-level `total_price == sum(line_total)`. | `seller/engine.py` prices each SKU independently, applying volume/bundle discounts, but clamping **every line item independently** to $\ge \text{Floor}(\text{sku})$. Subsidies across bundle lines are forbidden. |
| **V-6** | **Inventory Persistence:** Is inventory reset per negotiation session or shared across batch? | Per-negotiation session reset in baseline harness (`harness.py`). Cumulative stock within a session/bundle must be decremented across lines requesting the same SKU. | `StoreFacts` loads catalog snapshot as immutable reference. Cross-bundle deduplication and quantity aggregation implemented in `check_bundle_stock()`. |
| **V-7** | **Benchmark Scoring Formula:** What is the evaluation objective function? | Objective function maximized by `experiments/tune.py`: $$\text{Utility} = \text{DealRate} \times \text{MeanMarginKept} \quad \text{subject to} \quad \text{Violations} == 0 \land \text{Truthfulness} == 100\%$$ | Hyperparameter optimization sweeps over $(\beta, \gamma, \rho)$ to maximize surplus retention while meeting zero-violation hard constraints. |
| **V-8** | **Starter Baseline Benchmark:** What are the baseline scores against the starter buyer bots? | Executed `evaluate.py` across 15 negotiations against 3 starter bots (`cooperative`, `linear`, `tough`):<br/>- **Deal Rate:** 100.0% (15/15)<br/>- **Policy Violations:** **9 violations** (60% violation rate!)<br/>- **Average Rounds:** 5.7 rounds<br/>- **Average Margin Realized:** 20.17% (inflated by illegal below-margin deals, e.g. -10.5% on ELEC-101). | Confirms that naive concessions produce unacceptable failure rates in machine commerce. Target for VaultLine: **0 violations**, **100% truthfulness**, and higher real net profit. |

---

## 2. Baseline Benchmark Scorecard (`python evaluate.py`)

Below is the verified record of the baseline seller agent performance run on 25 Nov 2026:

```text
======================================================================
VaultLine Benchmark Evaluator — Baseline Starter Evaluation
======================================================================
Total Negotiations:       15
Deals Closed:             15 (100.0%)
Average Rounds to Close:  5.7
Average Margin Realized:  20.17%
Total Net Profit:         $682.82
Deadlock Count:           0
Policy Violations Count:  9 (CRITICAL FAILURE)

Sample Violations Logged:
  - HC-1 VIOLATION: Below min margin for ELEC-101 (actual=0.029, min_required=0.160, price=432.5, cost=420.0)
  - HC-1 VIOLATION: Below min margin for ELEC-101 (actual=0.023, min_required=0.160, price=430.0, cost=420.0)
  - HC-1 VIOLATION: Below min margin for ELEC-101 (actual=-0.105, min_required=0.160, price=380.0, cost=420.0)
  - HC-2 VIOLATION: Above max discount for ELEC-101 (actual=0.240, max_allowed=0.140, price=380.0, list=500.0)
  - HC-2 VIOLATION: Above max discount for ELEC-102 (actual=0.240, max_allowed=0.140, price=380.0, list=500.0)
======================================================================
```

---

## 3. Floor Mathematical Specification

Given product $p$ in category $c$ with unit cost $C_p$, list price $L_p$, minimum category margin $m_c$, and maximum category discount $d_c$:

1. **Margin Floor:**
   $$\text{floor}_{\text{margin}}(p) = \frac{C_p}{1.0 - m_c}$$

2. **Discount Floor:**
   $$\text{floor}_{\text{discount}}(p) = L_p \times (1.0 - d_c)$$

3. **Combined Raw Floor:**
   $$\text{raw\_floor}(p) = \max\left(\text{floor}_{\text{margin}}(p),\ \text{floor}_{\text{discount}}(p)\right)$$

4. **Guaranteed Safe Floor (Upward Ceiling + Buffer):**
   $$\text{Floor}(p) = \frac{\lceil \text{raw\_floor}(p) \times 100.0 \rceil}{100.0} + \epsilon \quad (\text{where } \epsilon = 0.01)$$

This formulation mathematically guarantees that for all valid inputs, $\text{Floor}(p) > \text{raw\_floor}(p)$, completely eliminating floating point precision underflow in evaluation checks.
