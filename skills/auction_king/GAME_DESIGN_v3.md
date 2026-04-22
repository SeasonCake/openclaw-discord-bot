# auction_king · Game Design v3.0

> **2026-04-18 冻结**。v3 最大变化：引入**多轮竞价 + 信息博弈**机制，让"价格判断"成为游戏核心策略。
> v2 保留为 "快速模式 (quick)"，v3 称为 "标准模式 (standard)"，玩家在 `start` 时选。

## 目录
1. [为什么改](#1-为什么改)
2. [两种模式并存](#2-两种模式并存)
3. [核心玩法（标准模式）](#3-核心玩法标准模式)
4. [碾压阈值机制](#4-碾压阈值机制)
5. [AI 反应式策略](#5-ai-反应式策略)
6. [State Schema 变化](#6-state-schema-变化)
7. [CLI 命令变化](#7-cli-命令变化)
8. [UX 流程样例](#8-ux-流程样例)
9. [LLM 台词新触发点](#9-llm-台词新触发点)
10. [实现阶段](#10-实现阶段)

---

## 1. 为什么改

**v2（3.4）的问题**：7 件物品每件只拍一轮。玩家的"价格判断"只用一次就结束，AI 的陷阱/狙击/FOMO 人设只能体现在**台词**上，**决策层面**没有博弈。

**v3 要解决**：让 AI 的反应式策略真正起作用——
- 阿鬼的陷阱现在能真正"设陷阱"：前几轮抬价，最后一轮退出把烫手山芋丢给别人
- Miles 的狙击现在能真正"装睡到最后一击"
- Kai 的 FOMO 现在能看到别人加价后**真的跟进**
- 玩家现在有机会在多轮之间调整判断

---

## 2. 两种模式并存

| | **快速模式 (quick)** | **标准模式 (standard)** |
|---|---|---|
| 来源 | 3.2a + 3.4 | v3.0（新） |
| 物品数 | 7 | 4–5（随机） |
| 每件轮数 | 1 | 1–4（动态结束） |
| 预算 | $2000 | $2000–$3000（随机） |
| 适用场景 | 快速 demo / 1 分钟体验 | 核心玩法 / 完整博弈 |
| `start` 参数 | `--mode quick`（默认 quick） | `--mode standard` |

**两种模式共享**：AI 池、物品库、LLM 台词层、state 存储、scoreboard。

---

## 3. 核心玩法（标准模式）

### 一局总览

1. **开局**：随机 4 或 5 件物品（混合单件 + 仓库）、随机预算 $2000–$3000、从 5 AI 池抽 3。
2. **按物品顺序推进**，每件物品独立走一个"多轮竞价子流程"（下节详述）。
3. **每件物品结束** → 更新预算、库存 → 进入下一件。
4. **所有物品拍完** → 终局排名。

### 单件物品的"多轮竞价子流程"

每件物品初始**全部 4 人都是活跃参与者**（human + 3 AI）。然后进入**最多 4 个 sub_round**：

```
┌───────────────────────────────────────────────────────────┐
│ sub_round 1：独立判断（无历史信息）                        │
│   - 每人做选择：出价 ≥ 底价 / 直接退出                     │
│   - 全员提交后 → 揭晓本轮出价                              │
│   - 【检查碾压】：最高价 ≥ 次高价 × 1.8 → 立刻结束         │
│   - 否则 → 退出者移出参与列表，进入 sub_round 2            │
├───────────────────────────────────────────────────────────┤
│ sub_round 2：反应阶段（可看 sub_round 1 出价）             │
│   - 每人做选择：加价 ≥ current_max × 1.05 / 退出           │
│   - 揭晓 → 【检查碾压】：最高价 ≥ 次高价 × 1.5 → 结束      │
│   - 否则 → 进入 sub_round 3                                │
├───────────────────────────────────────────────────────────┤
│ sub_round 3：继续（可看 1–2 的所有出价）                   │
│   - 规则同 sub_round 2                                     │
│   - 【检查碾压】：阈值 × 1.2                               │
│   - 否则 → 进入 sub_round 4                                │
├───────────────────────────────────────────────────────────┤
│ sub_round 4：封口（最后一轮）                              │
│   - 规则同 sub_round 2（加价或退出）                       │
│   - 无碾压检查，最高者直接拿下                             │
└───────────────────────────────────────────────────────────┘
```

**任何时候 active_participants ≤ 1 立即结束该物品**。

**没人出价达底价 → 流拍**（不扣钱、不计分）。

---

## 4. 碾压阈值机制

> 🔑 v3 最有意思的设计。让 R1 "一锤吓退所有人" 成为一种真实策略。

| sub_round 结束时检查 | 阈值 | 含义 |
|---|---|---|
| sub_round 1 | `max_bid ≥ second_bid × 1.8` | R1 孤注一掷，碾压拿下 |
| sub_round 2 | `max_bid ≥ second_bid × 1.5` | R2 相对领先，别人不追了 |
| sub_round 3 | `max_bid ≥ second_bid × 1.2` | R3 小胜即可碾压 |
| sub_round 4 | 不检查（直接拿下最高） | 封口轮 |

**特殊情况**：
- R1 只有 1 人出价（其他全退出）→ 直接拿下（相当于 ∞ 倍碾压）。
- R1 没人出价 → 流拍。
- 任一轮 second_bid = 0（因为只剩 2 人且一个刚 withdraw）→ 相当于 ∞ 倍，直接拿下。

**玩家体验**：
- R1 出 base_price 的 2 倍以上 + 比别人高 80% → "一槌定音"（高光时刻，但亏钱风险大）。
- 一般玩家会避开 R1 巨额，走稳健路线。但**看穿 hints 真值的老手**可能在 R1 就敢扔大价。

---

## 5. AI 反应式策略

每个 AI 在每个 sub_round 需要决定：**出价 X** 或 **withdraw**。

### 共用决策框架

```
est       = AI 内部估值（= estimate_from_hints × 人格系数）
ceiling   = AI 的最大承受价（est × 人格 ceiling）
current_max = 本件物品目前最高价（sub_round 2+ 才有）

如果 current_max > ceiling → withdraw
否则 → bid（具体金额看人格）
```

### 每个 AI 的人格参数

| AI | est 系数 | ceiling | R1 策略 | R2–3 反应 | R4 封口 |
|---|---|---|---|---|---|
| **老周头** | 真值 × 0.85 | est × 0.85 | 出 est × 0.70（瓷器加 10%） | 任何时候 current_max > ceiling → withdraw | 按 ceiling 出 |
| **Kai** | 真值 × 0.95 | 预算上限（不在乎价） | 出 est × 0.90 | **FOMO 触发**：current_max × 1.10（只要比自己估值低就跟） | 烧完预算为止 |
| **艺姐** | 本行真值 × 1.0，非本行 = 0 | est × 1.05 | 本行出 est × 0.90；非本行**直接 withdraw** | 本行坚持按 ceiling 出；非本行已退 | 本行最后狙击 est × 1.05 |
| **阿鬼** | 真值 × 0.95（accurate 80%） 或 真值 × 0.70（wild 20%） | est × 0.95 | 出 est × 0.75 | **陷阱模式（50%）**：R2 加到 current_max × 1.15（抬价迷惑）；R3 再加；**R4 突然 withdraw** 🎭<br>**正常模式（50%）**：按标准逻辑 | 陷阱模式必 withdraw；正常模式按 ceiling |
| **Miles** | 真值 × 0.95 | est × 1.10 | **必 withdraw** 装睡 | R2 仍 withdraw；R3 若 current_max < est × 0.85，复活加到 est × 0.85 | **狙击**：加到 current_max × 1.08，不超 ceiling |

### 特殊规则

**阿鬼陷阱模式**的精确逻辑：
- 开局时 `rng` 决定本件物品是否走陷阱（50%）。
- 走陷阱时：R1 正常出价，R2–R3 变成"加价狂魔"，R4 无论局势**必 withdraw**。
- **副作用**：如果在 R2/R3 就触发了碾压（他抬太高被自己坑），他就**自己吃下这个烫手山芋**——这就是陷阱反噬，是设计里的一部分。

**Kai 的预算保护**：
- Kai 会一直 FOMO 到预算 <= base_price 才退出。
- 如果加价后会 > 自己剩余预算，就按剩余预算出。

**Miles 的狙击条件**：
- R1、R2 永远 withdraw。
- R3 开始判断：如果 `current_max < est × 0.85`（别人都没出到真值），**复活**。
- R4 如果活着就狙击。

---

## 6. State Schema 变化

### 新增字段

```json
{
  "mode": "standard",                // 或 "quick"
  "active_ais": [...],
  "items_queue": [...],              // 标准模式 4–5 件
  "items_done": [...],
  "current_item": "item_003",        // 当前在拍的物品 id
  "current_item_state": {            // 🆕 标准模式核心
    "item_id": "item_003",
    "sub_round": 2,
    "active_participants": ["human", "Kai", "阿鬼"],  // 尚未 withdraw 的人
    "withdrawn": ["老周头"],                           // 已 withdraw 的人
    "history": [
      {
        "sub_round": 1,
        "bids": {"human": 500, "Kai": 800, "阿鬼": 275, "老周头": -1},  // -1 = withdraw
        "max_bid": 800,
        "max_bidder": "Kai",
        "second_bid": 500,
        "squash_triggered": false
      }
    ],
    "current_bids": {},              // 本 sub_round 待收集
    "current_max_bid": 800,          // sub_round 2+ 用来算最低加价
    "current_max_bidder": "Kai"
  },
  "status": "awaiting_human_bid",    // 状态不变
  "config": {
    "mode": "standard",
    "initial_budget": 2347,          // 2000–3000 随机
    "total_items": 4,                // 4 或 5
    "lot_rounds": [2, 4],            // 哪几件是仓库
    "max_sub_rounds_per_item": 4,
    "squash_thresholds": [1.8, 1.5, 1.2, null],  // null = 封口轮不检查
    "min_raise_ratio": 1.05          // R2+ 最低加价比例
  }
}
```

**快速模式**：`current_item_state` 字段不存在，走旧逻辑；`mode: "quick"` 标识走旧流程。

### items_done 格式（标准模式）

```json
{
  "item_id": "item_003",
  "type": "item",
  "sub_round_final": 3,              // 在第几轮结束的
  "end_reason": "squash" | "sole_survivor" | "final_round" | "no_bids",
  "winner": "Kai",
  "winning_bid": 1200,
  "history": [ ... ],                // 各轮的完整出价流程
  "narration": "Kai:All in ..."
}
```

---

## 7. CLI 命令变化

### 新增 / 变化

```bash
# 开局：加 --mode
python game.py start --session X --mode standard    # 标准模式
python game.py start --session X --mode quick       # 快速模式（默认）
python game.py start --session X                    # 默认 quick，向后兼容

# 出价：逻辑不变，但在标准模式下推进 sub_round 而不是整轮
python game.py bid --session X --amount 500

# 🆕 退出本件物品（标准模式专用）
python game.py withdraw --session X

# status 增强：显示 sub_round + 历史
python game.py status --session X
```

### `status` 标准模式输出

```
【第 2/4 件 · 单件 · sub_round 2/4】

🏺 民国白瓷茶壶
品类：瓷器 | 底价 $80

📜 历史：
  R1: 你 $300 | Kai $411 🥇 | 阿鬼 $275 | 老周头 退出

🟢 活跃：你, Kai, 阿鬼  
⚫ 已退：老周头
💰 当前最高：Kai $411
📈 本轮最低加价：$432（= $411 × 1.05）

⏱️ 请在 45 秒内 `bid --amount <金额>` 或 `withdraw`。
```

---

## 8. UX 流程样例

### 完整一件物品的玩家视角

```
【第 1/4 件 · 单件 · sub_round 1/4】

🏺 民国白瓷茶壶（瓷器）| 底价 $80

📌 线索
  · 同类拍品平均成交 $280
  · 品相 A，壶嘴有极小崩
  · 专家估价 $200-$450

⏱️ sub_round 1 独立判断阶段，无其他人出价信息。
   出价 ≥ 底价 $80 参与 / 直接 withdraw 退出。
   **碾压阈值**：本轮最高 ≥ 次高 × 1.8 可一次性拿下。

PS> python game.py bid --amount 300

📢 sub_round 1 揭晓：
  · Kai      $411 🥇
  · 你        $300
  · 阿鬼      $275
  · 老周头    退出

💬 老周头：「品相 B？老夫不伺候。」

⚖️ 碾压检查：$411 / $300 = 1.37 < 1.8 → 未触发。
   进入 sub_round 2（剩 3 人：你、Kai、阿鬼）。
   最低加价：$432。

─────────────────────────────
【第 1/4 件 · sub_round 2/4】

📌 线索（同上）
📜 历史：R1 最高 Kai $411

PS> python game.py bid --amount 480

📢 sub_round 2 揭晓：
  · 阿鬼     $620 🥇
  · Kai      $545
  · 你        $480

💬 阿鬼：「嘿嘿，这价儿，我觉得值。」

⚖️ 碾压检查：$620 / $545 = 1.14 < 1.5 → 未触发。
   进入 sub_round 3（剩 3 人）。
   最低加价：$651。

─────────────────────────────
【第 1/4 件 · sub_round 3/4】

PS> python game.py withdraw

📢 sub_round 3 揭晓：
  · 阿鬼     $820 🥇
  · Kai      $700
  · 你        退出

💬 Kai：「Damn，这东西突然变抢手了。」

⚖️ 碾压检查：$820 / $700 = 1.17 < 1.2 → 未触发。
   进入 sub_round 4 封口轮（剩 2 人：Kai、阿鬼）。

─────────────────────────────
【第 1/4 件 · sub_round 4/4 · 封口】

（玩家已退出，等 AI 出价）

📢 sub_round 4 揭晓（封口）：
  · 阿鬼     退出 🎭
  · Kai      $900 🏆

🏆 **Kai** 以 $900 拿下【民国白瓷茶壶】。真值 $300。

💬 阿鬼：「这货留给 Kai，我另有打算。嘿嘿。」

⚠️ Kai 接盘！$900 拿下真值 $300 的货，亏 $600。

💰 预算剩余：你 $2347 | 老周头 $2000 | Kai $1100 | 阿鬼 $2000

下一件：【清代粉彩瓷碗】即将开始…
```

**这场戏的信息量**：
- 阿鬼陷阱成功：他前三轮一路抬价到 $820，R4 立刻 withdraw，把 Kai 骗到 $900 接盘。
- 玩家正确判断了真值不值得，R3 退出保预算。
- Kai 的 FOMO 坑了自己 $600。

**这就是 AI 人设真正发挥作用的地方。v2 做不到这种戏。**

---

## 9. LLM 台词新触发点

v3 的多轮结构给 LLM 更多戏剧切入点：

| 触发场景 | 频次 | 人物 | 示例 |
|---|---|---|---|
| **开局** | 1/局 | 主持人 | 已有 |
| **R1 揭晓** | 1/件 | 某个 AI（中标/near-miss）| 已有 |
| **R2/R3 退出** 🆕 | 1–3/件 | 退出者 | "嘿嘿，这货诸位抢吧。" |
| **阿鬼陷阱 R4 撤退** 🆕 | 高频 | 阿鬼 | "这货留给 Kai，我另有打算。" |
| **物品最终揭晓** 🆕 | 1/件 | 某个 AI 或主持人 | "接盘侠有了！" |
| **终局总结** | 1/局 | 主持人 | 已有 |

**新增调用成本**：每件物品 +1–3 次 LLM = 一局 +5–10 次。总调用约 20 次/局 = 6000 tokens = ~¥0.004/局。仍然便宜。

---

## 10. 实现阶段

### Phase A：设计冻结 + 3.4 commit（**本次会话完成**）
- [x] 3.4 LLM 台词层
- [x] Kai 话痨机制
- [x] GAME_DESIGN_v3.md 冻结
- [ ] 更新主 README 路线图
- [ ] commit

### Phase B：v3 底层改造（~3 h）
1. **state.py**：加 `current_item_state` 字段、mode 字段、随机 budget/items 逻辑
2. **items.py / select_round_queue**：支持 4–5 件可变数量
3. **ai_bidders.py**：加 `decide_sub_round_action(item, ctx, history) -> ("bid", X) | ("withdraw",)` 接口（5 AI 各写一个）

### Phase C：game.py 重构（~2 h）
1. `cmd_start` 加 `--mode` 参数
2. `cmd_bid` / `cmd_withdraw` 分叉到 quick / standard 两条路径
3. `_resolve_sub_round`：碾压检查、退出处理、推进 sub_round

### Phase D：narration.py 扩展（~1 h）
1. R1 reveal / 中间 reveal / final reveal 三态模板
2. 历史出价表渲染
3. LLM 新触发点（退出台词、陷阱台词）

### Phase E：测试 + 平衡（~1.5 h）
1. 新测试：`test_sub_round_mechanics.py`、`test_squash_threshold.py`
2. 新 simulate 逻辑（multi-round）
3. 100 局跑平衡

### Phase F：更新文档 + commit v3（~30 min）
1. skills/auction_king/README.md 更新
2. TROUBLESHOOTING.md 新增条目（如果发现新坑）
3. commit + push

**总预计：~8 小时**，可拆成 2–3 次会话。

---

## 附录：设计常见疑问

**Q: R1 玩家为什么要"独立判断"？这和 AI 同时出价有区别吗？**
A: R1 所有人同时暗标，谁都看不到别人。R2 开始才揭晓 R1 结果。"独立判断"就是指 R1 没有他人信息可参考。

**Q: 玩家 R2 如果想加到低于 current_max 怎么办？**
A: 被拒。加价必须 ≥ `current_max × 1.05`。低于的话系统提示，要么加到合法值，要么 withdraw。

**Q: 阿鬼陷阱反噬了（自己被碾压）怎么办？**
A: 自己吃下。这是设计刻意留的风险——陷阱不是无代价的，阿鬼大约 10% 局数会把自己坑死。

**Q: 玩家怎么知道现在是 sub_round 几、最低加价是多少？**
A: 每次 `bid` 后输出的下一轮 header 会写清楚。也可以随时 `status` 查看。

**Q: 快速模式会废弃吗？**
A: 不会。快速模式保留作为"1 分钟体验版"，适合 demo、LinkedIn post、新玩家 onboarding。
