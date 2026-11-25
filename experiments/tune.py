"""Hyperparameter Grid Search Tuning Suite (Phase 6).

Sweeps across:
- Concession exponent beta in {1.2, 1.5, 1.8, 2.2}
- Target retention ratio gamma in {0.15, 0.22, 0.30, 0.38}
- Reciprocity weight rho in {0.10, 0.20, 0.30}

Optimizes:
    Utility = DealRate * MeanMarginKept
Subject to:
    Violations == 0 and Truthfulness == 100%

Records all results to outputs/grid_search_results.csv and identifies optimal parameters.
"""
import csv
import itertools
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Tuple

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
from harness import run_single_negotiation
from seller.agent import SellerAgent
from seller.engine import EngineConfig
from seller.facts import StoreFacts


def evaluate_parameter_set(
    config: EngineConfig,
    catalog: Dict[str, Any],
    policy: Dict[str, Any],
    facts: StoreFacts,
    runs_per_buyer: int = 15,
    seed: int = 42,
) -> Dict[str, Any]:
    """Runs a representative batch of negotiations for a specific parameter configuration."""
    random.seed(seed)
    
    buyer_personas = [
        ("cooperative_starter", lambda: CooperativeStarterBuyer()),
        ("linear_starter", lambda: LinearStarterBuyer()),
        ("tough_starter", lambda: ToughStarterBuyer()),
        ("cooperative_llm", lambda: CooperativeLLMBuyer(use_simulation=True)),
        ("hard_llm", lambda: HardLLMBuyer(use_simulation=True)),
        ("manipulator_llm", lambda: ManipulatorLLMBuyer(use_simulation=True)),
        ("injector_llm", lambda: InjectorLLMBuyer(use_simulation=True)),
    ]
    
    active_skus = [s for s, data in catalog.items() if data["stock"] > 0]
    
    total_negotiations = 0
    deals_closed = 0
    total_margin_kept = 0.0
    total_violations = 0
    total_rounds = 0
    
    for persona_name, buyer_factory in buyer_personas:
        for i in range(runs_per_buyer):
            sku = random.choice(active_skus)
            qty = random.choices([1, 2, 3, 5], weights=[0.5, 0.25, 0.15, 0.10])[0]
            
            sku_info = catalog[sku]
            list_price = sku_info["list_price"]
            cost = sku_info["cost"]
            
            buyer = buyer_factory()
            seller = SellerAgent(facts=facts, config=config, no_llm=True)
            
            transcript = run_single_negotiation(
                seller_agent=seller,
                buyer_agent=buyer,
                sku=sku,
                qty=qty,
                list_price=list_price,
                cost=cost,
                buyer_persona=persona_name,
                seller_type="vaultline_tuned",
                max_rounds=10,
            )
            
            violations = audit_transcript(transcript, catalog, policy)
            total_negotiations += 1
            total_rounds += transcript.rounds
            
            if violations:
                total_violations += len(violations)
                
            if transcript.closed and not violations and transcript.agreed_price is not None:
                deals_closed += 1
                prod = catalog[sku]
                cost = prod["cost"]
                agreed_p = transcript.agreed_price
                margin = (agreed_p - cost) / agreed_p if agreed_p > 0 else 0.0
                total_margin_kept += margin
                
    deal_rate = deals_closed / total_negotiations if total_negotiations > 0 else 0.0
    mean_margin_kept = total_margin_kept / deals_closed if deals_closed > 0 else 0.0
    avg_rounds = total_rounds / total_negotiations if total_negotiations > 0 else 0.0
    
    # Utility = DealRate * MeanMarginKept (0 if any policy violations exist)
    if total_violations > 0:
        utility = 0.0
    else:
        utility = deal_rate * mean_margin_kept
        
    return {
        "beta": config.beta,
        "gamma": config.target_ratio,
        "rho": config.reciprocity_weight,
        "total_negotiations": total_negotiations,
        "deals_closed": deals_closed,
        "deal_rate": deal_rate,
        "mean_margin_kept": mean_margin_kept,
        "utility": utility,
        "violations": total_violations,
        "avg_rounds": avg_rounds,
    }


def run_grid_search(
    runs_per_buyer: int = 15,
    output_csv: Path = Path("outputs/grid_search_results.csv"),
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Sweeps over hyperparameter grid and saves results."""
    root_dir = Path(__file__).resolve().parent.parent
    catalog = load_catalog(root_dir / "data" / "store.csv")
    policy = load_policy(root_dir / "data" / "policy.json")
    facts = StoreFacts()
    
    beta_values = [1.2, 1.5, 1.8, 2.2]
    gamma_values = [0.15, 0.22, 0.30, 0.38]
    rho_values = [0.10, 0.20, 0.30]
    
    combinations = list(itertools.product(beta_values, gamma_values, rho_values))
    print(f"=== Starting Grid Search ({len(combinations)} configurations, {runs_per_buyer} runs/buyer each) ===")
    
    results = []
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    for idx, (b, g, r) in enumerate(combinations, start=1):
        cfg = EngineConfig(beta=b, target_ratio=g, reciprocity_weight=r)
        metrics = evaluate_parameter_set(
            config=cfg,
            catalog=catalog,
            policy=policy,
            facts=facts,
            runs_per_buyer=runs_per_buyer,
        )
        results.append(metrics)
        print(
            f"[{idx:02d}/{len(combinations)}] beta={b:.1f}, gamma={g:.2f}, rho={r:.2f} -> "
            f"DealRate: {metrics['deal_rate']:.1%}, MarginKept: {metrics['mean_margin_kept']:.1%}, "
            f"Utility: {metrics['utility']:.4f}, Violations: {metrics['violations']}"
        )
        
    duration = time.time() - start_time
    print(f"Grid search completed in {duration:.1f}s")
    
    # Sort results by utility descending (only zero violations considered)
    valid_results = [r for r in results if r["violations"] == 0]
    valid_results.sort(key=lambda x: x["utility"], reverse=True)
    best_config = valid_results[0]
    
    # Save CSV
    fieldnames = [
        "beta", "gamma", "rho", "total_negotiations", "deals_closed",
        "deal_rate", "mean_margin_kept", "utility", "violations", "avg_rounds"
    ]
    with open(output_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)
            
    print("\n" + "=" * 60)
    print(f"OPTIMAL CONFIGURATION FOUND:")
    print(f"  beta (Concession Exponent): {best_config['beta']}")
    print(f"  gamma (Target Surplus):     {best_config['gamma']}")
    print(f"  rho (Reciprocity Weight):   {best_config['rho']}")
    print(f"  Deal Rate:                  {best_config['deal_rate']:.2%}")
    print(f"  Mean Margin Kept:           {best_config['mean_margin_kept']:.2%}")
    print(f"  Utility:                    {best_config['utility']:.4f}")
    print(f"  Violations:                 {best_config['violations']}")
    print("=" * 60)
    
    return best_config, results


if __name__ == "__main__":
    run_grid_search(runs_per_buyer=15)
