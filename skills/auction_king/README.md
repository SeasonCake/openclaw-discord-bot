# auction_king

**单人竞拍对局 skill** · 玩家 vs 5 AI 池随机抽 3 · OpenClaw skill · 支持 LLM 台词。

> 设计文档：
> - [GAME_DESIGN.md](./GAME_DESIGN.md) —— v2.0（快速模式的来源）
> - [GAME_DESIGN_v3.md](./GAME_DESIGN_v3.md) —— **v3.0（多轮竞价 + 碾压阈值 + AI 反应式策略）** 🆕 已冻结

---

## 阶段进度

- [x] **3.1** v2 设计冻结
- [x] **3.2a** 暗标核心跑通（5 AI 公式 + CLI + 15 单元测试 + 100 局 simulate）
- [x] **3.4** LLM 台词层：DeepSeek 主持人开场 / AI 中标反应 / 主持人终局总结 + 模板 fallback + 24 单元测试
- [x] **Kai 话痨机制**：领先 / 反超 / 接近领先时必出声，凸显 FOMO 人设
- [x] **v3 设计冻结**（多轮竞价）
- [x] **3.6a** Discord 集成 [SKILL.md](./SKILL.md)（LLM 路由 + stdout 透传）
- [ ] **3.6b** 部署 + Discord 端到端 + 录 demo
- [ ] **v3 实现**（~8 h，分 Phase B–F）
- [ ] **3.5** 图片资产
- [ ] **3.7** 实战 demo 录屏

---

## 当前可玩（快速模式，3.4）

### 环境变量

```powershell
# LLM 台词层（推荐开启，成本 ~¥0.002/局）
$env:DEEPSEEK_API_KEY = "sk-..."
$env:AUCTION_KING_USE_LLM = "1"

# 关闭 LLM 走纯模板
$env:AUCTION_KING_USE_LLM = "0"
```

### 命令行手玩

```powershell
python scripts\game.py start    --session my1 --seed 42 --force
python scripts\game.py status   --session my1
python scripts\game.py bid      --session my1 --amount 500
python scripts\game.py advance  --session my1                  # 超时/弃权推进
python scripts\game.py scoreboard --session my1                # 终局积分榜
```

### 自动模拟

```powershell
python scripts\game.py simulate --n-games 100 --human-strategy auto --seed 1
```

`--human-strategy`：`random` / `conservative` / `aggressive` / `auto`。

### 单元测试

```powershell
python -m pytest tests -v    # 39 tests: 15 AI 出价 + 24 LLM narrator
```

---

## v3 核心改动预览（设计已冻结，代码未实现）

| | **快速模式 (v2/3.4, quick)** | **标准模式 (v3, standard)** |
|---|---|---|
| 物品数 | 7 | 4–5（随机） |
| 每件轮数 | 1 | 1–4（动态结束） |
| 预算 | $2000 固定 | $2000–$3000 随机 |
| 碾压机制 | 无 | R1/R2/R3 碾压阈值 ×1.8 / ×1.5 / ×1.2 |
| 退出机制 | `--amount 0` = 弃权 | 支持 `withdraw` 退出本件 |
| AI 反应式 | 只在台词 | 决策层：陷阱抬价、FOMO 跟进、狙击装睡 |

细节见 [GAME_DESIGN_v3.md](./GAME_DESIGN_v3.md)。

---

## 平衡数据（3.2a 快速模式 · 100 局 simulate）

| 人机策略 | 玩家胜率 | 头部 AI | 尾部 AI |
|---|---|---|---|
| `auto` (est × 0.90) | **76%** | 阿鬼 20% / 老周头 2% / 艺姐 2% | Kai 0% / Miles 0% |
| `random` | 20% | **老周头 32%** / 阿鬼 31% | Kai 0% / Miles 2% |

**设计符合预期**：理性玩家强于 AI；乱出价被老炮 PUA；Kai 按设计永远亏钱。

v3 标准模式会在 Phase E 重新跑 100 局 simulate 验证。

---

## 目录结构（3.4 完成）

```
skills/auction_king/
├── GAME_DESIGN.md            v2 设计真相源
├── GAME_DESIGN_v3.md         v3 设计真相源（多轮竞价）
├── README.md                 你在看
├── SKILL.md                  （3.6 做，OpenClaw 集成）
├── data/
│   └── items.json            16 单件 + 3 仓库
├── scripts/
│   ├── game.py               CLI 入口
│   ├── ai_bidders.py         5 AI 人格公式（v3 将扩 decide_sub_round_action）
│   ├── items.py              数据类 + 加载
│   ├── state.py              session JSON I/O
│   ├── narration.py          模板台词 + LLM 挂钩
│   ├── llm_narrator.py       DeepSeek 客户端 + 人设卡 + 三类 prompt
│   └── scoring.py            终局积分 + LLM 主持人总结
├── state/                    运行时 session（gitignored）
├── assets/
│   ├── items/                （3.5 生成）
│   └── portraits/            （3.5 生成）
└── tests/
    ├── test_ai_bidders.py    15 tests
    └── test_llm_narrator.py  24 tests
```

---

## v3 实现路线（下次会话起）

| Phase | 工作内容 | 预估 |
|---|---|---|
| B | state + random budget/items + AI `decide_sub_round_action` × 5 | 3 h |
| C | `game.py` 重构 quick/standard 分叉 + `cmd_withdraw` + sub_round 推进 | 2 h |
| D | `narration.py` R1/中间/final 三态 + 退出台词 LLM prompt | 1 h |
| E | 新测试 + 平衡 simulate | 1.5 h |
| F | 文档更新 + commit | 0.5 h |
| **合计** | | **~8 h** |

**中间可切 3.5 / 3.6，不一定一气呵成**。
