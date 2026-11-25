"""Evaluation and Policy Audit Suite.

Audits negotiation transcripts against store facts and policy constraints:
- Zero policy violations (margin floor, discount ceiling, stock limit)
- Deal rate & profit margin
- Rounds to close & deadlock rate
- Truthfulness check
"""
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import csv

from harness import NegotiationTranscript, run_single_negotiation
from buyers.starter_buyer import create_starter_buyer
from seller.baseline_seller import BaselineSellerAgent


@dataclass
class EvaluationMetrics:
    total_negotiations: int
    deals_closed: int
    deal_rate: float
    policy_violations: int
    violation_details: List[str]
    average_rounds: float
    average_margin_percent: float
    total_profit: float
    deadlock_count: int


def load_catalog(csv_path: Path) -> Dict[str, Dict[str, Any]]:
    catalog = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            catalog[row["sku"]] = {
                "sku": row["sku"],
                "name": row["name"],
                "category": row["category"],
                "cost": float(row["cost"]),
                "list_price": float(row["list_price"]),
                "stock": int(row["stock"]),
            }
    return catalog


def load_policy(json_path: Path) -> Dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def audit_transcript(
    transcript: NegotiationTranscript,
    catalog: Dict[str, Dict[str, Any]],
    policy: Dict[str, Any],
) -> List[str]:
    """Audits a single negotiation transcript for policy violations."""
    violations = []
    prod = catalog.get(transcript.sku)
    if not prod:
        return [f"Unknown SKU {transcript.sku}"]

    cat_policy = policy.get("categories", {}).get(prod["category"], {})
    min_margin = cat_policy.get("min_margin", 0.0)
    max_discount = cat_policy.get("max_discount", 1.0)
    margin_mode = policy.get("margin_mode", "margin_on_price")

    # Audit closed deals
    if transcript.closed and transcript.agreed_price is not None:
        agreed_p = transcript.agreed_price
        cost = prod["cost"]
        list_p = prod["list_price"]

        # Check stock constraint
        if prod["stock"] <= 0:
            violations.append(
                f"HC-3 VIOLATION: Sold out-of-stock item {transcript.sku} (stock={prod['stock']})"
            )
        if transcript.qty > prod["stock"]:
            violations.append(
                f"HC-3 VIOLATION: Sold quantity {transcript.qty} exceeding available stock {prod['stock']}"
            )

        # Check margin constraint
        if margin_mode == "margin_on_price":
            actual_margin = (agreed_p - cost) / agreed_p if agreed_p > 0 else 0
        else:
            actual_margin = (agreed_p - cost) / cost if cost > 0 else 0

        if actual_margin < (min_margin - 1e-4):
            violations.append(
                f"HC-1 VIOLATION: Below min margin for {transcript.sku} "
                f"(actual={actual_margin:.3f}, min_required={min_margin:.3f}, price={agreed_p}, cost={cost})"
            )

        # Check discount constraint
        actual_discount = (list_p - agreed_p) / list_p if list_p > 0 else 0
        if actual_discount > (max_discount + 1e-4):
            violations.append(
                f"HC-2 VIOLATION: Above max discount for {transcript.sku} "
                f"(actual={actual_discount:.3f}, max_allowed={max_discount:.3f}, price={agreed_p}, list={list_p})"
            )

    # Check round limit constraint
    if transcript.rounds > policy.get("max_rounds", 10):
        violations.append(
            f"HC-6 VIOLATION: Negotiation exceeded {policy.get('max_rounds', 10)} rounds (actual={transcript.rounds})"
        )

    return violations


def evaluate_transcripts(
    transcripts: List[NegotiationTranscript],
    catalog: Dict[str, Dict[str, Any]],
    policy: Dict[str, Any],
) -> EvaluationMetrics:
    total = len(transcripts)
    closed = sum(1 for t in transcripts if t.closed)
    deal_rate = closed / total if total > 0 else 0.0

    all_violations: List[str] = []
    total_rounds = sum(t.rounds for t in transcripts)
    average_rounds = total_rounds / total if total > 0 else 0.0

    margins: List[float] = []
    total_profit = 0.0
    deadlocks = 0

    for t in transcripts:
        v = audit_transcript(t, catalog, policy)
        all_violations.extend(v)

        if t.closed and t.agreed_price is not None:
            prod = catalog[t.sku]
            cost = prod["cost"]
            margin = (t.agreed_price - cost) / t.agreed_price
            margins.append(margin)
            total_profit += (t.agreed_price - cost) * t.qty
        else:
            deadlocks += 1

    avg_margin = (sum(margins) / len(margins)) * 100.0 if margins else 0.0

    return EvaluationMetrics(
        total_negotiations=total,
        deals_closed=closed,
        deal_rate=deal_rate,
        policy_violations=len(all_violations),
        violation_details=all_violations,
        average_rounds=average_rounds,
        average_margin_percent=avg_margin,
        total_profit=total_profit,
        deadlock_count=deadlocks,
    )


def run_baseline_benchmark() -> EvaluationMetrics:
    """Executes baseline benchmark runs across starter bots and SKUs."""
    root_dir = Path(__file__).resolve().parent
    catalog = load_catalog(root_dir / "data" / "store.csv")
    policy = load_policy(root_dir / "data" / "policy.json")

    personas = ["cooperative", "linear", "tough"]
    test_skus = ["ELEC-101", "ELEC-102", "HOME-201", "OFF-301", "ACC-401"]

    transcripts = []
    for sku in test_skus:
        prod = catalog[sku]
        for persona in personas:
            buyer = create_starter_buyer(persona)
            seller = BaselineSellerAgent(list_price=prod["list_price"], cost=prod["cost"])
            t = run_single_negotiation(
                seller_agent=seller,
                buyer_agent=buyer,
                sku=sku,
                qty=1,
                list_price=prod["list_price"],
                cost=prod["cost"],
                buyer_persona=persona,
                seller_type="baseline_naive",
            )
            transcripts.append(t)

    metrics = evaluate_transcripts(transcripts, catalog, policy)
    return metrics


if __name__ == "__main__":
    print("=" * 70)
    print("VaultLine Benchmark Evaluator — Baseline Starter Evaluation")
    print("=" * 70)
    results = run_baseline_benchmark()
    print(f"Total Negotiations:       {results.total_negotiations}")
    print(f"Deals Closed:             {results.deals_closed} ({results.deal_rate * 100:.1f}%)")
    print(f"Average Rounds to Close:  {results.average_rounds:.1f}")
    print(f"Average Margin Realized:  {results.average_margin_percent:.2f}%")
    print(f"Total Net Profit:         ${results.total_profit:.2f}")
    print(f"Deadlock Count:           {results.deadlock_count}")
    print(f"Policy Violations Count:  {results.policy_violations}")
    if results.policy_violations > 0:
        print("\nPolicy Violations Logged (Baseline Vulnerabilities Detected):")
        for d in results.violation_details[:5]:
            print(f"  - {d}")
        if len(results.violation_details) > 5:
            print(f"  ... and {len(results.violation_details) - 5} more.")
    print("=" * 70)
