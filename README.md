# OpenClaw Discord Bot (原 WeChat Bot)

个人 AI 助手项目：用 [OpenClaw](https://github.com/openclaw/openclaw) 框架在 Discord 里跑一个自定义 AI 代理，对接 DeepSeek API，逐步开发数据分析与交互式游戏类 skill。

> 原计划走微信（[ClawBot 微信插件](https://github.com/Tencent/openclaw-weixin)），插件仅支持 iOS，项目作者用 Android，改道 Discord。迁移后 OpenClaw skill 代码完全不用改——架构 channel 与 skill 解耦。

## 快速导航

- 📘 **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** —— 踩坑 & 教训，从 Node.js PATH 到 skill 触发，10 大类真实问题与修法。**想复刻这个项目的先看这个**。
- 🏗️ **[SETUP.md](./SETUP.md)** —— 阶段 1 理想路径（实际走的路比这更曲折，细节在 TROUBLESHOOTING）
- 🎯 **[PIVOT_TODO.md](./PIVOT_TODO.md)** —— 转行 EHS → 数据/AI 的简历改版 checklist

## 项目目标

1. **环境打通**：在本机跑通 OpenClaw，绑定 Discord，能在 Discord 里和 AI 对话。
2. **数据分析 Skill**：`csv_analyzer` —— 发 CSV 自动出 EDA 报告。
3. **交互游戏 Skill**：`auction_king` —— 单人版暗标竞拍游戏（玩家 vs 3 AI 对手），灵感来自 Steam 游戏 *BidKing 竞拍之王*。

## 技术栈

- **Runtime**: Node.js 23 + npm（安装在 `C:\Program Files\nodejs`）
- **AI Provider**: DeepSeek API (`deepseek/deepseek-chat`)
- **Skill 语言**: Python 3（csv_analyzer） / TypeScript（auction_king，阶段 3）
- **渠道**: Discord（微信 Android 暂不支持，后续如开放再加）
- **网络**: xlcloud VPN（TUN global 模式，Discord 要走代理）

## 当前进度 / Roadmap

- [x] **阶段 1**：环境打通
  - [x] 买 DeepSeek API key + 设置为 `DEEPSEEK_API_KEY` env var
  - [x] 安装 OpenClaw CLI 2026.4.15（`C:\Users\shenc\AppData\Roaming\npm`）
  - [x] 手写配置 `~/.openclaw/openclaw.json` 挂 DeepSeek provider + 默认模型
  - [x] `openclaw gateway` 前台启动（已撤销开机自启 + 火绒告警）
  - [x] CLI `openclaw agent --to +1xxx` 能收到 DeepSeek 回复（~2s）

- [x] **阶段 1.5**：Discord channel 打通
  - [x] Discord Developer Portal 建 application `openclaw_bidking`
  - [x] Reset Token + 打开 Message Content Intent + Server Members Intent
  - [x] OAuth2 邀请链接把 bot 拉进 `Qilindage` 服务器
  - [x] 设置 `DISCORD_BOT_TOKEN` env var + `plugins.allow` 加 discord
  - [x] `channels.discord.token` 引用 env var + `enabled=true`
  - [x] `channels.discord.groupPolicy=open`（放宽白名单）
  - [x] **bot 在 Discord 里上线 + 能正常 @ 对话** ✅

- [x] **阶段 2**：`csv_analyzer` skill ✅ **完结**
  - [x] skill 目录骨架
  - [x] Python 分析脚本 + sample 数据
  - [x] 安装到 `~/.openclaw/workspace/skills/csv_analyzer/`
  - [x] `openclaw skills list` 能看到 skill `ready` + source `openclaw-workspace`
  - [x] Python 依赖装进默认 `C:\Python313`（pandas 3.0, openpyxl, tabulate）
  - [x] 命令行手动跑 `analyze.py` 输出正常
  - [x] Discord 端到端打通：bot 能分析 CSV / Excel 附件
  - [x] SKILL.md v2：加强触发词 + 防编码重试 + 防幻觉
  - [x] **Bot 显式调用 skill**（在消息里能看到 `"根据技能描述，我需要使用 csv_analyzer 技能"`）
  - [x] 三段式回复（headline / findings / 下一步）按 SKILL.md v2 样式产出

### 阶段 2 成果沉淀

**Demo 素材**（可直接进简历）：
- `Global_super_store_datasource.xlsx`（7.67 MB，Meta Capstone 数据集，51,290 行 × 24 列）→ bot 给出地理/客户/产品/折扣/财务健康度/业务建议
- `features_one_hot.csv`（SpaceX 猎鹰 9 号数据，90 行 × 77 列）→ bot 识别出 one-hot 编码，推断 PayloadMass 是预测目标
- `sample.csv`（产品库存小样本）→ 基础 EDA

**关键技术发现**：
- OpenClaw Discord 附件下载路径：`C:\Users\shenc\.openclaw\media\inbound\<uuid>.<ext>`
- 新 Discord 频道 = 新 session，SKILL.md 修改无需重启 gateway 即可生效
- **千万别在消息里粘贴 CSV 文本内容**，会撑爆 context window（131k tokens）；只用附件
- 触发 skill 的最可靠姿势：**只附件 + 简短 prompt**，不要同时粘贴文本内容

- [ ] **阶段 3**：`auction_king` skill（单人竞拍对局 skill）
  - [x] **3.1** v2 设计冻结：[GAME_DESIGN.md](./skills/auction_king/GAME_DESIGN.md)（7 轮 / $2000 / 5 AI 抽 3）
  - [x] **3.2a** 暗标核心跑通：5 AI 公式 + CLI 完整游戏 + 15 单元测试 + 100 局 simulate ✅
  - [x] **3.4** LLM 台词层：DeepSeek 主持人开场 / AI 角色反应 / 主持人终局总结 + 模板 fallback + 24 单元测试 ✅
  - [x] **Kai 话痨机制**：Kai 领先/反超时必出声，让 FOMO 人设更鲜明 ✅
  - [x] **v3 设计冻结**：[GAME_DESIGN_v3.md](./skills/auction_king/GAME_DESIGN_v3.md) —— 多轮竞价 + 碾压阈值（1.8 / 1.5 / 1.2）+ AI 反应式策略 🆕
  - [ ] **v3 实现**：state + AI `decide_sub_round_action` + `cmd_withdraw` + narration 扩展（~8 h）
  - [ ] **3.5** 图片资产
  - [ ] **3.6** Discord 集成（quick + standard 两种模式）
  - [ ] **3.7** 实战 demo 录屏

### 阶段 3 阶段性成果（3.4 完成时）

**已落地**：
- 5 人格 AI 池（老周头 / Kai / 艺姐 / 阿鬼 / Miles）随机抽 3，确定性种子。
- 7 轮暗标单局可玩，CLI `start / bid / status / end / simulate` 齐全。
- DeepSeek LLM 台词层：开场 host 词 + 逐轮中标者角色台词 + 终局 host 总结；`DEEPSEEK_API_KEY` 缺失时 fallback 到模板，**不崩**。
- 39 单元测试（15 AI 出价 + 24 LLM narrator）全绿。

**设计已冻结、待实现（v3）**：
- **两种模式并存**：`quick`（当前 v2/3.4）和 `standard`（v3 多轮）。
- **多轮竞价**：每件物品最多 4 sub_round，每轮后揭晓出价并支持退出。
- **碾压阈值**：R1 ≥ 次高 ×1.8 / R2 ×1.5 / R3 ×1.2 立刻终结，让"孤注一掷"成为真实策略。
- **AI 反应式策略**：阿鬼陷阱前抬后撤、Miles 前装睡后狙击、Kai FOMO 跟进 —— 真正在决策层面展开，而不只是台词。

## 当前已知的小问题（不影响推进）

- Discord 回复延迟 ~30-60s（skill 调用时），比 CLI 直连慢。原因：TUN global 把 DeepSeek 也绕路了。
  - 可接受，开发期不优化。
  - 最终展示时可考虑 VPN 改 rule 模式 + DeepSeek 直连、Discord 走代理。
- 短时间内连发多条 @，bot 会合并成一个 thread 只回最后一条（OpenClaw 设计，不是 bug）。
- 同一个 Discord 频道长时间聊天会累积 session，粘贴大量文本会快速撑爆 DeepSeek 131k token 上限。  
  解决：`/new` 命令开新 session，或新建频道。

## 项目结构

```
openclaw-wechat-bot/
├── README.md                ← 你在看（项目入口）
├── TROUBLESHOOTING.md       ← 踩坑 & 教训（复刻项目必读）
├── SETUP.md                 ← 阶段 1 理想路径
├── PIVOT_TODO.md            ← 转行简历改版 checklist
├── requirements.txt         ← Python 依赖（给 skill 用）
├── .gitignore
└── skills/
    ├── csv_analyzer/        ← 阶段 2 完成
    │   ├── SKILL.md         ← OpenClaw skill 定义（v2 强触发词）
    │   ├── scripts/
    │   │   └── analyze.py   ← pandas EDA 脚本（编码回退 utf-8/gbk/latin-1）
    │   └── assets/
    │       └── sample.csv   ← 测试数据
    └── auction_king/        ← 阶段 3 进行中（3.4 完成 / v3 设计冻结）
        ├── GAME_DESIGN.md          ← v2 设计（快速模式来源）
        ├── GAME_DESIGN_v3.md       ← v3 设计：多轮竞价 + 碾压阈值 + AI 反应式策略 🆕
        ├── README.md              ← skill 内部进度 + 命令速查
        ├── data/items.json        ← 16 单件 + 3 仓库
        ├── scripts/               ← game.py + ai_bidders.py + llm_narrator.py + narration.py + scoring.py ...
        └── tests/                 ← 39 单元测试（15 AI 出价 + 24 LLM narrator）
```

## 日常启动流程

```powershell
# 1. 打开 xlcloud VPN，切 TUN global（Discord 走代理必需）
# 2. 开一个 PowerShell 窗口跑 gateway（前台）
openclaw gateway
# 保持这个窗口开着

# 3. 去 Discord Qilindage 服务器 @openclaw_bidking 开聊
#    - 拖附件，别粘贴 CSV 文本（会爆 context）
#    - 新任务用新频道（或 /new 开新 session）
```

## 下一步

**阶段 3：`auction_king` skill**（游戏类 skill）。参考 Roadmap。
