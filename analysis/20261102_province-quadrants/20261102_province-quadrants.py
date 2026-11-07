from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts

import json

import pandas as pd

# Parameters

DATASET = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
METADATA = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population-metadata.json"

OUT_WEALTH_PNG = HERE / "20261102_wealth-vs-momentum.png"
OUT_WEALTH_CSV = HERE / "20261102_wealth-vs-momentum.csv"

# Functions

def load():
    """Read the dataset and the province names from its metadata."""
    df = pd.read_csv(DATASET, dtype={"province_code": str, "sector": str, "period": str, "status": str},
                     keep_default_na=False)
    meta = json.loads(METADATA.read_text(encoding="utf-8"))
    names = {code: charts.display_name(p["name"]) for code, p in meta["provinces"].items()}
    return df, names


# Steps

# Read the dataset
df, names = load()

# Plot 1: GRDP per capita 2025 against nominal GRDP growth 2024-2025, for all 38 provinces
grdp = df[(df["indicator"] == "grdp_current") & (df["sector"] == "TOTAL")].pivot(index="province_code", columns="period", values="value")
pop = df[df["indicator"] == "population"].pivot(index="province_code", columns="period", values="value")
provs = grdp.index[grdp["2024"].notna() & grdp["2025"].notna()]
wealth = pd.DataFrame({
    "province_code": provs,
    "province": [names[c] for c in provs],
    "grdp_per_capita_2025": (grdp.loc[provs, "2025"] / pop.loc[provs, "2025"]).values,
    "grdp_growth_2025_pct": ((grdp.loc[provs, "2025"] / grdp.loc[provs, "2024"] - 1) * 100).values,
})
assert len(wealth) == 38

# Cut at the national values: provincial GRDP summed over Indonesia's population, and growth of that sum
x_cut = grdp["2025"].sum() / pop.loc["00", "2025"]
y_cut = (grdp["2025"].sum() / grdp["2024"].sum() - 1) * 100
names_q = {(True, True): "Rich & fast", (True, False): "Rich & slowing",
           (False, True): "Catching up", (False, False): "Lagging"}
wealth["quadrant"] = [names_q[(a >= x_cut, b >= y_cut)]
                      for a, b in zip(wealth["grdp_per_capita_2025"], wealth["grdp_growth_2025_pct"])]

# Write the table behind the chart
wealth.sort_values(["quadrant", "grdp_per_capita_2025"], ascending=[True, False]).to_csv(
    OUT_WEALTH_CSV, index=False, float_format="%.2f", lineterminator="\n")

# Draw the chart with the shared quadrant chart, without a footnote. Caveats kept here instead: GRDP is at
# current prices, so growth includes inflation and commodity prices; 2025 is very preliminary (**) and 2024
# preliminary (*); the Indonesia line sums provincial GRDP, which BPS does not reconcile with national GDP
charts.quadrant_chart(
    wealth, "grdp_per_capita_2025", "grdp_growth_2025_pct", x_cut, y_cut, names_q,
    xlabel="GRDP per capita, 2025 (Rp million per person, log scale)",
    ylabel="Nominal GRDP growth, 2024 to 2025 (%)",
    title="Wealth vs momentum: Indonesian provinces, 2025",
    subtitle="GRDP per capita against GRDP growth; lines mark the Indonesia-wide values",
    note=None,
    path=OUT_WEALTH_PNG, logx=True, ylim=(2.5, 12), yunit="%",
)
print(wealth["quadrant"].value_counts().to_string())
