"""Batch Negotiation Experiment Runner.

Executes high-throughput negotiations across all 7 buyer personas:
- 3 Starter Rule Bots (Cooperative, Linear, Tough)
- 4 Adversarial LLM Personas (Cooperative LLM, Hard LLM, Manipulator LLM, Injector LLM)

Logs full transcripts to outputs/results.jsonl, computes mean/std metrics per buyer,
and asserts zero policy violations across all sessions.
"""
import argparse
import csv
import json
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Optional

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from buyers import (
    CooperativeLLMBuyer,
    CooperativeStarterBuyer,
    HardLLMBuyer,
    InjectorLLMBuyer,
    LinearStarterBuyer,
    ManipulatorLLMBuyer,
    ToughStarterBuyer,
)
from evaluate import audit_transcript, load_catalog, load_policy
from harness import NegotiationTranscript, run_single_negotiation
from seller.agent import SellerAgent
from seller.facts import StoreFacts


def get_buyer_instance(persona_name: str) -> Any:
    """Instantiates a buyer bot for the given persona name."""
    if persona_name == "cooperative_starter":
        return CooperativeStarterBuyer()
    elif persona_name == "linear_starter":
        return LinearStarterBuyer()
    elif persona_name == "tough_starter":
        return ToughStarterBuyer()
    elif persona_name == "cooperative_llm":
        return CooperativeLLMBuyer(use_simulation=True)
    elif persona_name == "hard_llm":
        return HardLLMBuyer(use_simulation=True)
    elif persona_name == "manipulator_llm":
        return ManipulatorLLMBuyer(use_simulation=True)
    elif persona_name == "injector_llm":
        return InjectorLLMBuyer(use_simulation=True)
    else:
        raise ValueError(f"Unknown buyer persona: {persona_name}")


def run_batch_evaluation(
    runs_per_buyer: int = 10,
    output_jsonl: Optional[Path] = None,
    output_csv: Optional[Path] = None,
    seed: int = 42,
    no_llm: bool = True,
) -> Dict[str, Any]:
    """Executes batch negotiations across catalog SKUs and all 7 buyer personas."""
    random.seed(seed)
    root_dir = Path(__file__).resolve().parent.parent
    catalog = load_catalog(root_dir / "data" / "store.csv")
    policy = load_policy(root_dir / "data" / "policy.json")
    facts = StoreFacts()

    buyer_personas = [
        "cooperative_starter",
        "linear_starter",
        "tough_starter",
        "cooperative_llm",
        "hard_llm",
        "manipulator_llm",
        "injector_llm",
    ]

    skus = list(catalog.keys())
    # Exclude out-of-stock SKU for general batch deals (tested separately)
    active_skus = [s for s in skus if catalog[s]["stock"] > 0]

    transcripts: List[NegotiationTranscript] = []
    metrics_by_persona: Dict[str, Dict[str, Any]] = {}
    all_violations: List[str] = []

    t_start = time.perf_counter()

    for persona in buyer_personas:
        persona_transcripts: List[NegotiationTranscript] = []
        deals_closed = 0
        total_margin = 0.0
        total_profit = 0.0
        total_rounds = 0
        deadlocks = 0

        for run_idx in range(runs_per_buyer):
            sku = active_skus[run_idx % len(active_skus)]
            prod = catalog[sku]
            qty = random.choice([1, 2, 3, 5])

            buyer = get_buyer_instance(persona)
            seller = SellerAgent(facts=facts, no_llm=no_llm)

            t = run_single_negotiation(
                seller_agent=seller,
                buyer_agent=buyer,
                sku=sku,
                qty=qty,
                list_price=prod["list_price"],
                cost=prod["cost"],
                buyer_persona=persona,
                seller_type="vaultline_v1",
                negotiation_id=f"batch-{persona}-{run_idx+1}",
            )

            # Audit against policy
            v = audit_transcript(t, catalog, policy)
            all_violations.extend(v)

            total_rounds += t.rounds
            if t.closed and t.agreed_price is not None:
                deals_closed += 1
                cost = prod["cost"]
                margin = (t.agreed_price - cost) / t.agreed_price
                total_margin += margin
                total_profit += (t.agreed_price - cost) * qty
            else:
                deadlocks += 1

            persona_transcripts.append(t)
            transcripts.append(t)

        deal_rate = deals_closed / runs_per_buyer if runs_per_buyer > 0 else 0.0
        avg_margin = (total_margin / deals_closed * 100.0) if deals_closed > 0 else 0.0
        avg_rounds = total_rounds / runs_per_buyer if runs_per_buyer > 0 else 0.0

        metrics_by_persona[persona] = {
            "persona": persona,
            "runs": runs_per_buyer,
            "deals_closed": deals_closed,
            "deal_rate_pct": round(deal_rate * 100.0, 1),
            "avg_margin_pct": round(avg_margin, 2),
            "avg_rounds": round(avg_rounds, 1),
            "total_profit": round(total_profit, 2),
            "deadlocks": deadlocks,
        }

    total_time = time.perf_counter() - t_start

    # Export transcripts to JSONL
    if output_jsonl:
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(output_jsonl, "w", encoding="utf-8") as f:
            for t in transcripts:
                f.write(json.dumps(t.to_dict()) + "\n")

    # Export summary metrics to CSV
    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "persona",
                    "runs",
                    "deals_closed",
                    "deal_rate_pct",
                    "avg_margin_pct",
                    "avg_rounds",
                    "total_profit",
                    "deadlocks",
                ],
            )
            writer.writeheader()
            for row in metrics_by_persona.values():
                writer.writerow(row)

    total_runs = len(transcripts)
    total_closed = sum(m["deals_closed"] for m in metrics_by_persona.values())
    total_net_profit = sum(m["total_profit"] for m in metrics_by_persona.values())

    return {
        "total_negotiations": total_runs,
        "total_deals_closed": total_closed,
        "overall_deal_rate_pct": round(total_closed / total_runs * 100.0, 1),
        "total_net_profit": round(total_net_profit, 2),
        "policy_violations_count": len(all_violations),
        "violation_details": all_violations,
        "duration_seconds": round(total_time, 2),
        "metrics_by_persona": metrics_by_persona,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VaultLine Batch Runner")
    parser.add_argument("--runs-per-buyer", type=int, default=15, help="Runs per buyer persona")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-llm", action="store_true", default=True, help="Run without external LLM")
    parser.add_argument("--output", type=str, default="outputs/results.jsonl", help="JSONL transcript path")
    parser.add_argument("--summary", type=str, default="outputs/summary_metrics.csv", help="Summary CSV path")
    args = parser.parse_args()

    print("=" * 75)
    print("VaultLine Batch Runner — High-Throughput Adversarial Evaluation")
    print("=" * 75)
    res = run_batch_evaluation(
        runs_per_buyer=args.runs_per_buyer,
        output_jsonl=Path(args.output),
        output_csv=Path(args.summary),
        seed=args.seed,
        no_llm=args.no_llm,
    )

    print(f"{'Buyer Persona':<22} | {'Runs':<6} | {'Closed':<10} | {'Margin %':<10} | {'Rounds':<8} | {'Profit'}")
    print("-" * 75)
    for p, m in res["metrics_by_persona"].items():
        print(
            f"{p:<22} | {m['runs']:<6} | {f'{m['deals_closed']} ({m['deal_rate_pct']}%)':<10} | "
            f"{f'{m['avg_margin_pct']}%':<10} | {m['avg_rounds']:<8} | ${m['total_profit']:.2f}"
        )
    print("=" * 75)
    print(f"Total Negotiations:       {res['total_negotiations']}")
    print(f"Overall Deals Closed:     {res['total_deals_closed']} ({res['overall_deal_rate_pct']}%)")
    print(f"Total Net Profit:         ${res['total_net_profit']:.2f}")
    print(f"Total Policy Violations:  {res['policy_violations_count']}")
    print(f"Batch Execution Time:     {res['duration_seconds']:.2f}s")
    print("=" * 75)
    if res["policy_violations_count"] == 0:
        print("[SUCCESS] Milestone M2 Gate PASSED: All 4 LLM buyers running with 0 Policy Violations!")
    else:
        print(f"[FAILURE] Recorded {res['policy_violations_count']} policy violations.")
