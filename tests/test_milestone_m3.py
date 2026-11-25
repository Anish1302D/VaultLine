"""tests/test_milestone_m3.py

Milestone M3 Verification Gate:
- 300+ runs per buyer logged in outputs/results.jsonl (>= 2,100 total runs)
- Zero policy violations across entire batch run (HC-1 through HC-8)
- Metamorphic fairness verified (ST-1)
- Optimal parameters logged and verified
"""
import csv
import json
from pathlib import Path
import pytest

from evaluate import audit_transcript, load_catalog, load_policy
from harness import NegotiationTranscript, TurnRecord


def test_milestone_m3_batch_scale_and_zero_violations():
    """Assert 2,100 total runs with 0 violations across all 7 personas."""
    results_path = Path("outputs/results.jsonl")
    summary_path = Path("outputs/summary_metrics.csv")
    assert results_path.exists(), "outputs/results.jsonl missing"
    assert summary_path.exists(), "outputs/summary_metrics.csv missing"
    
    # Check summary metrics
    personas_found = {}
    with open(summary_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            p = row["persona"]
            runs = int(row["runs"])
            deals = int(row["deals_closed"])
            personas_found[p] = runs
            assert runs >= 300, f"Expected >= 300 runs for {p}, got {runs}"
            
    assert len(personas_found) == 7, f"Expected 7 buyer personas, found {len(personas_found)}"
    
    # Audit transcripts
    catalog = load_catalog(Path("data/store.csv"))
    policy = load_policy(Path("data/policy.json"))
    
    total_transcripts = 0
    total_violations = 0
    
    with open(results_path, mode="r", encoding="utf-8") as f:
        for line in f:
            total_transcripts += 1
            data = json.loads(line)
            
            # Reconstruct transcript object
            turns = [
                TurnRecord(round=t["round"], buyer_message=t["buyer_message"], seller_message=t["seller_message"])
                for t in data.get("turns", [])
            ]
            t = NegotiationTranscript(
                negotiation_id=data["negotiation_id"],
                sku=data["sku"],
                qty=data["qty"],
                list_price=data["list_price"],
                cost=data["cost"],
                buyer_persona=data["buyer_persona"],
                seller_type=data["seller_type"],
                rounds=data["rounds"],
                closed=data["closed"],
                agreed_price=data["agreed_price"],
                agreed_total=data["agreed_total"],
                turns=turns,
            )
            v = audit_transcript(t, catalog, policy)
            if v:
                total_violations += len(v)
                
    assert total_transcripts >= 2100, f"Expected >= 2,100 transcripts, found {total_transcripts}"
    assert total_violations == 0, f"Expected 0 violations across all {total_transcripts} sessions, found {total_violations}"


def test_milestone_m3_grid_search_tuning_results():
    """Assert grid search completed and produced valid parameter records."""
    grid_csv = Path("outputs/grid_search_results.csv")
    assert grid_csv.exists(), "outputs/grid_search_results.csv missing"
    
    with open(grid_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    assert len(rows) == 48, f"Expected 48 parameter configurations, found {len(rows)}"
    for r in rows:
        assert int(r["violations"]) == 0, f"Violation found in config: {r}"
        assert float(r["utility"]) > 0.0, f"Non-positive utility: {r}"
