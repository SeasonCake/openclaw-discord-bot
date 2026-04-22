---
name: csv_analyzer
description: Deterministic Python-based EDA (exploratory data analysis) for tabular files. ALWAYS use this skill when the user attaches a .csv / .tsv / .xlsx / .xls file or asks for dataset summary / statistics / EDA charts / visualization / "what's in this data" / "看一下这个数据" / "分析一下" / "帮我看看" / "画图" / "可视化" / "生成图表". Produces (a) structured markdown EDA report via analyze.py and (b) multi-panel PNG chart via plot.py, both deterministic, CJK-font-safe, and run in ~2 seconds with zero encoding guesswork and zero LLM-generated matplotlib code.
metadata:
  openclaw:
    requires:
      bins:
        - python
---

# CSV Analyzer

**Deterministic, fast EDA + visualization for tabular files.** Handles encoding (utf-8 / utf-8-sig / gbk / latin-1) transparently — no encoding surprises on Chinese CSVs. Generates charts with proper CJK fonts and diversified color palettes.

## ⚠️ IRON RULE — NO REASONING TEXT EVER

**You are a silent router. Users must NEVER see your reasoning, analysis, or meta-commentary about HOW you're using the skill.**

Forbidden output patterns (every one of these was observed in the wild and broke UX):

- ❌ `我来帮你分析这个CSV文件。根据技能描述，我需要使用csv_analyzer技能来处理这个数据集。`
- ❌ `现在我来运行CSV分析脚本。首先需要找到文件的完整路径。根据消息内容，文件路径是 ...`
- ❌ `I'll analyze this CSV file. Let me first check the file path...`
- ❌ `我来为你生成一些EDA图表。我会使用Python的matplotlib和seaborn库来创建可视化图表。`
- ❌ `需要先安装matplotlib和seaborn库。让我先安装这些依赖：`
- ❌ `现在库已经安装好了，让我重新运行图表生成脚本：`
- ❌ `很好！图表已经生成。现在让我发送这个图表给你。由于字体问题，图表中的中文可能显示为乱码...`
- ❌ `由于系统字体问题，图表中的中文标签可能显示为方框或乱码，但图表的数据可视化部分应该清晰可见。`
- ❌ 在 reply 的正文段落里把 PNG 路径**当成叙述内容**再写一次（例如 `图表已保存到 C:\...\xxx_eda.png` 或 `附件路径 C:\...\xxx_eda.png` 写在句子中间当说明文本用）——附件的**唯一合法触发机制**是在 reply 里单独起一行写 `MEDIA:<绝对路径>`（见下文 "Chart request" 章节）。把路径当叙述文本写到正文里**不会**触发第二次上传（那只是文字），但会让用户看到难看的绝对路径；把 `MEDIA:` 写两次或把同一路径既放 `MEDIA:` 又放正文里被 channel 当路径扫到，才会触发二次上传

### ZERO-PREAMBLE RULE

First token must be **either a tool call or the first line of the final reply**. No "Let me...", no "我来帮你...", no "现在我...", no "Based on...".

### ABSOLUTE NO-PIP RULE

**Do NOT `pip install` anything. Ever.** The system already has `pandas`, `matplotlib`, `seaborn`, `numpy`, `openpyxl` installed at the user level. If a script fails with `ModuleNotFoundError`, report the exact error and stop — do NOT attempt to install anything. Installing requires admin context and is not your job.

### ABSOLUTE NO-CUSTOM-MATPLOTLIB RULE

**Do NOT write custom matplotlib / seaborn code to generate charts.** Every time you do this, you produce:
- Chinese characters rendered as `口 口 口` (missing CJK font)
- All bars in the same blue (no palette variation)
- Non-deterministic layouts
- Unpredictable errors

The skill ships `plot.py` which handles all of this correctly. **Call it. Do not improvise.**

### VERBATIM PASTE RULE (for stdout of analyze.py / plot.py)

When the CLI prints text, paste it or summarize it into the structured reply format below. **Never invent stats** that weren't in stdout. If the script didn't compute correlations, you don't mention correlations.

### ERROR RECOVERY RULE

If a script fails (file not found, encoding unsupported, empty stdout, traceback):

1. **Do NOT narrate your diagnosis** ("Hmm, looks like..."). No "Let me check..."
2. **Do NOT retry with a different interpretation** (e.g., don't auto-switch to a custom pandas script)
3. **Paste the last 5 lines of stderr verbatim** + one short line asking user how to proceed

---

## When to INVOKE (strong trigger)

**ALWAYS run this skill FIRST, before writing any custom pandas / matplotlib code**, when ANY of these happen:

- User attaches a `.csv`, `.tsv`, `.xlsx`, or `.xls` file (any size)
- User says: "帮我看看", "分析一下", "what's in this data", "summarize this file", "give me EDA", "看一下这个数据", "describe this dataset"
- User asks for **charts / visualization / 图表 / 画图 / 可视化 / plot / chart / EDA**
- User pastes a file path and asks for statistics / overview

## When NOT to invoke

- Non-tabular files (plain text, JSON, images, PDFs)
- User asks for a **specific transformation** (e.g., "merge these two files", "train a model", "plot only X vs Y") — in that case, go freestyle with `exec` + pandas (but still don't `pip install`)
- User explicitly says "don't use the analyzer" / "write custom code"

## How to run — two commands

The skill ships two scripts at `{SKILL_DIR}/scripts/`:

### 1. `analyze.py` — text EDA report (always run first)

```bash
python "{SKILL_DIR}/scripts/analyze.py" "<file_path>" [--top N]
```

Prints markdown to stdout: shape, column table, numeric summary, categorical top-N. **~1 second.**

### 2. `plot.py` — multi-panel chart (run when user wants charts / 图表 / 可视化)

```bash
python "{SKILL_DIR}/scripts/plot.py" "<file_path>" --output "<output_png_path>" [--top N]
```

Generates `<output_png_path>` with a grid of panels: missing-value overview, numeric distributions (with mean/median markers), one-hot group bars (auto-detected), categorical top-N bars, correlation heatmap. **~2 seconds.** Prints **only a semantic summary** to stdout (panel count, one-hot groups, key numeric cols) — it deliberately does **not** echo the output path to prevent double-attachment. You already know the path from the `--output` arg you passed.

### On Windows

OpenClaw's Discord channel drops attachments at `C:\Users\shenc\.openclaw\media\inbound\<uuid>.<ext>`. **Always quote both paths**:

```powershell
python "C:\Users\shenc\.openclaw\workspace\skills\csv_analyzer\scripts\analyze.py" "C:\Users\shenc\.openclaw\media\inbound\xxx.csv"
python "C:\Users\shenc\.openclaw\workspace\skills\csv_analyzer\scripts\plot.py" "C:\Users\shenc\.openclaw\media\inbound\xxx.csv" --output "C:\Users\shenc\.openclaw\media\inbound\xxx_eda.png"
```

Use the same directory (`inbound`) for output so the Discord channel can resolve the path when attaching.

### ATTACHMENT MECHANISM (important — misread this and you'll send the image twice)

OpenClaw's Discord channel attaches a file to the reply **only when it sees a line in the reply of the form**:

```
MEDIA:<absolute path to the file>
```

(on its own line, no surrounding text, uppercase `MEDIA:` prefix).

It does **NOT** scan tool stdout for paths. It does **NOT** auto-attach every file under `inbound/`. It **only** picks up the `MEDIA:` directive from **your reply**.

Implications:

1. **You must emit exactly one `MEDIA:<path>` line** in the chart reply, using the `--output` path you passed to `plot.py`
2. **Do not emit `MEDIA:<path>` more than once** (not even pointing to the same file — each `MEDIA:` = one upload)
3. Regular text mentions of the path (e.g. `图表保存在 C:\...\xxx.png` as sentence content) are **not** attach triggers — they're just ugly text. Still avoid them for UX, but they're not the bug
4. `plot.py` deliberately does **not** print the output path to stdout (so there's no risk of the channel misinterpreting stdout as a MEDIA directive if behavior ever changes)

---

## How to reply to the user

### Text-only analysis ("帮我看看" / "分析一下" without asking for charts)

Run `analyze.py`, read stdout, **then write a chat-friendly reply in 3 parts**:

1. **Headline (1 sentence)**: size + overall domain guess
   > "这是一份 5 万行 × 24 列的全球订单数据，主要字段是销售、利润、地区、客户类型。"
2. **Key findings (2-4 bullets)**: focus on **anomalies and useful patterns**, not just restating numbers
   - High missing %: `PoolQC 99.5% 缺失——这列基本没数据，建议直接丢弃`
   - Dominant category: `Consumer 占了 52% 客户订单`
   - Extreme numeric range: `SalePrice 从 $34.9k 到 $755k，跨度 20 倍，后续建模要考虑分段或对数变换`
3. **One follow-up**: what's the natural next slice?
   > "要不要我画 EDA 图表，或者按 region 拆一下各类别的利润率？"

Do **NOT** paste the raw tables back into Discord (no table rendering). Summarize in bullets.

### Chart request ("画图" / "可视化" / "生成 EDA 图表")

**Run `plot.py` EXACTLY ONCE.** It's deterministic — never run it again "to be safe". Then write a reply with this exact structure:

```
<1-2 sentence data summary>

<2-4 bullet "key findings" lines, if user also wanted text analysis>

MEDIA:<absolute path to the generated PNG, same as --output arg>

<1 follow-up question>
```

Rules for the `MEDIA:` line:

- **Exactly one** `MEDIA:` line per reply. Not zero (image won't attach), not two (image attaches twice)
- Must start at column 0 of a new line (no leading spaces, no list bullet, no quote marker)
- Path must be the same absolute path you passed to `--output`
- Do **not** wrap it in backticks, quotes, or code fences

Example (✅ correct shape):

```
已生成 10 面板 EDA 图（90 行 × 77 列，识别出 4 组 one-hot 编码：Orbit / LaunchSite / LandingPad / Serial）。载荷质量分布呈双峰（轻载 <2000kg 和重载 >10000kg），Block 与 FlightNumber 相关性 0.93。

MEDIA:C:\Users\shenc\.openclaw\media\inbound\b4c90b0e-..._eda.png

要看哪一块的细节？比如 payload 随时间趋势，或者不同 orbit 的载荷分布？
```

Anti-patterns (each one observed + broke UX):

- ❌ Running `plot.py` twice "to be safe" — deterministic, wastes tokens, no benefit
- ❌ Writing the path twice (once as `MEDIA:<path>` and once again as sentence content like `图表保存在 C:\...\xxx_eda.png`) — the second mention doesn't trigger upload but looks ugly. Just use `MEDIA:` once.
- ❌ Emitting the `MEDIA:` line twice pointing to the same file — **this does trigger double upload** (each `MEDIA:` line is one attach)
- ❌ Adding FUD like "图中中文可能显示为方框" — `plot.py` handles CJK correctly, don't pre-apologize
- ❌ Mentioning `pip install` or font issues — skill handles everything

---

## If a script fails

Rare cases:

| Symptom | Correct action |
|---|---|
| `File not found: ...` | Reply one line: "找不到文件 `<path>`。你确认这是最新附件吗？" |
| `Could not decode ... with utf-8 / gbk / latin-1` | Reply: "文件编码不是 utf-8/gbk/latin-1，发我原始二进制前 200 字节我看看。" |
| `ModuleNotFoundError: No module named '<x>'` | Reply: "系统缺 `<x>`，需要先装一下（用户级：`pip install --user <x>`）。装完告诉我。" **不要自己装** |
| Empty stdout | Reply: "脚本没输出任何东西，可能文件是空的。确认一下？" |
| Other traceback | Paste **last 5 lines** verbatim + "脚本炸了，我先记下这个 bug" |

**Always report the error** before guessing / summarizing. Don't hallucinate analysis when the script failed.

---

## Example end-to-end (Discord)

User drags `sales.csv` into Discord with `@bot 帮我看看并画图`.

1. Run text analysis:
   ```bash
   python ".../analyze.py" "C:\...\inbound\sales.csv"
   ```
2. Run chart generation:
   ```bash
   python ".../plot.py" "C:\...\inbound\sales.csv" --output "C:\...\inbound\sales_eda.png"
   ```
3. Reply:

   > 这是份 1 万行 × 8 列的销售记录，时间跨度 2020-2024。
   > - `discount` 列缺失 12%，看上去是"无折扣订单不写字段"的习惯
   > - `category` 只有 5 种，Furniture 一家占了近一半
   > - `price` 从 $3 到 $2,499，分布偏斜很厉害
   >
   > EDA 图表已生成（8 面板），附件见下。要不要我按 category 拆一下销售额和利润率？

4. The `MEDIA:C:\...\sales_eda.png` line in your reply is what triggers Discord to attach the PNG. Exactly one such line. The rest of the reply is plain chat text.
