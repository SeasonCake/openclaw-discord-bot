#!/usr/bin/env python3
"""Deterministic EDA chart generator for tabular files.

Generates a multi-panel PNG with:
  - Missing-value overview
  - Numeric distributions (non-binary columns)
  - One-hot group bars (auto-detected by shared prefix + binary values)
  - Categorical top-N bars (object/string columns)
  - Correlation heatmap (numeric only, if 3+ numeric cols)

Designed to be called by the csv_analyzer skill. Pure matplotlib/seaborn,
no LLM, no network. CJK-font-safe on Windows (Microsoft YaHei / SimHei).

Usage:
    python plot.py <file_path> [--output PATH] [--top N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

PALETTES = ["Set2", "Set3", "Pastel1", "Paired", "tab10", "Dark2"]


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    sep = "\t" if suffix == ".tsv" else ","
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return pd.read_csv(path, sep=sep, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path} with utf-8 / gbk / latin-1")


def detect_onehot_groups(df: pd.DataFrame, min_group_size: int = 3) -> dict[str, list[str]]:
    """Group one-hot columns by the prefix before the last '_'."""
    groups: dict[str, list[str]] = {}
    for col in df.columns:
        if "_" not in col:
            continue
        prefix = col.rsplit("_", 1)[0]
        series = df[col].dropna()
        if series.empty:
            continue
        if series.isin([0, 1]).all():
            groups.setdefault(prefix, []).append(col)
    return {p: cols for p, cols in groups.items() if len(cols) >= min_group_size}


def non_binary_numeric(df: pd.DataFrame, onehot_groups: dict[str, list[str]]) -> list[str]:
    onehot_cols = {c for cols in onehot_groups.values() for c in cols}
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    return [c for c in numeric_cols if c not in onehot_cols and df[c].nunique(dropna=True) > 2]


def plot_missing(ax, df: pd.DataFrame) -> None:
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=True)
    if missing.empty:
        ax.text(
            0.5,
            0.5,
            "无缺失值",
            ha="center",
            va="center",
            fontsize=18,
            fontweight="bold",
            transform=ax.transAxes,
            color="#2a9d8f",
        )
        ax.set_title("缺失值检查", fontsize=11, fontweight="bold")
        ax.axis("off")
        return
    colors = sns.color_palette("Reds_r", len(missing))
    ax.barh(missing.index.astype(str), missing.values, color=colors, edgecolor="white")
    ax.set_title("缺失值计数", fontsize=11, fontweight="bold")
    ax.set_xlabel("缺失条数", fontsize=9)
    ax.grid(axis="x", alpha=0.3)


def plot_numeric_dist(ax, df: pd.DataFrame, col: str, palette: str) -> None:
    data = df[col].dropna()
    color = sns.color_palette(palette)[0]
    ax.hist(data, bins=20, color=color, edgecolor="white", alpha=0.9)
    ax.axvline(data.mean(), color="#e76f51", linestyle="--", linewidth=1.5, label=f"均值 {data.mean():.1f}")
    ax.axvline(data.median(), color="#264653", linestyle=":", linewidth=1.5, label=f"中位 {data.median():.1f}")
    ax.set_title(f"{col} 分布", fontsize=11, fontweight="bold")
    ax.set_xlabel(col, fontsize=9)
    ax.set_ylabel("频次", fontsize=9)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(axis="y", alpha=0.3)


def plot_onehot_group(
    ax,
    df: pd.DataFrame,
    prefix: str,
    cols: list[str],
    palette: str,
    top_n: int,
) -> None:
    counts = df[cols].sum().sort_values(ascending=False).head(top_n).sort_values(ascending=True)
    labels = [c.replace(f"{prefix}_", "") for c in counts.index]
    colors = sns.color_palette(palette, len(counts))
    ax.barh(labels, counts.values, color=colors, edgecolor="white")
    suffix_label = "" if len(cols) <= top_n else f"（Top {top_n}/{len(cols)}）"
    ax.set_title(f"{prefix} 分布（one-hot）{suffix_label}", fontsize=11, fontweight="bold")
    ax.set_xlabel("计数", fontsize=9)
    ax.grid(axis="x", alpha=0.3)


def plot_categorical_top(ax, df: pd.DataFrame, col: str, top_n: int, palette: str) -> None:
    vc = df[col].value_counts().head(top_n)
    colors = sns.color_palette(palette, len(vc))
    ax.barh(vc.index.astype(str)[::-1], vc.values[::-1], color=colors[::-1], edgecolor="white")
    unique_total = df[col].nunique()
    suffix_label = "" if unique_total <= top_n else f"（Top {top_n}/{unique_total}）"
    ax.set_title(f"{col} 分布 {suffix_label}", fontsize=11, fontweight="bold")
    ax.set_xlabel("计数", fontsize=9)
    ax.grid(axis="x", alpha=0.3)


def plot_corr_heatmap(ax, df: pd.DataFrame, cols: list[str]) -> None:
    corr = df[cols].corr()
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        ax=ax,
        cbar_kws={"shrink": 0.7},
        annot_kws={"size": 8},
        linewidths=0.5,
        linecolor="white",
    )
    ax.set_title("数值列相关性", fontsize=11, fontweight="bold")


def build_plots(df: pd.DataFrame, output: Path, top_n: int) -> dict:
    onehot_groups = detect_onehot_groups(df)
    numeric_cols = non_binary_numeric(df, onehot_groups)
    cat_cols = list(df.select_dtypes(include=["object", "category", "string"]).columns)

    panels: list[tuple[str, object]] = [("missing", None)]
    for col in numeric_cols[:4]:
        panels.append(("numeric_dist", col))
    for prefix, cols in list(onehot_groups.items())[:4]:
        panels.append(("onehot", (prefix, cols)))
    for col in cat_cols[:3]:
        panels.append(("cat", col))
    if len(numeric_cols) >= 3:
        panels.append(("corr", numeric_cols[:10]))

    n = len(panels)
    if n == 0:
        raise ValueError("数据列太单一，没有可画的内容（既无数值列也无分类列）")

    n_cols = min(3, n)
    n_rows = (n + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 5.2, n_rows * 4.3))
    axes = np.atleast_1d(axes).flatten()

    for i, (kind, payload) in enumerate(panels):
        ax = axes[i]
        palette = PALETTES[i % len(PALETTES)]
        if kind == "missing":
            plot_missing(ax, df)
        elif kind == "numeric_dist":
            assert isinstance(payload, str)
            plot_numeric_dist(ax, df, payload, palette)
        elif kind == "onehot":
            prefix, cols = payload  # type: ignore[misc]
            plot_onehot_group(ax, df, prefix, cols, palette, top_n)
        elif kind == "cat":
            assert isinstance(payload, str)
            plot_categorical_top(ax, df, payload, top_n, palette)
        elif kind == "corr":
            assert isinstance(payload, list)
            plot_corr_heatmap(ax, df, payload)

    for j in range(n, len(axes)):
        axes[j].axis("off")

    fig.suptitle(
        f"EDA — {df.shape[0]:,} 行 × {df.shape[1]} 列",
        fontsize=15,
        fontweight="bold",
        y=1.003,
    )
    fig.tight_layout()
    fig.savefig(output, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return {
        "onehot_groups": list(onehot_groups.keys()),
        "numeric_cols": numeric_cols,
        "categorical_cols": cat_cols[:3],
        "panel_count": n,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic EDA chart generator.")
    parser.add_argument("file", type=Path, help="Path to .csv / .tsv / .xlsx / .xls")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output PNG path. Default: <input_stem>_eda.png next to input.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=8,
        help="Top N categories per bar chart (default 8)",
    )
    args = parser.parse_args()

    if not args.file.exists():
        sys.exit(f"File not found: {args.file}")

    output = args.output or args.file.with_name(f"{args.file.stem}_eda.png")

    df = load_table(args.file)
    info = build_plots(df, output, args.top)

    print(f"EDA 图表生成完毕")
    print(f"  - 数据规模：{df.shape[0]:,} 行 × {df.shape[1]} 列")
    print(f"  - 面板数：{info['panel_count']}")
    if info["onehot_groups"]:
        shown = info["onehot_groups"][:4]
        extra = len(info["onehot_groups"]) - len(shown)
        suffix = f"（还有 {extra} 组未画）" if extra > 0 else ""
        print(f"  - 识别到 {len(info['onehot_groups'])} 组 one-hot 编码：{', '.join(shown)}{suffix}")
    if info["numeric_cols"]:
        shown = info["numeric_cols"][:4]
        extra = len(info["numeric_cols"]) - len(shown)
        suffix = f"（+{extra} 列未画）" if extra > 0 else ""
        print(f"  - 连续数值列（前 4）：{', '.join(shown)}{suffix}")


if __name__ == "__main__":
    main()
