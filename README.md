# VaultLine — Guardrail-First Autonomous Seller Agent
**Event:** Techfest 2026-27 (IIT Bombay) · AgentX Challenge 2 – Selling to Machines

> **Core Principle:** *Code decides, the LLM only talks.*  
> Shoppers are deploying autonomous AI agents to negotiate on their behalf. Conventional store chatbots built for humans fail against machine buyers: they accept below-cost deals, get anchored by fabricated competitor quotes or fake budgets, leak internal margin structures, or end in deadlock. **VaultLine** separates deterministic pricing authority from natural-language generation using a five-layer zero-trust architecture.

---

## Documentation Suite (`docs/`)

All architectural blueprints, phased execution roadmaps, and module-level engineering specifications are located in the [`docs/`](file:///d:/Projects/VaultLine/docs) directory:

1. **[Master Implementation Plan](file:///d:/Projects/VaultLine/docs/IMPLEMENTATION_PLAN---SELLING%20TO%20MACHINES.md)** (`docs/IMPLEMENTATION_PLAN---SELLING TO MACHINES.md`)  
   Original workflow diagrams, layered architecture overview, hard constraints (`HC-1..HC-8`), functional/non-functional requirements, milestone schedule, and risk register.
2. **[Start-to-End System & Software Architecture](file:///d:/Projects/VaultLine/docs/ARCHITECTURE.md)** (`docs/ARCHITECTURE.md`)  
   Complete end-to-end topology, zero-trust boundaries, deep-dive internal design of the 5 seller layers (`InputGuard`, `StoreFacts`, `NegotiationEngine`, `Composer`, `OutputValidator`), mathematical formulas (dual-constraint floor, Boulware concession curve, reciprocity, bundle clamping, fairness by construction), data schemas, evaluation architecture, and requirements traceability matrix.
3. **[Start-to-End Implementation Phases & Execution Blueprint](file:///d:/Projects/VaultLine/docs/PHASES.md)** (`docs/PHASES.md`)  
   Step-by-step engineering roadmap from **Phase 0** (Day-1 starter kit verification checklist) through **Phase 7** (Interactive demo UI, Docker offline resilience, 1-page architecture note, 500-word abstract, and 3-minute video), including the 3-member daily synchronization matrix, milestone gates (`M1–M5`), and cut-order contingency playbook.
4. **[Module-by-Module Technical Specifications & Contracts](file:///d:/Projects/VaultLine/docs/MODULE_SPECIFICATIONS.md)** (`docs/MODULE_SPECIFICATIONS.md`)  
   File-by-file blueprint for the entire repository layout (`seller/`, `buyers/`, `experiments/`, `tests/`, `demo/`, `data/`), defining class interfaces, dataclasses, decision tables, 7-gate validator rules, buyer personas, and test suite contracts.
