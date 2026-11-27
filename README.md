# VaultLine — Guardrail-First Autonomous Seller Agent
**Event:** Techfest 2026-27 (IIT Bombay) · AgentX Challenge 2 – Selling to Machines  
**Core Axiom:** *"Code decides, the LLM only talks."* The LLM has zero pricing authority.

[![CI Quality Gate](https://github.com/Anish1302D/VaultLine/actions/workflows/ci.yml/badge.svg)](https://github.com/Anish1302D/VaultLine/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker Offline](https://img.shields.io/badge/docker-offline%20ready-green.svg)](Dockerfile)
[![Policy Violations](https://img.shields.io/badge/violations-0%20(2%2C100%20runs)-brightgreen.svg)](outputs/summary_metrics.csv)

---

## 5-Command Quickstart

Get VaultLine running in under 60 seconds (cross-platform: Linux, macOS, Windows):

```bash
# 1. Clone repository
git clone https://github.com/Anish1302D/VaultLine.git && cd VaultLine

# 2. Setup virtual environment & install locked dependencies
uv venv && uv pip install -r requirements.txt
# (or: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt)

# 3. Run full 93-test verification suite (unit, red-team, metamorphic fairness)
pytest -v tests/

# 4. Launch interactive dual-pane Streamlit Workbench
streamlit run demo/app.py

# 5. (Optional) Run 100% offline inside Docker with zero network access
docker build -t vaultline:latest .
docker run --rm --network none vaultline:latest
```

---

## Benchmark Performance (2,100 Batch Negotiations)

VaultLine was comprehensively evaluated across 2,100 negotiations ($\ge 300$ runs per buyer persona) using seed 42:

| Buyer Persona | Strategy / Attack Vector | Runs | Deals Closed | Deal Rate % | Avg Margin Kept % | Avg Rounds | Total Profit | Policy Violations |
|---|---|---|---|---|---|---|---|---|
| `cooperative_starter` | Predictable upward concessions | 300 | 275 | 91.7% | 33.17% | 6.1 | $48,613.44 | **0** |
| `linear_starter` | Fixed linear price increment | 300 | 225 | 75.0% | 32.58% | 7.7 | $35,308.80 | **0** |
| `tough_starter` | Holds below-floor price | 300 | 50 | 16.7% | 35.21% | 8.8 | $2,194.52 | **0** |
| `cooperative_llm` | Value-seeking natural language | 300 | 275 | 91.7% | 34.43% | 5.2 | $54,196.16 | **0** |
| `hard_llm` | Aggressive low-balling & holdout | 300 | 197 | 65.7% | 29.87% | 9.0 | $27,153.86 | **0** |
| `manipulator_llm` | Fake competitor quotes & fake budgets | 300 | 253 | 84.3% | 32.74% | 7.3 | $45,363.27 | **0** |
| `injector_llm` | Jailbreaks, authority claims & cost probes | 300 | 253 | 84.3% | 32.03% | 7.4 | $43,391.22 | **0** |
| **Total / Overall** | **Comprehensive Benchmark** | **2,100** | **1,528** | **72.8%** | **32.87%** | **7.3** | **$256,221.27** | **0 (Zero)** |

---

## 5-Layer System Architecture

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

## Documentation Index

- **[Master Implementation Plan](docs/IMPLEMENTATION_PLAN---SELLING%20TO%20MACHINES.md)**: Requirements traceability, hard constraints (HC-1..HC-8), and risk matrix.
- **[System Architecture](docs/ARCHITECTURE.md)**: 5-layer topology, trust boundaries, and mathematical proofs.
- **[1-Page Architecture Note](docs/ARCHITECTURE_NOTE.md)**: Executive summary for competition evaluators.
- **[500-Word Abstract](docs/ABSTRACT.md)**: Competition abstract (463 words).
- **[3-Minute Demo Video Script](docs/DEMO_SCRIPT.md)**: Presentation script with time codes.
- **[Project Status Tracker](docs/PROJECT_STATUS.md)**: Milestone and phase audit.
- **[Decision Log](DECISIONS.md)**: Verification checklist (V-1..V-8) and grid search results.
