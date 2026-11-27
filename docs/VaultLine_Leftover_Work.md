# VaultLine: Leftover Work Plan

**Event:** Techfest 2026-27, AgentX Challenge 2 (Selling to Machines)
**Hard deadline:** 30 Nov 2026, 11:59 PM IST (registration and Round 1 submission)
**Plan written:** 27 Nov 2026
**Scope:** Items found missing or weak during the repo review. I could only see the top-level repo files, the README and `docs/ABSTRACT.md`, so Phase 1 starts by checking the folders I couldn't open.

---

## Phase 0: Registration and Ownership (27 Nov, do first)

- [ ] Confirm the team is **registered at techfest.org** and has a Team ID. Registration closes at the same time as submission.
- [ ] Decide who the **Team Leader** is. Only the leader's submission counts.
- [ ] Settle the **fork question**. The repo is a fork of `Anish1302D/VaultLine`.
  - [ ] Confirm Anish is a teammate, or credit all contributors in the README.
  - [ ] Consider detaching the fork or moving to a repo owned by the team, so it can't look like copied work.
- [ ] Add a real `LICENSE` file (MIT, to match the README badge).

---

## Phase 1: Verify the Unseen Parts (27 Nov)

- [ ] Open `data/` and confirm `store.csv` and `policy.json` are present and match the organisers' versions.
- [ ] Open `buyers/` and confirm the three starter bots and your four LLM personas are all there.
- [ ] Open `outputs/` and confirm `summary_metrics.csv` and the per-run logs are there and match the README table.
- [ ] Check `tests/`: do the 93 tests actually pass on a clean machine?
- [ ] Confirm `harness.py` and `evaluate.py` are **unmodified originals**, since the hidden evaluation uses the organisers' versions.
  - [ ] Run your seller through the untouched files once more.
- [ ] Check that the CI workflow in `.github/workflows` runs green.

---

## Phase 2: Fix the README and Reproducibility (27-28 Nov)

- [ ] Replace every `VaultLine/VaultLine` clone URL and badge link with `Mihir-Mendake/VaultLine` (or the new canonical repo).
- [ ] Remove the Windows-only `.venv/Scripts/python.exe` commands.
  - [ ] Use `python -m pytest -v`.
  - [ ] Use `python -m streamlit run demo/app.py`.
- [ ] Test the 5-command quickstart on a **clean Linux or Mac environment** (or a Docker container).
- [ ] Verify `docker build` and `docker run --network none` work as the README claims.
- [ ] Make sure `requirements.txt` is complete (fresh install, then run the tests).

---

## Phase 3: Robustness Testing (28 Nov)

- [ ] Run the seller through the **official starter harness** with all three official starter bots.
- [ ] Test against **free-text LLM buyers** phrasing offers in unusual ways.
  - [ ] Check that the input guard still extracts price and quantity correctly.
  - [ ] Check that parse failures lead to a safe fallback, not a bad deal.
- [ ] Re-run the manipulator and injector scenarios with the **optional LLM paraphraser on** (the README default is off) and confirm the validator still catches every violation.
- [ ] Look at the weak personas:
  - [ ] `tough_starter` (16.7% deal rate): confirm walking away is correct and write down why.
  - [ ] `hard_llm` (65.7%): check whether any safe concession tuning would raise the deal rate without lowering margin.
- [ ] Record the final benchmark numbers with a fixed seed and update the README table.

---

## Phase 4: Abstract and Written Deliverables (28-29 Nov)

- [ ] **Recount the abstract.** The README says 463 words, but the file looks closer to 500. It must stay at or under **500 words**.
- [ ] Add the missing sections the PDF asks for:
  - [ ] **Impact:** who benefits and what failure it prevents.
  - [ ] **Cost estimate:** inference cost per negotiation, hosting cost, and how it scales. This feeds the 15-point Feasibility criterion.
- [ ] Keep the innovation and build summary (already strong).
- [ ] Check that `ARCHITECTURE_NOTE.md` is really **one page**.
- [ ] Check that numbers in the abstract, the architecture note and the README all agree.
- [ ] Review `AGENT_CARD.json` so it clearly states what the seller can and cannot negotiate.

---

## Phase 5: Demo Video (29 Nov)

- [ ] Rehearse from `docs/DEMO_SCRIPT.md` and trim it to **3 minutes or less**.
- [ ] Record the video, showing:
  - [ ] The Streamlit demo against a normal buyer.
  - [ ] A manipulator or injector attack being blocked.
  - [ ] The benchmark results and the zero-violations proof.
- [ ] Check audio and screen readability.
- [ ] Export it and upload it to Google Drive.

---

## Phase 6: Package and Submit (30 Nov, finish well before 11:59 PM)

- [ ] Create **one Google Drive folder** containing:
  - [ ] Abstract (PDF or Doc)
  - [ ] 1-page architecture note
  - [ ] 3-minute demo video
  - [ ] Text or doc file with the **public GitHub repo link**
  - [ ] Outputs from the runs (`outputs/` exports)
- [ ] Set the folder's sharing to **"Anyone with the link can view."**
- [ ] Open the folder link in an **incognito window** to confirm it works.
- [ ] Confirm the GitHub repo is public and the final commit is pushed.
- [ ] The **Team Leader** pastes the Drive link into the **"Submission Link"** field on techfest.org.
- [ ] Take a screenshot of the confirmation.
- [ ] **Target finishing by the evening of 30 Nov**, not at 11:50 PM.

---

## Phase 7: After Submission (if shortlisted)

- [ ] Round 1 results are announced by **5 Dec 2026**.
- [ ] Prepare the **10-minute pitch + 5-minute Q&A** for the finals (IIT Bombay, 16-18 Dec).
- [ ] Prepare **latency and cost numbers** (the finals judge these under Feasibility).
- [ ] Prepare a code walkthrough of the 5 layers and be ready for design questions.
- [ ] Prepare a **live robustness demo** for jury-chosen test cases.
- [ ] Expect a **fresh hidden set**, and don't tune only to your own benchmark.
- [ ] Keep an eye on the Competition Portal's Doubt section and your email for updates.

---

## Priority Summary

| Priority | Item |
|---|---|
| 🔴 Must do | Demo video, abstract word count, cost and impact content, registration, Drive folder and submission |
| 🟠 Should do | README clone URLs and cross-platform commands, fork or credit issue, `LICENSE`, unmodified `evaluate.py` and `harness.py` check |
| 🟡 Nice to have | Weak-persona tuning, paraphraser-on testing, extra edge-case tests |
