"""Shared helpers for the exploratory scripts: paths, data loading, monochrome style."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from config import PROCESSED, RAW  # noqa: E402,F401

FIG = ROOT / "eda" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

INK, MID, LIGHT = "#111111", "#777777", "#d0d0d0"
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": INK, "axes.labelcolor": INK, "axes.titleweight": "bold", "axes.titlesize": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True,
    "grid.color": "#ececec", "grid.linewidth": 0.6,
    "xtick.color": INK, "ytick.color": INK, "image.cmap": "Greys",
    "axes.prop_cycle": matplotlib.cycler(color=[INK, MID, LIGHT]),
})


def trips(cols=None) -> pd.DataFrame:
    t = pd.read_parquet(PROCESSED / "trips_clean.parquet", columns=None if cols is None else cols + ["valid"])
    return t[t.valid].drop(columns="valid")


def save(fig, name: str) -> None:
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)
    print("saved", f"eda/figures/{name}.png")
