<p align="right">🌐 <strong>English</strong> · <a href="./README.zh-CN.md">中文</a></p>

# OpenClaw Discord Bot

> An AI assistant hosted on Discord, built with the [OpenClaw](https://github.com/openclaw/openclaw) framework. Two custom skills: **deterministic CSV EDA** and an **auction game with AI personalities**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-2026.4.15-8A2BE2)](https://github.com/openclaw/openclaw)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-1E90FF)](https://platform.deepseek.com/)
[![Discord](https://img.shields.io/badge/Channel-Discord-5865F2?logo=discord&logoColor=white)](https://discord.com/)

---

## Demo

https://github.com/user-attachments/assets/d48fbde1-1160-4886-adc0-20be6bf00876

**▶ Also on YouTube:** [https://youtu.be/4KZbtfR2rOY](https://youtu.be/4KZbtfR2rOY) (unlisted) · **▶ In-repo copy:** [`assets/videos/demo.mp4`](./assets/videos/demo.mp4)

### Snapshots

Three moments from a single Discord session — CSV analysis, a bid in progress, and the final scoreboard.

<table>
<tr>
<td width="33%" align="center"><strong>1. CSV analysis</strong><br/><img src="./assets/screenshots/01-csv-analyzer.png" alt="csv analyzer" /></td>
<td width="33%" align="center"><strong>2. Auction game start</strong><br/><img src="./assets/screenshots/02-auction-king-start.png" alt="auction start" /></td>
<td width="33%" align="center"><strong>3. Final scoreboard</strong><br/><img src="./assets/screenshots/03-auction-king-scoreboard.png" alt="scoreboard" /></td>
</tr>
</table>

> 🖼️ **Full unedited chat flow** (long screenshot) → [`04-full-chat-flow.png`](./assets/screenshots/04-full-chat-flow.png) — shows one bot handling both skills from the same `@` mention, routed by natural-language intent with zero mode switching.
>
> 📊 **Sample EDA chart outputs** from `csv_analyzer` on other datasets → [`eda-sample-1`](./assets/screenshots/eda-sample-1.webp) · [`eda-sample-2`](./assets/screenshots/eda-sample-2.webp)

---

## What it does

Both skills share one Discord entry point (`@<your-bot> <anything>`). The framework routes by natural-language intent — no manual mode switching.

### 1. `csv_analyzer` — deterministic CSV / XLSX EDA

Drop any tabular file, instantly get:

- **10-panel EDA chart** (PNG): distribution histograms with mean/median markers, correlation heatmap, missing-value overview, **auto-detected one-hot encoding groups**, diversified Seaborn palettes per panel, **CJK-safe fonts**
- **Structured text summary**: row/column count, dtype breakdown, salient findings in 2–4 bullets

Fully deterministic Python — no prompt-engineering roulette.

### 2. `auction_king` — multi-round auction game with 3 AI opponents

- **5 AI personalities** (pick 3 per game): *Zhou the steady · Kai the FOMO · Sister Yi the classy · Gui the trapper · Miles the sniper*
- **Personality-aware bidding**: trappers bait-and-switch, snipers wait until round 3, FOMO chases the leaderboard
- **Narration layer** (DeepSeek): opening MC, per-round AI commentary, final sardonic wrap-up; falls back to templates if API key is missing — won't crash
- **Multi-mode**: `quick` (v2, sealed single-round) and `standard` (v3, 4 sub-rounds with `withdraw` / budget reuse / re-auction on tie)
- **State machine**: persists every turn, sessions resumable by ID, 39 unit tests covering bidding and narration layers

---

## Tech stack

- **Agent framework**: [OpenClaw](https://github.com/openclaw/openclaw) 2026.4.15 (TypeScript, npm global install)
- **LLM**: [DeepSeek Chat](https://platform.deepseek.com/) via OpenAI-compatible API
- **Skill logic**: Python 3.13 · `pandas` · `matplotlib` · `seaborn` · `openpyxl`
- **Channel**: Discord (bot account, OAuth2 invite, Message Content + Server Members intents)
- **Host**: Windows 11 / PowerShell (Linux + macOS paths also work — nothing Windows-specific in skill code)

---

## Quick start

Full reproducible 30-minute setup → **[SETUP.md](./SETUP.md)**. Real pitfalls & fixes (13 classes of bug) → **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)**.

```powershell
# Prereqs: Node.js 23+ · Python 3.13+ · Discord bot token · DeepSeek API key

# 1) Install OpenClaw CLI (global)
npm install -g openclaw

# 2) Set env vars (persistent, so gateway child-processes inherit them)
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY",     "sk-...", "User")
[Environment]::SetEnvironmentVariable("DISCORD_BOT_TOKEN",    "...",    "User")
[Environment]::SetEnvironmentVariable("AUCTION_KING_USE_LLM", "1",      "User")

# 3) Copy openclaw.json template to ~/.openclaw/ (schema in SETUP.md)
openclaw config validate

# 4) Deploy skills (robocopy to ~/.openclaw/workspace/skills/)
.\tools\deploy-skill.ps1 csv_analyzer
.\tools\deploy-skill.ps1 auction_king

# 5) Start the gateway (foreground)
openclaw gateway

# In Discord:
#   @<your-bot> analyze this    [+ attach CSV]   → instant EDA chart + summary
#   @<your-bot> start a standard game              → auction game
#   700                                          → bid
#   withdraw                                     → fold this sub-round
```

---

## Project journey

I'm pivoting from **EHS (Environmental Health & Safety)** into **Data / AI**. This is my first end-to-end portfolio project — not a tutorial follow-along, but something with real architecture decisions, real Windows-specific bugs, and real trade-offs **documented as they happened** in [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

Representative milestones:

- **Started targeting WeChat, pivoted to Discord.** The ClawBot plugin is iOS-only and I use Android. Because OpenClaw cleanly decouples *channel* from *skill*, zero skill code changed during migration.
- **Worked around OpenClaw's symlink-escape security feature.** The framework refuses to load skills reached via Windows junction links. Replaced with a `robocopy`-based [`tools/deploy-skill.ps1`](./tools/deploy-skill.ps1) one-command sync.
- **Root-caused a CRLF fence-parsing bug in OpenClaw 2026.4.15.** The `parseFenceSpans` regex doesn't handle `\r`, so example `MEDIA:` paths inside SKILL.md code fences were being extracted as real directives → Discord sent duplicate attachments. Fix: strip literal paths from examples. Upstream PR drafted.
- **Split the "IRON RULE" into three named LLM guardrails.** A single rule always collapsed into "say less everywhere" and paraphrased CLI output I needed preserved. Split into *zero-preamble before tool calls*, *verbatim paste after*, *one-line error recovery*, each with real-observed bad outputs as ❌ counter-examples. Fixes alignment over-generalization.

Each of these is the kind of problem a working engineer hits in their first week with an unfamiliar agent framework. Shipping through them — and writing them down clearly — is the work I'm trying to get hired to do.

---

## Roadmap snapshot

| Stage | Status |
|---|---|
| 1. Environment + Discord bot wiring | ✅ Done |
| 2. `csv_analyzer` skill | ✅ Done |
| 3. `auction_king` skill (v2 quick + v3 standard) | ✅ Shipped |
| 4. Portfolio polish (video + screenshots + LinkedIn) | ✅ Done |

Detailed per-stage breakdown → [PIVOT_TODO.md](./PIVOT_TODO.md).

---

## Repo structure

```
openclaw-discord-bot/
├── README.md                   ← you are here (English)
├── README.zh-CN.md             ← 中文版
├── SETUP.md                    ← reproducible setup
├── TROUBLESHOOTING.md          ← 13 documented bugs + fixes
├── PIVOT_TODO.md               ← career pivot checklist
├── LICENSE                     ← MIT
├── requirements.txt            ← Python deps for skills
├── assets/
│   ├── screenshots/            ← 4 Discord screenshots + 2 sample charts
│   └── videos/demo.mp4         ← 15-second demo
├── tools/
│   └── deploy-skill.ps1        ← one-command skill sync to ~/.openclaw/workspace/
└── skills/
    ├── csv_analyzer/           ← deterministic EDA skill
    │   ├── SKILL.md
    │   └── scripts/
    │       ├── analyze.py      ← pandas EDA (encoding fallback utf-8/gbk/latin-1)
    │       └── plot.py         ← multi-panel CJK-safe chart generator
    └── auction_king/           ← auction game skill
        ├── GAME_DESIGN.md      ← v2 quick-mode design
        ├── GAME_DESIGN_v3.md   ← v3 standard-mode design
        ├── SKILL.md            ← 4 named LLM guardrails
        ├── data/items.json     ← 16 items + 3 warehouses
        ├── scripts/            ← game.py + ai_bidders.py + llm_narrator.py + ...
        └── tests/              ← 39 unit tests
```

---

## Docs map

- 📺 **[assets/videos/demo.mp4](./assets/videos/demo.mp4)** · 15-second demo
- 🏗️ **[SETUP.md](./SETUP.md)** · reproducible setup
- 📘 **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** · 13 real bugs + root causes
- 🎯 **[PIVOT_TODO.md](./PIVOT_TODO.md)** · career pivot roadmap
- 🎮 **[skills/auction_king/README.md](./skills/auction_king/README.md)** · game design + CLI reference

---

## License

[MIT](./LICENSE) © 2026 SeasonCake
