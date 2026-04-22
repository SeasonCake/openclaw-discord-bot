# auction_king — Game Design

**版本：** v2.0（2026-04-22 冻结）
**角色：** 开发期的唯一真相源。所有代码按这份文档实现，有分歧就改这份文档再改代码。
**v2 主要变化：** 7 轮 / $2000 / 5 选 3 AI / 加仓库拍卖（英式叫价）/ 加陷阱机制 / 时限递减。

---

## 1. 一句话定位

**单人混合拍卖博弈游戏**：玩家 vs 从 5 人池随机抽出的 3 个 AI 对手，在 **5 轮单件暗标 + 2 轮仓库英式叫价** 的混合赛制中，以"**剩余预算 + 物品真实价值之和**"最高者为胜。

灵感：Steam《BidKing 竞拍之王》+ 美剧《Storage Wars》+ 沪上老上海拍卖行文化。

---

## 2. 核心循环（Core Loop）

```
┌──────────────────────────────────────────────────────────────────┐
│  开局初始化                                                        │
│    · 从 5 AI 池随机抽 3 个对手 + 玩家 = 4 人局                     │
│    · 每人预算 $2000                                                │
│    · 生成 7 件拍品序列：5 单件 + 2 仓库（第 3、第 6 轮放仓库）     │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  第 N 轮，根据拍品类型分流：                                        │
│                                                                    │
│  类型 A（单件，暗标）:                                              │
│    ① 公布 [图片 + 品名 + 品类 + 底价 + 2-3 条线索]                  │
│    ② 时限 T_n 秒内，4 方同时暗标                                   │
│       · 3 AI 立即按人格算法出价                                     │
│       · 玩家 DM bot 提交出价                                        │
│    ③ 同时揭晓 4 方出价                                              │
│    ④ 最高者中标（并列随机）→ 扣预算 → LLM 台词                      │
│                                                                    │
│  类型 B（仓库，英式叫价）:                                          │
│    ① 公布 [仓库描述 + 可见部分线索 + 起拍价]                        │
│    ② 循环："谁加价？" 每人可选 加价X / 跟价 / 退出                  │
│       · 一旦退出不可再入                                            │
│       · 玩家通过频道回复 + / + 50 / out                             │
│       · AI 按策略决定（陷阱型触发逻辑在此生效）                     │
│    ③ 只剩 1 人时该人中标 → 扣预算 → 揭晓仓库清单                    │
└──────────────────────────────────────────────────────────────────┘
                              ↓ 循环 7 轮
┌──────────────────────────────────────────────────────────────────┐
│  终局揭晓                                                          │
│    · 披露全部 7 件/组拍品的 true_value                             │
│    · 四人最终得分 = 剩余预算 + Σ(所持物真值)                        │
│    · 排名 + ROI 榜单 + "最惨接盘" 奖                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 基础参数

| 项 | 值 | 说明 |
|---|---|---|
| 玩家数 | 4 | 1 人 + 3 AI（从 5 AI 池抽选）|
| 初始预算 | **$2000 / 人** | |
| 总轮数 | **7** | 5 单件 + 2 仓库 |
| 单件轮时限（递减）| 轮 1-2: **60s** / 轮 4-5: **45s** / 轮 7: **30s** | 递减压力感 |
| 仓库轮单步时限 | **30s** | 每次加价/退出决策 |
| 仓库加价幅度 | **$50** 起步，可选 $50 / $100 / $200 | |
| 出价下限（单件） | 底价 | 低于视为弃权 |
| 出价上限 | 剩余预算 | 超额无效 |
| 并列最高 | 随机抽取中标 | `random.choice`，seeded |

---

## 4. 拍品体系

### 4.1 两种拍品类型

| 类型 | 机制 | 数量（每局）| 价值区间 |
|---|---|---|---|
| **item**（单件） | 暗标 | 5 | true_value: $200–$1000 |
| **lot**（仓库组）| 英式叫价 | 2 | true_total: $500–$1500 |

### 4.2 单件拍品 Schema

```json
{
  "id": "item_001",
  "type": "item",
  "name": "清代粉彩瓷碗",
  "category": "瓷器",
  "true_value": 620,
  "base_price": 150,
  "description": "清中期民窑粉彩瓷碗，口径 15cm。",
  "hints": [
    "同类拍品上月平均成交 $550",
    "品相 B，底部有细微磕损",
    "专家估价 $400–$900"
  ],
  "image": "items/item_001.png"
}
```

**品类（7 种）**：`瓷器 / 玉器 / 书画 / 钟表 / 珠宝 / 家具 / 杂项`

### 4.3 仓库拍品 Schema

```json
{
  "id": "lot_001",
  "type": "lot",
  "name": "李氏家族遗产专场",
  "description": "老李家上世纪 60 年代留下的一批物件",
  "items_inside": [
    {"name": "青花大盘",   "category": "瓷器", "true_value": 320, "visible": true,  "note": "边缘有磕损"},
    {"name": "玉坠两枚",   "category": "玉器", "true_value": 180, "visible": false, "note": "品相尚可"},
    {"name": "民国银元 5", "category": "杂项", "true_value": 250, "visible": false, "note": null},
    {"name": "旧油画一幅", "category": "书画", "true_value": 100, "visible": true,  "note": "作者不详"}
  ],
  "true_total": 850,
  "base_price": 300,
  "hints": [
    "最显眼的是一件青花大盘 + 一幅旧油画",
    "家族口述估值 $600–$1000",
    "未全数开箱核验"
  ],
  "image": "lots/lot_001.png"
}
```

**关键字段**：

- `visible: true` 的物品 → 在线索里**会被描述**（"看得见")
- `visible: false` 的物品 → 完全隐藏，开箱才知道（"赌"的部分）
- `true_total` = Σ(`items_inside.true_value`)，计算终局分数时用

### 4.4 定价约束（保证可玩性）

- **单件**：`base_price ∈ [true_value × 0.20, true_value × 0.40]`
- **仓库**：
  - `base_price ∈ [true_total × 0.30, true_total × 0.50]`
  - 可见物品真值之和必须 ≥ `true_total × 0.40`（避免"所有宝贝全是隐藏"，玩家完全盲赌）
  - 可见物品真值之和必须 ≤ `true_total × 0.70`（避免"全揭示"，失去赌的刺激）

### 4.5 拍品库规模要求

- 单件 ≥ **25 件**（每局随机抽 5）
- 仓库 ≥ **8 个**（每局随机抽 2）

---

## 5. AI 对手池（5 人，每局抽 3）

**设计哲学**：
- 出价逻辑 **100% 确定性算法**（快、可复现、零 API 成本）
- 只用 LLM 生成**角色台词**（每回合 ≤ 1 次）
- 每局 AI 不同，**玩家记不住谁是谁**就输了一半 → 增加策略深度

### 5.1 估值函数（共用）

每个 AI 从 hints 解析估值 `est`：

```python
def estimate(item_or_lot, hints):
    # 优先级：专家区间 > 同类成交价 > 口述估值 > 底价兜底
    if "专家估价" in hints or "家族口述估值" in hints:
        (A, B) = parse_range(hints)
        est = (A + B) / 2
    elif "同类拍品" in hints or "上月成交" in hints:
        est = parse_amount(hints)
    else:
        est = base_price * 2.5
    return est
```

各 AI 在此基础上叠加**人格修正**。

### 5.2 角色 1：老周头（Conservative / 保守派）

**人设**：福建古董行老江湖，40 年经验，爱讲行话。

**暗标出价公式**：

```python
bid = est * 0.70
if item.category == "瓷器":                   # 专长品类
    bid *= 1.10
if remaining_budget < 600:                     # 后期收缩
    bid *= 0.8
if round_num >= 6 and remaining_budget > 1000: # 末期不得不花
    bid = est * 0.85
if bid < base_price:
    bid = 0                                    # 宁愿弃权
```

**仓库英式叫价策略**：

```python
walk_away_price = est * 0.70  # 瓷器品类 +10%
# 当前叫价超过 walk_away_price 立即退出
```

**台词风格**：福建腔行话。"年轻人啊"、"这玩意儿打眼了"、"老话讲捡漏要看眼色"。2 句话内。

### 5.3 角色 2：Kai（Aggressive / 激进派）

**人设**：硅谷回国创投人，年轻、FOMO 严重、爱中英混搭。

**暗标出价公式**：

```python
bid = est * 1.05 + random.randint(0, 50)
if round_num <= 2:                             # 前期抢货
    bid *= 1.15
if item.category in ["书画", "钟表"]:          # 他眼中的 "niche hot"
    bid *= 1.08
if round_num >= 5 and len(self.inventory) == 0: # 一件没中就失控
    bid *= 1.30
bid = min(bid, remaining_budget * 0.95)        # 能全 in 就全 in
```

**仓库英式叫价策略**：

```python
walk_away_price = est * 1.05
if round_num <= 2:
    walk_away_price *= 1.15
# 如果当前叫价在 [walk_away_price * 0.9, walk_away_price] → 继续跟
# 超过 walk_away_price → 退出
# 但若 len(self.inventory) == 0 且是第 6/7 轮 → walk_away_price *= 1.3（FOMO）
```

**台词风格**：中英夹杂、金融/创投词汇、自信到狂妄。"Let's go"、"FOMO"、"All in"、"这个 deal 不能错过"、"classic undervalued asset"。

### 5.4 角色 3：艺姐（Arbitrageur / 套利派）

**人设**：前苏富比行内人，40 岁，话不多但刀刀致命。

**暗标出价公式**：

```python
bid = est * 0.88 + random.gauss(0, 15)
if item.category in ["玉器", "书画"]:          # 专长
    bid = est * 1.05
if item.category in ["钟表", "珠宝"]:          # 不熟
    bid = est * 0.70
# 预算管理严格
max_per_round = remaining_budget / (total_rounds - round_num + 1) * 1.3
bid = min(bid, max_per_round)
```

**仓库英式叫价策略**：

```python
walk_away_price = est * 0.88  # 按品类构成再微调
```

**台词风格**：冷静、精准、毒舌。短句。"行里人都知道这东西品相不行"、"底价本身就是笑话"、**会直接点评其他 AI**（"老周头又在装行家"、"Kai 永远学不会冷静"）。

### 5.5 🆕 角色 4：阿鬼（Trap / 陷阱派）

**人设**：江湖传闻"收藏局局长"，外表光鲜讲究，专设局坑同场买家。实际上他**自己从不赚最多**，但常让别人赔最多。

**特殊能力 🗝️**：
- **仓库拍卖时**，他能看到 `true_total × [0.9, 1.1]` 之间的一个"内部估值" `trap_est`
- **单件拍品时**，他能看到 `true_value × [0.85, 1.15]` 之间的 `trap_est`
- **代价**：每局有 **20%** 概率他的"情报"是完全错的（`trap_est = true * random(0.5, 1.8)`），此时他可能反被坑（博弈平衡）

**暗标出价公式**（精准杀手模式）：

```python
bid = trap_est * 0.92                          # 极精准、略低价
if 本局概率性装输(probability=0.15):            # 每局 15% 轮次装
    bid = est * 0.55                           # 故意出低让别人
```

**仓库英式叫价策略（陷阱核心）🎯**：

```python
# 阶段 1：诱饵阶段 (current_price < trap_est * 0.85)
#   → 持续加价 +50（积极，诱导别人跟进）
# 阶段 2：托价阶段 (trap_est * 0.85 ≤ current_price < trap_est * 1.05)
#   → 每次加价，轮流大小：+50 / +100 / +200 随机
#   → 说台词暗示 "这批货我志在必得"
# 阶段 3：危险阶段 (trap_est * 1.05 ≤ current_price < trap_est * 1.20)
#   → 随机决定：继续加 vs 退出
#     · 如果只剩 2 人（含自己）且对方是玩家 → 60% 概率退出（陷阱成功）
#     · 其他情况 → 40% 概率退出
# 阶段 4：止损阶段 (current_price ≥ trap_est * 1.20)
#   → 必退出
```

**关键反制（陷阱的代价）**：

- 如果所有人**不跟**他的抬价，他的诱饵就咽进肚里——当轮到他时，如果只有他一个人在叫，那件物品就是他买单了（用真实估值算可能亏或赚）
- 若 `trap_est` 被那 20% 概率误导（比真实低很多），他可能在"安全区间"死撑，最后以高于 true_value 的价格接盘

**台词风格**：油腻、华丽、胸有成竹。"这批货我心里有数"、"诸位不必抢"、"老夫志在必得"。**退出时要说**（这是陷阱的戏剧性）："嗯……还是算了吧。" / "想想还是留给别人。" / "气氛到了，价也上了，老夫撤。"

### 5.6 🆕 角色 5：Miles（Sniper / 狙击派）

**人设**：前华尔街量化交易员，冷静、延迟启动。别人狂欢他不动，关键几轮突然激进。

**暗标出价公式**：

```python
if round_num <= 3:
    bid = base_price + random.randint(0, 30)   # 装死，出象征性底价
elif round_num <= 5:
    bid = est * 0.85                           # 正常出手
else:  # round 6-7，狙击期
    bid = est * 1.15                           # 激进
    if item.category == "杂项":                 # 他的偏好（数据狗喜欢数学品）
        bid *= 1.20
```

**仓库英式叫价策略**：

```python
if round_num <= 3:
    walk_away_price = base_price * 1.5         # 基本不参与
else:
    walk_away_price = est * 1.10               # 后期正常抢
```

**台词风格**：冷静、理性、数据派。"running my numbers"、"EV 不够，pass"、"终于出现一个 mispriced asset"。**一般不说话**，一旦开口就是精准吐槽（尤其吐槽 Kai 的非理性）。

### 5.7 5 选 3 抽签规则

```python
def draft_opponents(seed):
    random.seed(seed)
    pool = ["老周头", "Kai", "艺姐", "阿鬼", "Miles"]
    return random.sample(pool, 3)
```

每局开始时抽一次，全程固定。

### 5.8 AI 台词调度

**v1 简化**：每回合**只有 1 人说话**（LLM 1 次调用）。发言者选择：

1. **中标者**（60% 权重）：炫耀 / 满意
2. **出价第二接近中标者**（20%）：可惜 / 不甘
3. **艺姐**（若在场，10%）：毒舌点评
4. **阿鬼**（若在场 + 本轮是仓库且他退出了，10%）：戏剧性退出台词

仓库英式叫价阶段：**阿鬼在关键退出时必说一句台词**（额外 +1 次 LLM 调用，最多每局 2 次）。

---

## 6. 得分与胜负

### 6.1 终局得分

```
final_score = remaining_budget + Σ(物品/仓库的 true_value)
           = 2000 + 总利润（净值）
```

### 6.2 排名

- 按 `final_score` 降序
- 并列第一：并列冠军
- 额外榜单：
  - **最佳 ROI**（单品/仓库 利润率最高）
  - **最惨接盘**（单品/仓库 亏损最多）
  - **陷阱受害者**（本局阿鬼在场时，若有玩家接了阿鬼"退出"后的盘且亏钱，标注）

### 6.3 预期胜率（设计目标）

100 局 simulate 的四人平均得分**期望排序**（当随机玩家用 `est × 0.90` 策略）：

```
艺姐 ≈ 理性玩家 > 阿鬼 > 老周头 ≈ Miles > Kai
```

若玩家策略差，Kai / 阿鬼 会赢。

---

## 7. 游戏状态 Schema

```json
{
  "session_id": "sess_a3f2b1",
  "started_at": "2026-04-22T20:00:00+08:00",
  "seed": 42,
  "config": {
    "initial_budget": 2000,
    "max_rounds": 7,
    "time_limits": {"early": 60, "mid": 45, "late": 30},
    "lot_rounds": [3, 6]
  },
  "active_ais": ["老周头", "艺姐", "阿鬼"],
  "players": {
    "human":       {"display": "你",     "budget": 2000, "inventory": []},
    "老周头":      {"display": "老周头", "budget": 2000, "inventory": []},
    "艺姐":        {"display": "艺姐",   "budget": 2000, "inventory": []},
    "阿鬼":        {"display": "阿鬼",   "budget": 2000, "inventory": [], "trap_accuracy": 0.8}
  },
  "items_queue": ["item_003", "item_017", "lot_002", "item_008", "item_022", "lot_005", "item_011"],
  "items_done": [
    {
      "item_id": "item_003",
      "type": "item",
      "round": 1,
      "bids": {"human": 500, "老周头": 420, "艺姐": 510, "阿鬼": 485},
      "winner": "艺姐",
      "winning_bid": 510,
      "true_value": 620,
      "narration": "艺姐轻轻点头，没说话。"
    }
  ],
  "current_round": 2,
  "current_item": "item_017",
  "current_type": "item",
  "current_bids": {
    "老周头": 140,
    "艺姐":   195,
    "阿鬼":   208
  },
  "current_lot_state": null,
  "status": "awaiting_human_bid",
  "status_deadline": "2026-04-22T20:03:45+08:00",
  "log": [
    "20:00:00 game started with seed 42, opponents: 老周头, 艺姐, 阿鬼",
    "20:00:05 round 1: item_003 presented",
    "..."
  ]
}
```

### 仓库轮的 `current_lot_state`

```json
{
  "current_price": 450,
  "highest_bidder": "Kai",
  "active_bidders": ["human", "老周头", "Kai"],      // 没退出的
  "dropped_bidders": ["艺姐"],
  "bid_history": [
    {"bidder": "老周头", "action": "raise", "amount": 300, "new_price": 300},
    {"bidder": "艺姐",   "action": "raise", "amount": 50,  "new_price": 350},
    {"bidder": "Kai",    "action": "raise", "amount": 100, "new_price": 450},
    {"bidder": "艺姐",   "action": "quit"}
  ],
  "next_to_act": "human",
  "step_deadline": "2026-04-22T20:02:15+08:00"
}
```

---

## 8. 状态机

### 8.1 单件轮

```
in_round_start → presenting_item → awaiting_bids → revealing → narration → scoring_round → next_round
```

### 8.2 仓库轮

```
in_round_start → presenting_lot → lot_bidding_loop → lot_won → opening_lot → scoring_round → next_round
```

`lot_bidding_loop` 内部：

```
while len(active_bidders) > 1:
    next_bidder = rotate(active_bidders)
    await_decision(next_bidder)  # raise_50 / raise_100 / raise_200 / quit
    update_state
winner = active_bidders[0]
```

---

## 9. CLI 接口（game.py）

```bash
# 开局
python game.py start --session <id> [--seed 42] [--budget 2000] [--rounds 7]

# 查看状态 (markdown 输出，给 skill 转发)
python game.py status --session <id>

# 单件暗标出价
python game.py bid --session <id> --amount 220

# 仓库英式叫价操作
python game.py raise --session <id> --amount 50      # 加价
python game.py pass --session <id>                   # 等别人（仅部分规则可用）
python game.py quit --session <id>                   # 退出

# 强制推进（AI 已出 / 超时）
python game.py advance --session <id>

# 终局积分榜
python game.py scoreboard --session <id>

# 一键自动模拟（调参/回归测试）
python game.py simulate --session <id> \
    [--human-strategy random|conservative|aggressive|auto] \
    [--n-games 100]
```

所有命令**输出 Markdown 到 stdout**，便于 skill 转发给 Discord。

---

## 10. Discord UX 流程

### 10.1 开局

玩家：`@openclaw_bidking 开始竞拍`

bot：
```
🏛️ **竞拍之夜开始！**

📋 规则：7 轮（5 暗标 + 2 仓库英式叫价），初始预算 $2000。
🎭 本局对手（5 选 3 随机）：

  · **艺姐** — 前苏富比行内人，冷静精准
  · **阿鬼** — 江湖"收藏局局长"，行动诡异
  · **Miles** — 前华尔街量化交易员，后期发力

准备好了吗？第 1 轮马上开始...
```

### 10.2 单件轮（暗标）

```
【第 1/7 轮 · 单件】

[图片：item_003.png]

🏺 **清代粉彩瓷碗**
品类：瓷器 | 底价 $150

📌 线索
  · 同类拍品上月平均成交 $550
  · 品相 B，底部有细微磕损
  · 专家估价 $400–$900

⏱️ 请在 60 秒内 DM 我你的出价（数字即可，如 `520`）
不出价就 DM `pass`。
```

玩家 DM：`520`

bot DM：
```
✅ 收到出价 $520。等待其他买家...
```

bot（公共频道，揭晓）：
```
📢 揭晓第 1 轮出价：
  · 艺姐   $530 🏆
  · 阿鬼   $485
  · 你     $520
  · Miles  $150 （狙击模式待机）

🏆 **艺姐** 以 $530 拿下【清代粉彩瓷碗】。

💬 艺姐轻轻点头，没说话。

💰 预算剩余：艺姐 $1470 | 阿鬼 $2000 | Miles $2000 | 你 $2000

第 2/7 轮 5 秒后开始...
```

### 10.3 仓库轮（英式叫价）

```
【第 3/7 轮 · 仓库 🎁】

[图片：lot_002.png]

📦 **李氏家族遗产专场**
起拍价 $300 | 加价幅度 ≥$50

📌 线索
  · 最显眼的是一件青花大盘 + 一幅旧油画
  · 家族口述估值 $600–$1000
  · 未全数开箱核验

👀 可见物品：
  · 青花大盘（瓷器，边缘有磕损）
  · 旧油画一幅（书画，作者不详）
  · ……还有其他 **2 件** 隐藏物品

⏱️ 每一步 30 秒。**老周头**先叫价。
```

bot 按轮次逐步推进：

```
📣 老周头加价 $50  → 当前 $300
   老周头：「这批货看起来有点意思……」

📣 Miles：「running numbers... pass for now」 → 老周头仍持有

📣 阿鬼加价 $100 → 当前 $400
   阿鬼：「这批货我心里有数，诸位不必抢。」

📣 **轮到你**。当前 $400，剩余预算 $2000。
   回复：`+50` / `+100` / `+200` / `out`
   ⏱️ 30 秒...
```

玩家：`+100`

```
📣 你加价 $100 → 当前 $500

📣 老周头：「不跟了，老夫心里没底。」 → 老周头退出

📣 阿鬼加价 $200 → 当前 $700
   阿鬼：「气氛刚到位，加一点。」

📣 **轮到你**。当前 $700，剩余预算 $2000。
```

玩家：`+50`

```
📣 你加价 $50 → 当前 $750

📣 阿鬼：「嗯……还是算了吧。」 → **阿鬼退出** 🚨

🏆 **你** 以 $750 拿下【李氏家族遗产专场】！

开箱 📦：
  · 青花大盘        真值 $320
  · 旧油画一幅      真值 $100
  · 玉坠两枚        真值 $180  （隐藏）
  · 民国银元 5 枚   真值 $250  （隐藏）

仓库真实总价：**$850**
你花了 $750，净利 **+$100** 🎉

💰 预算剩余：老周头 $2000 | 阿鬼 $2000 | 你 $1250

第 4/7 轮 5 秒后开始...
```

### 10.4 终局

```
🏛️ **拍卖结束！**

📊 真实价值复盘：
  1. 清代粉彩瓷碗   真值 $620 → 艺姐 $530 买入 (+$90)
  2. ...
  3. 李氏家族遗产   真值 $850 → 你   $750 买入 (+$100)
  4. ...

🏆 **最终排名**
  🥇 你     $2450  (+$450)  🎯 最佳 ROI: 李氏遗产 +$100
  🥈 艺姐   $2310  (+$310)
  🥉 阿鬼   $2000  (±$0)    💡 本局陷阱未得手
  4️⃣ Miles  $1890  (−$110)  😱 最惨接盘

🎮 GG！想再来一局就 @我 `再来一局`。
```

---

## 11. LLM 调用预算

| 场景 | 调用次数 | 每次 tokens | 总 tokens/局 |
|---|---|---|---|
| 开局介绍 | 1 | ~300 | 300 |
| 单件轮台词 | 5 | ~120 | 600 |
| 仓库轮台词 | 2 × (3-6 条) | ~100 | 1000 |
| 阿鬼退出戏剧性台词 | 2（若在场）| ~80 | 160 |
| 终局复盘 | 1 | ~400 | 400 |
| **合计** | **~15** | | **~2500 tokens** |

DeepSeek 定价 → **每局 < ¥0.02**。

---

## 12. 扩展点（v2+，明确不做）

- [ ] 多人真人模式
- [ ] 动态定价（true_value 受历史影响）
- [ ] AI 之间的明面联盟/暗盘
- [ ] 连续赛季 / 累计段位
- [ ] Slash command / Modal 出价界面（依赖 OpenClaw 原生支持）
- [ ] 可视化倒计时条（Discord 无原生）
- [ ] 玩家也能做"陷阱"（复杂度爆炸）

---

## 13. v1 Done 判定（清单）

开发期以此为准，全部满足才视为 v1 完成：

- [ ] `data/items.json` ≥ 25 件单件 + ≥ 8 个仓库，满足定价约束
- [ ] 5 个 AI 角色公式全部实现并单元测试
- [ ] `game.py simulate --n-games 100` 不 crash，输出分布符合设计目标（§ 6.3）
- [ ] `game.py` 全 CLI 命令可跑
- [ ] 仓库轮英式叫价状态机正确处理：并列、超时、退出、重入拒绝
- [ ] 阿鬼陷阱机制 simulate 下观察到：**诱敌成功** / **诱敌失败反被坑** 两种结局都出现过
- [ ] SKILL.md 触发词 + DM 出价 + 频道叫价 规则清晰
- [ ] Discord 端完整玩一局 7 轮（可无图片）
- [ ] 1 局实战截图 / GIF 存档

---

*Design frozen by Qilin on 2026-04-22 (v2.0). All subsequent code must conform. Revisions require bumping version.*
