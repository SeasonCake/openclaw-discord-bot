---
name: auction_king
description: Turn-based single-player sealed-bid auction game against 3 randomly drawn AI opponents (from a 5-persona pool). ALWAYS use this skill when the user says "开一局 / 开始拍卖 / 玩 auction / 玩竞拍 / 拍卖游戏 / auction king / start auction / 一局 / 新游戏 / 出价 / bid / 拍卖 / 来一把 / 再来一局 / 竞拍 / 现在什么情况 / scoreboard / 排名 / 终局". The game is fully deterministic Python — this skill is a thin router that spawns CLI commands and returns their stdout to the user; the CLI output already contains LLM-generated host narration, AI character lines, and scoreboard.
metadata:
  openclaw:
    requires:
      bins:
        - python
---

# auction_king

**Single-player sealed-bid auction game. Player vs 3 AI drawn from a 5-persona pool.**

This skill is a **router**, not a narrator. The game CLI (`game.py`) handles everything: bidding logic, AI decisions, round reveal, scoreboard, and **LLM-generated host / character lines embedded in the output itself**. Your job as the agent is:

1. **Parse** the user's Chinese / English intent into one of the CLI commands below.
2. **Run** the corresponding `python game.py ...` command with `exec` / shell tool.
3. **Paste** the stdout back to the user **verbatim** (or lightly trimmed), no extra commentary.

**Do NOT** generate your own auction descriptions, AI lines, or scores. The script already does that, and adding your own will cause duplication, contradictions, and break character consistency.

---

## When to INVOKE

**Strong triggers** (run the skill immediately):

- 开局 / 开始 / 新游戏 / 开一局 / 来一把 / 再来一局 / 重开
- 出价 / 我出 / 报价 / bid / raise
- 状态 / 现在什么情况 / 现在哪一轮 / 剩多少预算
- 结束 / 终局 / 排名 / scoreboard / 赛果 / 积分
- 弃权 / 跳过 / 这轮不出 / pass / skip
- 模拟 / simulate 100 局 / 跑一下 AI 平衡

**Weak triggers** (ask a one-line confirmation first):

- "无聊 / 有什么游戏 / 玩点什么" → ask: "要开一局 auction_king 拍卖游戏吗？你 vs 3 AI，7 轮暗标。"

## When NOT to invoke

- CSV / Excel attachments → that's `csv_analyzer`.
- Generic knowledge questions ("拍卖规则是什么") → answer inline, don't spawn the game.
- Anything that's clearly not game-related.

---

## Session naming (critical)

**One Discord user = one session. Reuse the session across messages.**

Pick the session id from the Discord username (or any stable identifier from the message context) and **keep using it for every command in this conversation**.

```
session_id = f"auction_{discord_username_lowercase}"
# Example: auction_seasoncake
```

If the session already exists, commands like `bid` / `status` / `scoreboard` just continue the game. Only pass `--force` to `start` when the user **explicitly says** "重开 / 新一局 / restart". Otherwise `start` will refuse to overwrite.

---

## Command mapping (natural language → CLI)

**Paths on Windows**: OpenClaw deploys skills to `~\.openclaw\workspace\skills\auction_king\`. The scripts live under `scripts\`. **Quote the path** because it contains spaces (user profile path).

The `python` interpreter is the system Python (3.13 in this setup). All internal imports (`from ai_bidders import ...`) work because Python auto-adds the script's dir to `sys.path[0]` when invoked as `python <script_path>`.

| User intent (examples) | CLI command |
|---|---|
| "开一局 / 新游戏 / 开始拍卖" | `python "{SKILL_DIR}\scripts\game.py" start --session <sid>` |
| "再来一局 / 重开 / 清档重开" | `python "{SKILL_DIR}\scripts\game.py" start --session <sid> --force` |
| "指定种子开局 seed=42" | add `--seed 42` |
| "改预算 / 用 3000 预算" | add `--budget 3000` |
| "现在什么情况 / 轮到谁 / 还剩多少钱 / 哪一轮了" | `python "{SKILL_DIR}\scripts\game.py" status --session <sid>` |
| "我出价 500 / 出 500 / bid 500 / 500" (in bidding context) | `python "{SKILL_DIR}\scripts\game.py" bid --session <sid> --amount 500` |
| "跳过 / 这轮不要 / 弃权 / pass" | `python "{SKILL_DIR}\scripts\game.py" bid --session <sid> --amount 0` |
| "超时 / advance / 强推" | `python "{SKILL_DIR}\scripts\game.py" advance --session <sid>` |
| "终局 / 排名 / scoreboard / 赛果" | `python "{SKILL_DIR}\scripts\game.py" scoreboard --session <sid>` |
| "跑 100 局模拟 / simulate" | `python "{SKILL_DIR}\scripts\game.py" simulate --n-games 100 --human-strategy auto --seed 1` |

**Concrete example on Windows**:
```powershell
python "C:\Users\shenc\.openclaw\workspace\skills\auction_king\scripts\game.py" bid --session auction_seasoncake --amount 500
```

**Bare number rule**: if the user only types a number (e.g., `500`) **and** the last reply was a round header asking them to bid, treat it as `bid --amount 500`. If context is ambiguous (no active bid round), ask "你是要出价 500 吗？".

**Unit normalization**: user might say "500 块 / 五百 / $500 / 500 USD" — all → `--amount 500`. Ignore currency; game currency is internal `$`.

---

## Output handling

The CLI stdout is **already formatted for chat** (emojis, markdown headers, 💬 lines, ⚖️ checks, 💰 budgets). Paste it back **verbatim**.

**Rules**:
1. **Do NOT** add your own commentary at the top or bottom like "好的，我开始了" or "看起来 Kai 在领先哦"。 The script output is the reply.
2. **Do NOT** re-summarize the AI dialogue — it's already there, in character.
3. **Do NOT** "fix" or "improve" the Chinese / English — pass through even if it looks quirky; that's the character voice.
4. **Exception**: if the stdout is empty / contains only a warning (`⚠️ ...`), copy that warning and add a short guidance line. Example: stdout = `⚠️ session auction_seasoncake 已存在。加 --force 覆盖` → reply: `那局还没下完哦 —— 要继续就告诉我出价金额，想重开就说"重开"。`

**Length**: Discord has a 2000-char per-message limit. The game's per-round output is ~1500 chars, usually fits. If `scoreboard` output exceeds 2000 chars, split at blank lines.

---

## Environment (one-time setup context)

The user has already configured:
- `DEEPSEEK_API_KEY` env var → game.py's `llm_narrator.py` uses it
- `AUCTION_KING_USE_LLM=1` → enables DeepSeek narration (recommended; adds ~6s / round; costs ~¥0.002 / game)

If the player complains output is "too mechanical", the bot LLM can suggest: "把 AUCTION_KING_USE_LLM 设成 1 能启用 DeepSeek 主持人，更有戏。" (Don't auto-set — that's user env var territory.)

If `DEEPSEEK_API_KEY` is missing, the game **falls back to templates** silently — still playable, just less dynamic lines. This is by design.

---

## Common failure modes

| stdout / exit signal | Cause | Reply |
|---|---|---|
| `⚠️ session ... 已存在` | User ran `start` without `--force` over an existing session | Tell user: 当前有未完的局，出价继续 / 说"重开" 才会清档。 |
| `⚠️ 当前状态是 ending, 不能出价` | Round ended, status = `ended` | Tell user: 本局已结束，输入"排名"查看赛果。 |
| `⚠️ 出价 $X 超过你的预算 $Y` | User over-bid | Relay verbatim, remind of remaining budget. |
| `FileNotFoundError` / `no such session` | User asked for status/bid with a session that doesn't exist | Offer to `start` a new one. |
| Script raises traceback to stderr | Bug | Paste the last 10 lines of traceback to user, say "游戏脚本炸了，我先记下这个 bug"。 Don't pretend it worked. |

---

## Full end-to-end example (Discord)

User: `@bot 开一局 auction_king`

1. Extract session: `auction_seasoncake` (from Discord username).
2. Run:
   ```powershell
   python "C:\Users\shenc\.openclaw\workspace\skills\auction_king\scripts\game.py" start --session auction_seasoncake
   ```
3. Stdout (example):
   ```
   🎭 拍卖会开场

   > 诸位藏家，欢迎光临今晚的专场。今晚 3 位对手坐镇：老周头沉稳、Kai 激进、阿鬼狡诈。7 轮 $2000，各凭本事。

   【第 1/7 轮 · 单件】

   🏺 民国白瓷茶壶（瓷器）| 底价 $80
   📌 线索
     · 同类拍品平均成交 $280
     · 品相 A，壶嘴有极小崩
     · 专家估价 $200-$450
   ...
   ```
4. Paste stdout back verbatim.

User: `@bot 我出 300`

1. Parse → `bid --amount 300` on session `auction_seasoncake`.
2. Run:
   ```powershell
   python "C:\Users\shenc\.openclaw\workspace\skills\auction_king\scripts\game.py" bid --session auction_seasoncake --amount 300
   ```
3. Paste stdout (reveal + next round header).

User: `@bot 看看现在`

1. Parse → `status`.
2. Run `status --session auction_seasoncake`, paste stdout.

User (after round 7): `@bot 赛果`

1. Parse → `scoreboard`.
2. Run `scoreboard --session auction_seasoncake`, paste stdout.

---

## Anti-patterns (don't do these)

- ❌ Generating your own item description / AI dialogue — the script has it.
- ❌ Forgetting `--force` when user says "重开".
- ❌ Creating a new session id every message (breaks game continuity).
- ❌ Summarizing the scoreboard in prose instead of pasting the table.
- ❌ Running `start` when user just typed a number mid-game (that's a `bid`).
- ❌ Hand-calculating AI bids or "helping" with strategy advice during play — that defeats the game.

---

## Reminder for future versions (v3 multi-round bidding)

The CLI will gain a `withdraw` command and a `--mode standard` flag. When that lands, extend the Command mapping table. For now (quick mode only), the 7-round single-shot flow above covers all gameplay.
