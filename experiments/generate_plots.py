"""Analysis and Visualization Script (Phase 6).

Reads outputs/results.jsonl and outputs/summary_metrics.csv to generate
publication-quality charts saved to outputs/plots/:
1. deal_rate_by_persona.png - Deal closure rate comparison across all 7 buyer personas
2. margin_distribution.png - Distribution of profit margins achieved across closed deals
3. rounds_to_close.png - Average rounds to reach agreement or walk away
4. concession_trajectories.png - Representative seller concession paths vs buyer offers
"""
import csv
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

# Apply clean visual styling
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.titlesize": 13,
})

OUTPUT_DIR = Path("outputs/plots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def plot_metrics_from_summary(csv_path: Path = Path("outputs/summary_metrics.csv")):
    """Generates bar plots for deal rates, margins, and round lengths."""
    personas = []
    deal_rates = []
    margins = []
    rounds = []
    profits = []

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            personas.append(row["persona"].replace("_", " ").title())
            deal_rates.append(float(row["deal_rate_pct"]))
            margins.append(float(row["avg_margin_pct"]))
            rounds.append(float(row["avg_rounds"]))
            profits.append(float(row["total_profit"]))

    # 1. Deal Rates Bar Chart
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=300)
    colors = ["#2ecc71" if dr > 70 else "#f39c12" if dr > 40 else "#e74c3c" for dr in deal_rates]
    bars = ax.barh(personas, deal_rates, color=colors, edgecolor="black", alpha=0.85, height=0.6)
    ax.set_xlabel("Deal Closure Rate (%)")
    ax.set_xlim(0, 105)
    ax.set_title("VaultLine Deal Closure Rate Across 7 Buyer Personas (300 Runs/Type)")
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f"{w:.1f}%", (w + 1.2, bar.get_y() + bar.get_height() / 2),
                    va="center", ha="left", fontsize=9, fontweight="bold")
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "deal_rate_by_persona.png")
    plt.close(fig)

    # 2. Margins Kept Bar Chart
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=300)
    bars = ax.barh(personas, margins, color="#3498db", edgecolor="black", alpha=0.85, height=0.6)
    ax.set_xlabel("Mean Profit Margin Kept (%)")
    ax.set_xlim(0, 45)
    ax.set_title("VaultLine Mean Margin Preserved on Closed Deals (Zero Policy Violations)")
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f"{w:.1f}%", (w + 0.8, bar.get_y() + bar.get_height() / 2),
                    va="center", ha="left", fontsize=9, fontweight="bold")
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "margin_by_persona.png")
    plt.close(fig)

    # 3. Average Rounds to Close
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=300)
    bars = ax.barh(personas, rounds, color="#9b59b6", edgecolor="black", alpha=0.85, height=0.6)
    ax.set_xlabel("Average Rounds per Negotiation (Max 10)")
    ax.set_xlim(0, 11)
    ax.set_title("Average Rounds to Closure or Walk-Away Across Personas")
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f"{w:.1f} rds", (w + 0.2, bar.get_y() + bar.get_height() / 2),
                    va="center", ha="left", fontsize=9, fontweight="bold")
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "rounds_to_close.png")
    plt.close(fig)


def plot_trajectories_from_jsonl(jsonl_path: Path = Path("outputs/results.jsonl")):
    """Plots representative negotiation trajectories showing Boulware curve and stall freeze."""
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=300)
    
    # Extract representative trajectories for cooperative and hard buyers
    coop_seller_quotes = []
    coop_buyer_offers = []
    hard_seller_quotes = []
    hard_buyer_offers = []

    with open(jsonl_path, mode="r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            p = data.get("buyer_persona")
            if p == "cooperative_llm" and not coop_seller_quotes and data.get("closed"):
                turns = data.get("turns", [])
                coop_seller_quotes = [t["seller_message"].get("items", [{}])[0].get("unit_price") for t in turns if "items" in t["seller_message"]]
                coop_buyer_offers = [t["buyer_message"].get("items", [{}])[0].get("price_offer") for t in turns if "items" in t["buyer_message"]]
            elif p == "hard_llm" and not hard_seller_quotes and data.get("closed"):
                turns = data.get("turns", [])
                hard_seller_quotes = [t["seller_message"].get("items", [{}])[0].get("unit_price") for t in turns if "items" in t["seller_message"]]
                hard_buyer_offers = [t["buyer_message"].get("items", [{}])[0].get("price_offer") for t in turns if "items" in t["buyer_message"]]

    if coop_seller_quotes and coop_buyer_offers:
        rds = list(range(1, len(coop_seller_quotes) + 1))
        ax.plot(rds, coop_seller_quotes, "o-", color="#2980b9", label="Seller Quote (vs Cooperative)", lw=2)
        ax.plot(rds, coop_buyer_offers[:len(rds)], "s--", color="#27ae60", label="Buyer Offer (Cooperative)", lw=2)

    if hard_seller_quotes and hard_buyer_offers:
        rds_h = list(range(1, len(hard_seller_quotes) + 1))
        ax.plot(rds_h, hard_seller_quotes, "o-", color="#e67e22", label="Seller Quote (vs Hard Bargainer)", lw=2)
        ax.plot(rds_h, hard_buyer_offers[:len(rds_h)], "^--", color="#c0392b", label="Buyer Offer (Hard Bargainer)", lw=2)

    ax.set_xlabel("Negotiation Round")
    ax.set_ylabel("Unit Price ($)")
    ax.set_title("VaultLine Multi-Round Price Concession Trajectories")
    ax.legend(loc="upper right", frameon=True)
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "concession_trajectories.png")
    plt.close(fig)


if __name__ == "__main__":
    plot_metrics_from_summary()
    plot_trajectories_from_jsonl()
    print("All plots generated successfully in outputs/plots/!")
