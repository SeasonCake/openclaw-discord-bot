#!/usr/bin/env python3
"""CSV / TSV / Excel analyzer — prints a markdown EDA report to stdout.

Usage:
    python analyze.py <file_path> [--top N]

Designed to be called by an OpenClaw skill. Pure pandas, no LLM, no network.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def load_table(path: Path) -> pd.DataFrame:
    """Load a CSV/TSV/Excel file, auto-detecting encoding for text formats."""
    suffix = path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)

    sep = "\t" if suffix == ".tsv" else ","
    # Try common encodings; GBK is common for CSVs exported from Chinese tools.
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return pd.read_csv(path, sep=sep, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path} with utf-8/gbk/latin-1")


def column_overview(df: pd.DataFrame) -> str:
    rows = len(df)
    records = []
    for col in df.columns:
        missing = int(df[col].isna().sum())
        pct = (missing / rows * 100) if rows else 0.0
        records.append(
            {
                "column": col,
                "dtype": str(df[col].dtype),
                "missing": f"{missing} ({pct:.1f}%)",
                "unique": int(df[col].nunique(dropna=True)),
            }
        )
    return pd.DataFrame(records).to_markdown(index=False)


def numeric_summary(df: pd.DataFrame) -> str | None:
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return None
    stats = numeric.describe().T[["mean", "std", "min", "50%", "max"]].round(2)
    stats = stats.rename(columns={"50%": "median"})
    return stats.to_markdown()


def categorical_top(df: pd.DataFrame, top_n: int) -> str | None:
    cat = df.select_dtypes(include=["object", "category", "str"])
    if cat.empty:
        return None
    chunks: list[str] = []
    for col in cat.columns:
        vc = df[col].value_counts().head(top_n)
        chunks.append(f"\n**{col}** ({df[col].nunique()} unique)")
        for val, count in vc.items():
            chunks.append(f"- `{val}`: {count}")
    return "\n".join(chunks)


def analyze(df: pd.DataFrame, top_n: int = 5) -> str:
    rows, cols = df.shape
    parts: list[str] = [f"**Shape:** {rows:,} rows × {cols} columns", "\n## Columns\n", column_overview(df)]

    numeric = numeric_summary(df)
    if numeric:
        parts.extend(["\n## Numeric summary\n", numeric])

    cat = categorical_top(df, top_n)
    if cat:
        parts.extend([f"\n## Categorical — top {top_n} values", cat])

    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick EDA for tabular files.")
    parser.add_argument("file", type=Path, help="Path to .csv, .tsv, .xlsx, or .xls")
    parser.add_argument("--top", type=int, default=5, help="Top N categorical values per column")
    args = parser.parse_args()

    if not args.file.exists():
        sys.exit(f"File not found: {args.file}")

    df = load_table(args.file)
    print(f"# EDA Report — {args.file.name}\n")
    print(analyze(df, top_n=args.top))


if __name__ == "__main__":
    main()
