---
name: csv_analyzer
description: Deterministic Python-based EDA (exploratory data analysis) for tabular files. ALWAYS use this skill FIRST when the user attaches a .csv / .tsv / .xlsx / .xls file or asks for dataset summary / statistics / "what's in this data" / "看一下这个数据" / "分析一下" / "帮我看看". Produces a structured markdown report with shape, dtypes, missing values, numeric summary, and top categorical values in ~1 second with zero encoding guesswork.
metadata:
  openclaw:
    requires:
      bins:
        - python
---

# CSV Analyzer

**Deterministic, fast EDA for tabular files.** Handles encoding (utf-8 / utf-8-sig / gbk / latin-1) transparently — no encoding surprises on Chinese CSVs.

## When to INVOKE (strong trigger)

**ALWAYS run this skill FIRST, before writing any custom pandas code**, when ANY of these happen:

- User attaches a `.csv`, `.tsv`, `.xlsx`, or `.xls` file (any size)
- User says: "帮我看看", "分析一下", "what's in this data", "summarize this file", "give me EDA", "看一下这个数据", "describe this dataset"
- User pastes a file path and asks for statistics / overview

Don't hand-write pandas code before trying the skill. The skill already:
- Falls back through utf-8 / utf-8-sig / gbk / latin-1 encodings (solves the Windows + Chinese CSV encoding hell)
- Prints deterministic, well-formatted markdown
- Is idempotent and fast (~1s for files under 100k rows)

## When NOT to invoke

- Non-tabular files (plain text, JSON, images, PDFs)
- User asks for a **specific transformation** (e.g., "merge these two files", "train a model", "plot X vs Y") — in that case, go freestyle with `exec` + pandas
- User explicitly says "don't use the analyzer" / "write custom code"

## How to run

Use the `exec` / shell tool. The skill is located at `{SKILL_DIR}` (OpenClaw provides this env var).

```bash
python "{SKILL_DIR}/scripts/analyze.py" "<file_path>"
```

Flags:
- `--top N` — top N categorical values per column (default 5)

**Windows note**: OpenClaw's Discord channel downloads attachments to a temp directory. The `<file_path>` is provided in the message context as an absolute path. **Quote both paths** because Windows paths contain spaces.

**Concrete example on Windows**:
```powershell
python "C:\Users\shenc\.openclaw\workspace\skills\csv_analyzer\scripts\analyze.py" "C:\path\to\downloaded\file.csv"
```

The script prints a markdown report to stdout. No LLM inside, no external calls.

## After running — how to reply to the user

The script output contains:
- **Shape**: rows × columns
- **Columns table**: dtype, missing count + %, unique count
- **Numeric summary**: mean / std / min / median / max
- **Categorical — top N**: top values per object/string column

**Read the full stdout, then write a chat-friendly reply in 3 parts:**

1. **Headline (1 sentence)**: size + overall domain guess
   > "这是一份 5 万行 × 24 列的全球订单数据，主要字段是销售、利润、地区、客户类型。"
2. **Key findings (2-4 bullets)**: focus on **anomalies and useful patterns**, not just restating numbers
   - High missing %: `"PoolQC 99.5% 缺失——这列基本没数据，建议直接丢弃"`
   - Dominant category: `"Consumer 占了 52% 客户订单"`
   - Extreme numeric range: `"SalePrice 从 $34.9k 到 $755k，跨度 20 倍，后续建模要考虑分段或对数变换"`
3. **One follow-up suggestion** — what's the natural next slice?
   > "要不要我按 region 拆一下各类别的利润率？"

**Don't** paste the raw tables back into Discord. Discord has no table rendering. Summarize in bullets.

**Don't** invent numbers. If the script stdout doesn't mention something (e.g., time trends, deep correlations), don't claim it. You can say "要看时间趋势的话我再跑一轮专门的分析" and wait for user confirmation.

## If the script fails

Rare cases:
- File not found → double-check the absolute path in message context
- Encoding totally unsupported (neither utf-8/gbk/latin-1 works) → fall back to freestyle `exec` with explicit encoding guess
- Multi-sheet xlsx → script reads only the first sheet; if user needs others, freestyle

**Always report the error** to the user before guessing / summarizing. Don't hallucinate an analysis when the script failed — that's what caused the embarrassing behavior before.

## Example end-to-end (Discord)

User drags `sales.csv` into Discord with message `@bot 帮我看看`.

1. You run:
   ```bash
   python "C:\Users\shenc\.openclaw\workspace\skills\csv_analyzer\scripts\analyze.py" "C:\Temp\openclaw-attachments\sales.csv"
   ```
2. Script prints report (markdown) to stdout.
3. You reply:

   > 这是份 1 万行 × 8 列的销售记录，时间跨度 2020-2024。
   > - `discount` 列缺失 12%，看上去是"无折扣订单不写字段"的习惯
   > - `category` 只有 5 种，Furniture 一家占了近一半
   > - `price` 从 $3 到 $2,499，分布偏斜很厉害
   >
   > 要不要我按 category 拆一下销售额和利润率？
