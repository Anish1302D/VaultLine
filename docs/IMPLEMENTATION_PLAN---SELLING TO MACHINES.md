# AgentX Challenge 2 – Selling to Machines
## Implementation Plan

**Event:** Techfest 2026-27 (IIT Bombay) · AgentX by Rezolve.ai
**Round 1 deadline:** 30 Nov 2026, 11:59 PM IST (target submission: 6 PM)
**Team:** 3 members (A – Engine/Leader, B – Safety/Testing, C – Buyers/Demo)

> **Core principle:** *Code decides, the LLM only talks.* The LLM never has authority over a price or a fact. A deterministic engine computes every number; an independent validator blocks anything unsafe before it is sent.

> **VERIFY items:** The starter kit (`store.csv`, `policy.json`, `harness.py`, `evaluate.py`, buyer bots) has not been seen. Anything marked **VERIFY** must be confirmed on Day 1.

---

## Contents
1. [Workflow Diagrams](#1-workflow-diagrams)
2. [Architecture Diagrams](#2-architecture-diagrams)
3. [Requirements](#3-requirements)
4. [Implementation Phases and Milestones](#4-implementation-phases-and-milestones)
5. [Repository Layout](#5-repository-layout)
6. [Risks and Open Questions](#6-risks-and-open-questions)

---

## 1. Workflow Diagrams

### 1.1 Per-turn negotiation workflow (runtime)

What happens every time a buyer bot sends a message. Maximum 10 rounds per negotiation.

```mermaid
flowchart TD
    A([Buyer message JSON arrives]) --> B{Round > 10?}
    B -- Yes --> Z1([Walk away politely - never exceed 10 rounds])
    B -- No --> C[Input Guard: schema-validate JSON]
    C --> D{Schema valid?}
    D -- No --> D1[Ignore bad fields, use safe defaults]
    D -- Yes --> E
    D1 --> E[Scan ALL free-text fields for injection / authority claims / fake quotes]
    E --> F[Extract structured intent: product, qty, offered price, bundle request, claims]
    F --> G[Store Facts: load list price, floor, stock for requested items]
    G --> H{Item in stock and qty <= stock?}
    H -- No --> H1[Offer in-stock alternative or decline item - no invented restock date]
    H -- Yes --> I[Negotiation Engine: update state, detect buyer pattern]
    H1 --> I
    I --> J{Buyer offer >= reservation price for this round?}
    J -- Yes --> K[ACCEPT deal at buyer price - must be >= floor]
    J -- No --> L{Round >= 8?}
    L -- Yes --> M[Issue clear FINAL offer, legal price >= floor]
    L -- No --> N[Compute counter via concession curve + reciprocity + bundle option]
    M --> O
    N --> O[Fact object: price, qty, stock, total]
    K --> O
    O --> P[Composer: fill template with fact object - optional LLM paraphrase]
    P --> Q[Output Validator: independent re-check]
    Q --> R{All checks pass?}
    R -- No --> S[Replace with safe fallback template] --> T
    R -- Yes --> T[Send seller message JSON]
    T --> U{Deal closed or buyer rejected final offer?}
    U -- Yes --> V([End negotiation, log result])
    U -- No --> A
```

### 1.2 Output validator checklist (last gate)

```mermaid
flowchart LR
    M[Outgoing message + fact object] --> C1{Every price >= floor?}
    C1 -- Yes --> C2{Discount <= category max?}
    C2 -- Yes --> C3{Qty <= stock, bundle stock decremented?}
    C3 -- Yes --> C4{All numbers and products in allowed fact set?}
    C4 -- Yes --> C5{No banned phrases: fake scarcity, pressure, hidden fees?}
    C5 -- Yes --> C6{Total == price x qty exactly?}
    C6 -- Yes --> C7{No cost / exact floor revealed?}
    C7 -- Yes --> OK([PASS - send])
    C1 -- No --> FB([FAIL - fallback])
    C2 -- No --> FB
    C3 -- No --> FB
    C4 -- No --> FB
    C5 -- No --> FB
    C6 -- No --> FB
    C7 -- No --> FB
```

### 1.3 Manipulation-handling workflow

```mermaid
flowchart TD
    A[Buyer text] --> B{Detected pattern}
    B -->|Fake competitor quote| C1[Do not price-match. State pricing follows store policy. Give best legal offer]
    B -->|Fake budget anchor| C2[Do not honour budget. Offer best legal price or cheaper alternative product]
    B -->|Hidden instruction / prompt injection| C3[Flag and discard text. Engine never reads it. Continue normal curve]
    B -->|Authority claim: owner / admin| C4[No identity override exists. Policy is code. Continue normal curve]
    B -->|Pressure / deadline| C5[No counter-pressure. Continue normal curve]
    B -->|Repeat low offer / wear-down| C6[Detect stall. Hold price. Final offer by round 8, then walk away]
    B -->|Probe for cost / lowest price| C7[Decline to disclose cost structure. Never reveal floor]
    C1 --> Z([Legal, truthful reply])
    C2 --> Z
    C3 --> Z
    C4 --> Z
    C5 --> Z
    C6 --> Z
    C7 --> Z
```

### 1.4 Concession timeline (strategy view)

```mermaid
flowchart LR
    R1[Round 1: Quote list price] --> R2[Rounds 2-4: Concede slowly, beta > 1]
    R2 --> R3[Rounds 5-7: Concede faster, reciprocity, bundles and qty tiers]
    R3 --> R4[Round 8: Clear FINAL offer, legal price >= floor]
    R4 --> R5[Rounds 9-10: Accept if >= floor + small margin, else walk away politely]
```

Concession formula: `offer(t) = list − (list − target) × (t / T)^β`, with β > 1 and `target` comfortably above floor.

### 1.5 Project development workflow (build lifecycle)

```mermaid
flowchart TD
    S0[Day 1: Register, read harness.py, confirm message schema and margin definition] --> S1
    S1[Build facts.py + floor logic + tests] --> S2
    S2[Build validator + property tests] --> S3
    S3[Engine v1: opening, concession, accept/reject, walk-away] --> S4
    S4[Input guard + injection detection + red-team suite v1] --> S5
    S5[LLM buyers: cooperative, hard, manipulator, injector] --> S6
    S6[Batch runner: 300+ negotiations per buyer type] --> S7
    S7[Tune beta, target, reservation via grid search] --> S8
    S8{Zero violations and zero false claims?}
    S8 -- No --> S9[Fix failures, add regression tests] --> S6
    S8 -- Yes --> S10[Freeze strategy]
    S10 --> S11[Architecture note, README, Docker check]
    S11 --> S12[Demo video, abstract, Drive folder]
    S12 --> S13([Leader submits on website by 6 PM, 30 Nov])
```

### 1.6 Git / CI workflow

```mermaid
flowchart LR
    A[Feature branch] --> B[Pull request] --> C[CI: ruff + black + pytest + hypothesis]
    C --> D[CI: 50-negotiation smoke run with deterministic bots]
    D --> E{Any policy violation?}
    E -- Yes --> F[Block merge]
    E -- No --> G[Reviewer approval; engine/validator PRs need Member A]
    G --> H[Merge to main] --> I[Tag release]
```

---

## 2. Architecture Diagrams

### 2.1 Layered system architecture

```mermaid
flowchart TB
    subgraph External
        BUY[Buyer bot - starter kit or hidden LLM]
        HAR[harness.py - runs negotiation, logs messages]
    end

    subgraph SellerAgent[Seller Agent - seller/agent.py]
        direction TB
        G[1. Input Guard - guard.py<br/>schema validation, injection flags, intent extraction]
        F[2. Store Facts - facts.py<br/>store.csv + policy.json: floor, list, stock]
        E[3. Negotiation Engine - engine.py<br/>concession curve, bundles, accept / reject / walk-away]
        C[4. Composer - composer.py<br/>templates + optional LLM paraphrase]
        V[5. Output Validator - validator.py<br/>independent re-check of every number and claim]
    end

    subgraph Data[Single source of truth]
        CSV[(store.csv)]
        POL[(policy.json)]
    end

    LLM[Optional LLM - low temperature<br/>language only, no authority]

    BUY -->|JSON message| HAR
    HAR -->|JSON message| G
    G -->|structured intent| E
    F --> E
    CSV --> F
    POL --> F
    E -->|fact object| C
    C -.->|paraphrase request| LLM
    LLM -.->|text only| C
    C -->|draft message| V
    F -->|independent floor and stock check| V
    V -->|validated message or fallback| HAR
    HAR -->|JSON reply| BUY
```

### 2.2 Trust boundaries

```mermaid
flowchart LR
    subgraph Untrusted
        U1[Buyer free text]
        U2[Product notes / JSON fields from buyer]
        U3[LLM-generated wording]
    end
    subgraph Trusted[Trusted - deterministic code]
        T1[Input Guard]
        T2[Negotiation Engine]
        T3[Output Validator]
        T4[Store data + policy]
    end
    U1 --> T1
    U2 --> T1
    T1 -->|structured intent only| T2
    T4 --> T2
    T2 -->|fact object| U3
    U3 -->|text| T3
    T4 --> T3
    T3 --> OUT([Sent to buyer])
```

Rules: buyer text never reaches any prompt with authority over pricing; LLM output is always re-validated.

### 2.3 Negotiation engine internals

```mermaid
flowchart TB
    IN[Structured intent + store facts] --> ST[Per-negotiation state<br/>round, history, buyer pattern]
    ST --> PAT[Pattern detector: cooperative / stalling / wear-down]
    ST --> FLR[Floor calculator<br/>max of margin floor and discount floor, rounded up + epsilon]
    ST --> STK[Stock tracker<br/>decrement across bundle]
    PAT --> CUR[Concession curve + reciprocity]
    FLR --> CUR
    FLR --> RES[Reservation price by round]
    CUR --> DEC{Decision}
    RES --> DEC
    STK --> BUN[Bundle / qty-tier builder<br/>floor applied per line item]
    DEC -->|accept| OUT[Fact object]
    DEC -->|counter| BUN --> OUT
    DEC -->|final offer| OUT
    DEC -->|walk away| OUT
```

Floor rule: `floor = ceil( max( cost/(1−min_margin) [or cost×(1+min_margin) – VERIFY], list×(1−max_discount) ) ) + epsilon`

### 2.4 Evaluation and test architecture

```mermaid
flowchart TB
    subgraph Buyers[Buyer bots]
        S1[Starter rule-based bots x3]
        L1[Cooperative LLM]
        L2[Hard-bargainer LLM]
        L3[Manipulator LLM]
        L4[Injector LLM]
    end

    subgraph Runner[Experiment runner - asyncio / multiprocessing]
        RB[run_batch.py]
        TU[tune.py - grid search beta, target, reservation]
    end

    SELL[Seller agent]
    LOG[(results.jsonl / CSV logs)]

    subgraph Checks[Automated checks]
        TA[Truthfulness audit: extract numbers, compare to store.csv]
        PV[Policy violation counter]
        FP[Fairness pairs: metamorphic test]
        PB[Property tests: hypothesis, 10,000+ cases]
        RT[Red-team suite: 30+ attacks]
    end

    REP[Notebook: deal rate, margin, deadlocks, plots]
    DEMO[Streamlit demo UI]

    Buyers --> RB
    RB --> SELL
    SELL --> LOG
    TU --> RB
    LOG --> TA
    LOG --> PV
    LOG --> REP
    PB --> SELL
    RT --> SELL
    FP --> SELL
    REP --> DEMO
```

### 2.5 Deployment architecture (demo and production story)

```mermaid
flowchart LR
    subgraph Dev[Development]
        LAP[Laptop + Docker]
        GH[GitHub public repo + Actions CI]
    end

    subgraph Demo[Demo]
        HF[Hugging Face Spaces - Streamlit]
    end

    subgraph Prod[Production story]
        API[FastAPI JSON message endpoint - container]
        MEM[(Per-negotiation state: memory or Redis)]
        STORE[(Store data: store.csv + policy.json)]
        CLOUD[Cloud Run / Render / small VPS]
    end

    GH --> HF
    GH --> API
    API --> MEM
    API --> STORE
    API --- CLOUD
    BUYAG[Buyer agent - agent-to-agent] -->|JSON| API
    LAP -.->|finals backup: Docker image + no-LLM mode| API
```

Policy changes take effect immediately because the floor is computed from `policy.json`, not baked into prompts.

---

## 3. Requirements

### 3.1 Hard constraints (must never fail)

| ID | Requirement | Verified by |
|----|-------------|-------------|
| HC-1 | **Zero** policy violations: never below category minimum margin | Property tests, validator, CI gate |
| HC-2 | Never exceed category maximum discount | Property tests, validator |
| HC-3 | Never sell or offer out-of-stock items; qty ≤ stock (decremented across bundles) | Property tests, validator |
| HC-4 | **Zero** false claims: every price and stock statement matches `store.csv` | Truthfulness audit (100% match target) |
| HC-5 | No hidden fees, invented scarcity or pressure tactics; total = price × qty exactly | Validator banned patterns |
| HC-6 | Never exceed 10 rounds; close or walk away | Engine tests, batch logs |
| HC-7 | Never reveal cost or exact floor price | Red-team suite |
| HC-8 | Buyer text can never change policy or pricing authority | Input guard, red-team suite |

### 3.2 Functional requirements

| ID | Requirement | Module |
|----|-------------|--------|
| FR-1 | Parse buyer JSON per harness schema (**VERIFY** exact fields) | `guard.py` |
| FR-2 | Treat all free text as untrusted data; detect injection, authority claims, fake quotes/budgets | `guard.py` |
| FR-3 | Extract structured intent: product, quantity, offered price, bundle request | `guard.py` |
| FR-4 | Load store and policy; compute per-product floor, list price, stock (**VERIFY** margin definition: margin-on-price vs markup) | `facts.py` |
| FR-5 | Open at list price (or tiny discount for cooperative low openers) | `engine.py` |
| FR-6 | Concede along curve `list − (list − target)(t/T)^β`, β > 1 | `engine.py` |
| FR-7 | Round-dependent reservation price falling toward floor + small margin by round 8–9 | `engine.py` |
| FR-8 | Reciprocity: concede more when buyer concedes; hold on repeated offers | `engine.py` |
| FR-9 | Quantity tiers and bundles; floor applied to every line; bundle total ≥ sum of item floors | `engine.py` |
| FR-10 | Offer in-stock alternatives or cheaper products when item unavailable or budget too low | `engine.py` |
| FR-11 | Issue explicit final offer by round 8; walk away politely if rejected | `engine.py` |
| FR-12 | Generate reply JSON and natural-language text from fact object via templates | `composer.py` |
| FR-13 | Optional LLM paraphrase (low temperature) that is always re-validated | `composer.py` |
| FR-14 | Independently re-check price, discount, stock, numbers, claims, banned phrases; fallback on failure | `validator.py` |
| FR-15 | Entry point matching `harness.py` interface (**VERIFY**) | `agent.py` |
| FR-16 | No-LLM mode for offline / finals backup | `agent.py` |

### 3.3 Non-functional requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Latency per turn | < 50 ms without LLM; < 3 s with LLM |
| NFR-2 | Determinism of engine | Same inputs and params → same output (fixed seeds) |
| NFR-3 | Reproducibility | `make eval` reproduces all reported numbers |
| NFR-4 | Cost per negotiation (production) | ~Rs 0.5–5 (measure real tokens before quoting) |
| NFR-5 | Dev/test LLM budget | Rs 500–3,000 total |
| NFR-6 | Security | API keys in env vars only; never committed |
| NFR-7 | Setup | README with 5-command setup |
| NFR-8 | Code quality | ruff, black, pre-commit; mypy optional |
| NFR-9 | Portability | Docker + requirements.txt + Makefile |

### 3.4 Performance and quality targets

| Metric | Target |
|--------|--------|
| Policy violations | 0 |
| False claims / truthfulness match | 0 / 100% |
| Deal rate | Above baseline seller |
| Margin kept | As high as possible (optimise deal rate × margin) |
| Deadlock rate | Low |
| Red-team pass rate | 100% of attacks give legal, truthful replies |
| Property tests | No failing case in 10,000+ examples |
| Batch size | ≥ 300 negotiations per buyer type, report mean and standard deviation |

### 3.5 Stretch requirements (cut first if short on time)

| ID | Requirement |
|----|-------------|
| ST-1 | Fairness: offer depends only on product, quantity, round and buyer concession pattern; never on tone, politeness, identity or message length. Metamorphic paired-buyer test |
| ST-2 | `AGENT_CARD.json` declaring what can and cannot be negotiated |
| ST-3 | Live demo on Hugging Face Spaces with policy panel (floor, margin, violations = 0) |
| ST-4 | FastAPI endpoint with containerised deployment |

> **Cut order if time runs short:** fairness → agent card → hosted demo. **Never cut** the validator or red-team tests.

### 3.6 Technology requirements

| Layer | Choice |
|-------|--------|
| Language | Python 3.11 |
| Data / models | pandas, pydantic |
| Engine | Plain Python classes (LangGraph optional) |
| Seller LLM (optional) | Claude Haiku-class, Gemini Flash, Groq Llama 3.x, or local Qwen2.5 via Ollama |
| Buyer LLMs | Different provider/model than seller; diverse personas |
| Testing | pytest, hypothesis |
| Experiments | asyncio / multiprocessing, JSONL/CSV logs |
| Analysis | pandas, matplotlib, Jupyter |
| Demo | Streamlit |
| CI | GitHub Actions |
| Packaging | Docker, requirements.txt, Makefile |

### 3.7 Deliverable requirements

| Deliverable | Spec | Owner |
|-------------|------|-------|
| Abstract | ≤ 500 words: problem/impact (80), approach/innovation (150), build (100), results (80), cost/scale (60), limitations (30) | C drafts, all review |
| Demo video | 3 minutes: round-by-round negotiation, manipulator attack resisted, metrics | C |
| Public code repo | Seller, our buyer bots, tests, outputs | All; B owns hygiene |
| Architecture note | 1 page | A |
| Drive folder | Abstract, note, video, repo link, outputs; link sharing on (test in incognito) | C assembles |
| Website submission | **Team Leader only**; before 30 Nov 11:59 PM IST | A |
| Finals readiness | Everyone available 16–18 Dec 2026; 10 min pitch + 5 min Q&A | All |

### 3.8 Requirements-to-scoring traceability

| Judging criterion (pts) | Requirements that serve it |
|-------------------------|----------------------------|
| Benchmark (25) | HC-1…HC-6, FR-5…FR-11 |
| Technical depth (20) | FR-14, NFR-2, NFR-8, property tests, architecture note |
| Robustness (15) | HC-7, HC-8, FR-2, red-team suite |
| Innovation (15) | Guardrail-first design, independent validator, fairness by construction |
| Feasibility, cost, scale (15) | NFR-1, NFR-4, ST-4, abstract cost section |

---

## 4. Implementation Phases and Milestones

| Day | Member A (Engine, Leader) | Member B (Safety, Testing) | Member C (Buyers, Demo) |
|-----|---------------------------|-----------------------------|--------------------------|
| **Wed 25** | Register team; read harness.py; confirm message schema and margin definition; run starter bots | Repo, CI, `facts.py` + floor tests | Task board, Drive folder, persona prompts v1 |
| **Thu 26** | Engine v1: opening, curve, accept/reject, walk-away | Validator v1 + property tests | Cooperative and hard LLM buyers in harness |
| **Fri 27** | Bundles, qty logic, deadlock handling | Input guard + injection detection; red-team v1 | Manipulator and injector LLM buyers; batch runner |
| **Sat 28** | Parameter tuning; fairness logic | Fix red-team failures; truthfulness audit | 300+ negotiations per buyer type; plots; Streamlit demo |
| **Sun 29** | Architecture note; freeze strategy | Final tests, README, Docker check | Record video; write abstract; produce outputs |
| **Mon 30** | Final review of all files | Tag release; clean repo | Assemble Drive folder; **Leader submits by 6 PM** |

### Day 1 verification checklist
- [ ] Exact buyer/seller JSON fields in `harness.py`
- [ ] How bundles are expressed in messages
- [ ] How accept / reject / walk-away are signalled
- [ ] Margin definition in `policy.json` / `evaluate.py` (on price vs markup)
- [ ] Rounding and currency unit
- [ ] Starter bot behaviour and baseline scores from `evaluate.py`
- [ ] Whether stock is shared across concurrent negotiations

### Milestone gates
1. **M1 (Thu night):** Facts + validator + property tests green; engine closes a deal vs starter bot with 0 violations.
2. **M2 (Fri night):** All four LLM buyers running; red-team suite v1 passing.
3. **M3 (Sat night):** 300+ runs per buyer type logged; tuned parameters recorded in `DECISIONS.md`.
4. **M4 (Sun night):** Strategy frozen; all deliverables drafted.
5. **M5 (Mon 6 PM):** Submitted.

---

## 5. Repository Layout

```
agentx-c2/
├── README.md  DECISIONS.md  AGENT_CARD.json  requirements.txt  Dockerfile  Makefile
├── data/                 store.csv, policy.json (read-only starter kit)
├── seller/
│   ├── facts.py          load store/policy; floor and stock functions
│   ├── guard.py          sanitising, injection flags, intent extraction
│   ├── engine.py         concession curve, accept/reject, bundles, walk-away
│   ├── composer.py       templates (+ optional LLM paraphrase)
│   ├── validator.py      independent output checks
│   └── agent.py          entry point matching harness.py
├── buyers/
│   ├── cooperative_llm.py  hard_llm.py  manipulator_llm.py  injector_llm.py
│   └── prompts/
├── experiments/          run_batch.py  tune.py  report.ipynb
├── tests/                test_floor.py  test_validator.py  test_guard.py
│                         test_fairness.py  test_properties.py
├── demo/app.py           Streamlit chat view + policy panel
├── outputs/              logs, metrics, plots
└── .github/workflows/ci.yml
```

---

## 6. Risks and Open Questions

| Risk | Impact | Mitigation |
|------|--------|------------|
| Policy violation from bug or LLM output | Severe (target zero) | Code-computed floor, independent validator, property tests, CI gate |
| Hidden LLM buyers differ from ours | Lower deal rate | Diverse personas, multiple providers, multiple seeds; avoid tuning to one bot |
| Over-conservative seller deadlocks | Low deal rate | Reservation falls to near floor by round 8; clear final offer |
| Over-generous seller | Low margin | Slow concession, reciprocity, tune on margin × deal rate |
| Margin definition misunderstood | Hidden violations | Verify on Day 1 against `evaluate.py` |
| Injection via unexpected JSON fields | Manipulation succeeds | Engine ignores free text; schema validation; fuzz all fields |
| Teammate unavailable | Delay | Pair on safety-critical modules; shared reviews |
| Venue Wi-Fi failure at finals | Demo fails | Docker image, offline logs, recorded video, no-LLM mode |

### Open questions to resolve on Day 1
1. Is the final quote total per item or per bundle in the harness schema?
2. Do hidden buyers see stock levels or list prices up front?
3. Is the seller scored on margin per deal, total profit, or margin percentage?
4. Are there tie-breaking or latency limits in the harness?

---

*Safety first: a seller that cannot violate policy is the foundation. Improve deal rate only after that foundation is tested.*
