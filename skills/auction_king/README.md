# auction_king

**单人暗标拍卖博弈游戏** · 玩家 vs 5 AI 池随机抽 3 · OpenClaw skill。

> 详细设计见 [GAME_DESIGN.md](./GAME_DESIGN.md)（v2.0）。

## 阶段进度

- [x] **3.1** 设计冻结（`GAME_DESIGN.md` v2.0）
- [x] **3.2a** 暗标核心跑通
- [ ] **3.2b** 仓库轮英式叫价 + 阿鬼陷阱分阶段逻辑
- [ ] **3.3** 平衡调参（AI 胜率分布达到设计目标 §6.3）
- [ ] **3.4** LLM 台词层（替换 `narration.py` 模板 → DeepSeek）
- [ ] **3.5** 图片资产（`assets/items/` + `assets/portraits/`）
- [ ] **3.6** Discord 集成（`SKILL.md` + DM 出价流程）
- [ ] **3.7** 实战录像 / GIF demo

## 当前可玩

### 命令行手玩

```powershell
# 开局（seed 固定可复现，--force 覆盖旧 session）
python scripts\game.py start --session my1 --seed 42 --force

# 看状态（每轮前）
python scripts\game.py status --session my1

# 出价（--amount 0 表示弃权）
python scripts\game.py bid --session my1 --amount 500

# 超时自动推进（AI 照常出价，玩家记 $0）
python scripts\game.py advance --session my1

# 终局积分榜
python scripts\game.py scoreboard --session my1
```

### 自动模拟（AI 平衡回归）

```powershell
python scripts\game.py simulate --n-games 100 --human-strategy auto --seed 1
```

`--human-strategy` 可选：`random` / `conservative` / `aggressive` / `auto`。

### 单元测试

```powershell
python -m pytest tests -v
```

## 3.2a 观察到的 AI 平衡（100 局 simulate）

| 人机策略 | 玩家胜率 | 头部 AI | 尾部 AI |
|---|---|---|---|
| `auto` (est×0.90) | **76%** | 阿鬼 20% / 老周头 2% / 艺姐 2% | Kai 0% / Miles 0% |
| `random` | 20% | **老周头 32%** / 阿鬼 31% | Kai 0% / Miles 2% |

**结论**：理性玩家显著强于 AI（符合设计目标 §6.3）；乱出价被老周头 / 阿鬼 / 艺姐 PUA 到还钱。Kai 按设计永远拿 0 胜——他是"溢价王"，买到东西也亏钱。

## 目录结构

```
skills/auction_king/
├── GAME_DESIGN.md       设计真相源
├── README.md            你在看
├── SKILL.md             （3.6 做，OpenClaw 集成）
├── data/
│   └── items.json       16 单件 + 3 仓库
├── scripts/
│   ├── game.py          CLI 入口
│   ├── ai_bidders.py    5 AI 人格公式
│   ├── items.py         数据类 + 加载
│   ├── state.py         session JSON I/O
│   ├── narration.py     台词模板（3.4 会替换为 LLM）
│   └── scoring.py       终局积分
├── state/               运行时 session（gitignored）
├── assets/
│   ├── items/           （3.5 生成）
│   └── portraits/       （3.5 生成）
└── tests/
    └── test_ai_bidders.py
```

## 3.2b 规划（下一步）

1. **仓库英式叫价状态机**
   - 每步 30s，每人轮流 `raise_50` / `raise_100` / `raise_200` / `quit`
   - 新命令：`game.py raise --session X --amount 100` / `game.py quit --session X`
   - 新 `current_lot_state` 字段（active_bidders / bid_history）

2. **阿鬼陷阱分阶段**
   - 阶段 1/2/3/4 的行为树（GAME_DESIGN §5.5）
   - 阶段转换时触发戏剧性台词
   - simulate 100 局统计陷阱"诱敌成功" vs "自坑" 比例

3. **拍品库扩展**
   - 单件从 16 扩到 25+
   - 仓库从 3 扩到 8+
   - 保证 100 局随机不重复的 variance

4. **平衡调参**
   - 若 Kai / Miles 完全打不到胜率（0%），可微调数值
   - 目标：100 局中每 AI 至少有几次胜利作为"惊喜"
