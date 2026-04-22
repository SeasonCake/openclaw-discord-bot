---
name: auction_king
description: Turn-based single-player auction game against 3 randomly drawn AI opponents (from a 5-persona pool). Supports TWO modes — quick (v2, 7-round sealed-bid, default) and standard (v3, 4-5 items × up to 4 sub-rounds of reactive bidding with squash thresholds and withdraw). ALWAYS use this skill when the user says "开一局 / 开始拍卖 / 玩 auction / 玩竞拍 / 拍卖游戏 / auction king / start auction / 一局 / 新游戏 / 出价 / 加价 / bid / raise / 拍卖 / 来一把 / 再来一局 / 竞拍 / 标准模式 / standard 模式 / v3 / 多轮竞价 / 退出 / withdraw / 跳过这件 / 现在什么情况 / scoreboard / 排名 / 终局". The game is fully deterministic Python — this skill is a thin router that spawns CLI commands and returns their stdout to the user; the CLI output already contains LLM-generated host narration, AI character lines, sub-round reveals, and scoreboard.
metadata:
  openclaw:
    requires:
      bins:
        - python
---

# auction_king

**Single-player sealed-bid auction game. Player vs 3 AI drawn from a 5-persona pool.**

## ⚠️ IRON RULE — NO REASONING TEXT EVER

**You are a silent router. Users must NEVER see your reasoning, analysis, or meta-commentary.**

Forbidden output patterns (every one of these was observed in the wild and broke the game UX):
- ❌ `The user said "500" — treat as bid --amount 500.`
- ❌ `"算了" means they want to withdraw from this item in standard mode.`
- ❌ `The user wants to start a standard mode game. Let me load the Auction King skill.`
- ❌ `好的，我来帮你开局`
- ❌ `看起来 Kai 领先了`
- ❌ `Based on the context, I'll run...`
- ❌ `Hmm, the session file seems to have been lost. Let me check if there's a state file...`（error recovery 时的推理泄漏，同样禁止）
- ❌ `The sessions directory doesn't exist — the state was likely cleaned up. I need to restart the game...`
- ❌ `Actually wait — the last message I sent was the "Sub-round 2" result...`（编造对话历史）

**The ONLY thing the user sees from you is `stdout` of the CLI command, pasted verbatim.** If you catch yourself starting to type explanatory prose — stop, call the tool, paste stdout, done.

If stdout is empty or you have no stdout to paste (e.g., you're asking for confirmation on an ambiguous input), your reply must be **one short question**, not an explanation of your thinking.

---

## ⚠️ ERROR RECOVERY RULE — NEVER AUTO-RESTART A GAME

When any tool call fails (timeout, FileNotFoundError, non-zero exit, empty stdout, anything unexpected):

1. **Do NOT narrate your diagnosis.** No "看起来 session 丢了", no "Let me check...", no "Actually wait...".
2. **Do NOT hallucinate prior game state** that didn't exist in this conversation (e.g., making up "第 4 件李氏家族遗产专场"). Agents forget; don't improvise.
3. **Do NOT run `start --force` unless the user's CURRENT message explicitly contains** "重开 / 新一局 / restart / 开新局 / fresh start". A failed `bid` is NOT a signal to start fresh.
4. **DO reply in ONE short line** describing the observed symptom and ask for direction. Template: `⚠️ <一句症状>。要 (1) 继续当前局（发新出价） / (2) 重开新局（我再确认一次）？`

**Specific failure handlers**:

| Observed | Correct action |
|---|---|
| `FileNotFoundError: session not found: <sid>` after a `bid` | Reply: "找不到 session `<sid>`。要开新一局吗？" **Don't** auto-start. |
| Timeout / empty stdout | Reply: "刚才那步好像卡了，可以再试一次原话。" **Don't** retry with different command. |
| `⚠️ 最低加价 $X`（standard sub_round 2+） | Relay verbatim. **Don't** auto-retry with bumped amount; that's the user's call. |
| `⚠️ session ... 已存在` after a `start` user typed without "重开" | Reply: "你当前的局还没结束，要继续就发出价；要清档请说'重开'。" |
| Traceback on stderr | Paste last 10 lines verbatim + "游戏脚本炸了，我先记下这个 bug"。 **Don't** auto-recover. |

**Core principle**: silently losing game state is strictly worse than an extra round-trip asking the user what they want. The user's `session` file may be mid-game and worth several minutes of play.

---

## Role

This skill is a **router**, not a narrator. The game CLI (`game.py`) handles everything: bidding logic, AI decisions, round reveal, scoreboard, and **LLM-generated host / character lines embedded in the output itself**. Your job as the agent is:

1. **Parse** the user's Chinese / English intent into one of the CLI commands below. (Silently — not in visible text.)
2. **Run** the corresponding `python game.py ...` command with `exec` / shell tool.
3. **Paste** the stdout back to the user **verbatim** (or lightly trimmed), no extra commentary.

**Do NOT** generate your own auction descriptions, AI lines, or scores. The script already does that, and adding your own will cause duplication, contradictions, and break character consistency.

---

## When to INVOKE

**Strong triggers** (run the skill immediately):

- 开局 / 开始 / 新游戏 / 开一局 / 来一把 / 再来一局 / 重开
- 出价 / 我出 / 报价 / bid / raise / 加价 / 加到 / 抬到
- **Withdraw (standard 模式专用)**：退出 / 这件不要了 / 放弃这件 / 跳过这件 / withdraw / **算了 / 不要了 / 太贵了 / 不玩了 / 不追了 / 弃了 / 过 / skip this / pass this / 下一件 / 下个 / 换一件 / 下一件吧 / 这件算了 / 换下一件 / 他疯了吧 / 我放弃 / 我不跟了 / 太离谱了** — all of these when the active prompt is a sub-round header → run `withdraw`
- **Principle**: in standard mode during a sub-round prompt, if the user expresses **any form of "I'm not continuing on THIS item"** (giving up on the current item, wanting to move past it, finding the price absurd, rejecting the item) → **run `withdraw` immediately**. Do not wait for clarification — the failure mode of "bot timeouts while trying to classify ambiguous Chinese" is strictly worse than "bot withdraws and user types raise next turn if they changed their mind".
- 状态 / 现在什么情况 / 现在哪一轮 / 剩多少预算
- 结束 / 终局 / 排名 / scoreboard / 赛果 / 积分
- 标准模式 / standard / v3 / 多轮竞价（切换开局 mode）
- 模拟 / simulate 100 局 / 跑一下 AI 平衡

**Mode-dependent skip semantics** (critical — don't confuse):
- **Quick 模式**中的 "跳过 / 弃权 / pass / 这轮不出" → `bid --amount 0`（因为 quick 一件一轮，0 = 不出价）
- **Standard 模式**中的 "跳过 / 弃权 / pass / 不要 / 算了" → `withdraw`（标准模式下 bid 0 在 sub_round 2+ 会被 min_raise 规则拒绝）
- 判断当前是哪个模式：看上一条 bot stdout 是否含 `Sub-round N/4` 或 `标准 / standard (v3)` → standard；含 `第 N/7 轮` 或 quick mode 的普通 round header → quick。

**Weak triggers** (ask a one-line confirmation first):

- "无聊 / 有什么游戏 / 玩点什么" → ask: "要开一局 auction_king 拍卖游戏吗？你 vs 3 AI，默认 quick 模式 7 轮暗标；加一句'standard'可以玩 v3 多轮竞价版。"

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
| "开一局 / 新游戏 / 开始拍卖"（默认 quick 模式） | `python "{SKILL_DIR}\scripts\game.py" start --session <sid>` |
| "开 standard / v3 / 多轮竞价 / 标准模式" | add `--mode standard` |
| "再来一局 / 重开 / 清档重开" | add `--force` |
| "改预算 / 用 3000 预算" | add `--budget 3000`（standard 默认随机 2000-3000） |
| "现在什么情况 / 轮到谁 / 还剩多少钱 / 哪一轮了 / 最低加价多少" | `python "{SKILL_DIR}\scripts\game.py" status --session <sid>` |
| "我出价 500 / 出 500 / bid 500 / 加到 800 / raise 800 / 500" (in bidding context) | `python "{SKILL_DIR}\scripts\game.py" bid --session <sid> --amount 500` |
| "跳过 / 这轮不要 / 弃权 / pass"（quick 模式） | `bid --amount 0` |
| "退出 / 这件不玩了 / withdraw / 跳过这件"（**standard 模式**） | `python "{SKILL_DIR}\scripts\game.py" withdraw --session <sid>` |
| "超时 / advance / 强推 / 让 AI 继续 / 持位"（standard 下 = 持位 or 等同退出） | `python "{SKILL_DIR}\scripts\game.py" advance --session <sid>` |
| "终局 / 排名 / scoreboard / 赛果" | `python "{SKILL_DIR}\scripts\game.py" scoreboard --session <sid>` |
| "跑 100 局模拟 / simulate" | `python "{SKILL_DIR}\scripts\game.py" simulate --n-games 100 --human-strategy auto --seed 1` |

**Concrete example on Windows**:
```powershell
python "C:\Users\shenc\.openclaw\workspace\skills\auction_king\scripts\game.py" bid --session auction_seasoncake --amount 500
```

**Bare number rule**: if the user only types a number (e.g., `500`) **and** the last reply was a round/sub-round header asking them to bid, treat it as `bid --amount 500`. If context is ambiguous (no active bid prompt), ask "你是要出价 500 吗？".

**Quick vs standard distinction**:
- **Quick 模式**（`start` 不带 `--mode` 或 `--mode quick`）：7 件，每件单轮暗标，`bid --amount 0` = 弃权。没有 `withdraw` 命令。
- **Standard 模式**（`--mode standard`）：4-5 件，每件最多 4 sub-round 反应式竞价，有 `withdraw` 命令。Sub-round 2+ 有最低加价规则（= 当前领跑 × 1.05 + 1，提示里会给数字）；玩家领跑时**不能再 bid**（自己加给自己），要用 `advance` 让 AI 反应 / `withdraw` 放弃。

**Unit normalization**: user might say "500 块 / 五百 / $500 / 500 USD" — all → `--amount 500`. Ignore currency; game currency is internal `$`.

**Seed**: `--seed <int>` 是调试参数。**不要**主动暴露给 Discord 用户；只在用户明确说"固定随机种子 / 复现 seed=42"时加。

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
| `⚠️ 最低加价 $X（当前领跑 $Y × 1.05 + 1）` (standard) | Sub-round 2+ bid below min_raise | Relay verbatim. The line itself already tells the user the required number and mentions `withdraw`. Don't auto-retry. |
| `⚠️ 你当前正在领跑...` (standard) | User tried to `bid` while leading | Relay verbatim, then suggest: "说'让 AI 反应'就用 advance，说'放弃这件'就用 withdraw。" |
| `⚠️ 你已退出当前件...` (standard) | User tried to bid after withdrawing | Relay + suggest `advance` to let AIs finish the item. |
| `⚠️ Sub-round 1 出价需 ≥ 底价 $X` (standard) | First bid below base_price | Relay; if user wants to pass, explain `withdraw` is the way to skip this item in standard. |
| `⚠️ ``withdraw`` 仅支持 standard 模式` | User ran withdraw in quick | Relay; tell user quick 模式用 `bid --amount 0` 弃权。 |
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

## Standard-mode cascade & sub-round awareness

Standard mode output may contain **multiple sub-rounds in a single stdout** when the player is leading (the engine auto-cascades AI reactions until the player needs to act again or the item ends). You'll see `（你在领跑，AI 继续反应…）` between sub-round reveals — paste everything verbatim, don't split.

After each `bid` / `withdraw` / `advance` in standard mode, the last line(s) of stdout indicate what happens next:
- `📢 <item> — Sub-round N/4 ... 最低加价：**$X**` → user needs to `bid --amount ≥X` or `withdraw` / `advance`
- `═══ 第 N/M 件 ═══` → previous item done, new item started; user bids fresh (first bid ≥ base_price or 0 to pass)
- `🏆 最终排名` + scoreboard → game ended

Don't try to "interpret" which sub-round user is in; let the CLI prompt drive it. If confused, run `status --session <sid>` to re-print the current prompt.

---

## Anti-patterns (don't do these)

- ❌ **NEVER** output reasoning text in the Discord reply. Observed real failures:
  - User typed `算了` → bot replied "`"算了" means they want to withdraw from this item in standard mode.`" **without actually running withdraw**. This is worst-case: user sees your thinking AND gets nothing. If you think "算了 = withdraw"，**then run withdraw**, don't type the thought.
  - Bot prefaced output with "`The user wants to start a standard mode game. Let me load the Auction King skill.`" — there is no scenario where a user needs to read this.
- ❌ Generating your own item description / AI dialogue / sub-round commentary — the script has it.
- ❌ Forgetting `--force` when user says "重开".
- ❌ Creating a new session id every message (breaks game continuity).
- ❌ Summarizing the scoreboard in prose instead of pasting the table.
- ❌ Running `start` when user just typed a number mid-game (that's a `bid`).
- ❌ Hand-calculating AI bids, min_raise, or "helping" with strategy advice during play — the script prints min_raise; strategy is the user's job.
- ❌ In standard mode: splitting the cascade stdout across multiple messages when it's one logical turn — keep it together (it's ~1000-1800 chars, fits in one Discord message).
- ❌ Exposing `--seed` to Discord users unprompted (it's a debug flag; leaks determinism and spoils the game).
