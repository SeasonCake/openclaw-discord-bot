# 转行 TODO: EHS → 数据 / AI

**决策时间**：2026-04 开启本项目时确认
**决策内容**：彻底脱离 EHS 方向，转数据分析 / AI 应用开发方向。
**原则**：EHS 工作经历**真实存在**，保留事实，但**叙事重心**全部转向数据/工程能力。EHS 只作为"应用场景"带过，不作主语。

---

## 📄 简历改版清单（下次改简历时一次性处理）

### 1. 求职意向行
- **当前**：`EHS 相关岗位 / 初级数据分析 / 数据运营`
- **目标**：删除"EHS 相关岗位"，改为 → `初级数据分析 / 数据工程 / AI 应用开发`

### 2. 个人总结（Professional Summary）
- **当前首句**：「拥有2年+新能源头部企业（CATL系）EHS管理经验...」
- **改写方向**：首句主体改为"数据自动化与分析经验"，EHS 放从句里
  - 示例：「拥有 2 年+ 制造业数据自动化与分析经验，基于 Python/SQL 主导过承包商准入自动化、EHS 数据可视化等数据工程项目...」

### 3. 工作经历 bullets 取舍

**宁波普勤时代（CBL / 印尼 BULI）**：
- ✅ **保留**：`EHS 数据可视化与风险监控系统 (Python/Plotly)` ← 强数据项目
- ⚠️ **压缩**：`EHS 体系建设与跨国知识库` ← 体系建设偏管理，压成 1-2 句强调"脚本辅助构建知识库"
- ❌ **删除**：`应急响应 / 大型消防应急演练` ← 与数据方向无关

**宁德邦普（BRUNP）**：
- ✅ **保留**：`承包商准入自动化系统 (Python)` ← 硬核数据项目，核心卖点
- ⚠️ **压缩**：`跨部门安环培训体系构建` ← 压成 1 行带过
- ❌ **删除**：`厂区级应急管理与疏散`
- ❌ **删除**：`BBS 视频拍摄小组（敏捷方法）` ← 与目标岗无关

### 4. 项目经历
- **项目 1「工业安全 EHS 智能管理系统」** → 重命名为 `工业数据提效工具集 (EHS 场景)`，把 EHS 降到括号
- **项目 2「SpaceX 猎鹰 9 号」** → 保留不动
- **新增项目 3** ✅ 已具备可写条件：`OpenClaw AI 助手 Discord Bot + 自定义 Skills` —— 2026.04 完成阶段 1/2
  - **一句话描述**：基于 OpenClaw 开源 Agent 框架 + DeepSeek API 搭建 Discord AI 助手，设计并实现自定义 Python Skill 完成数据文件自动 EDA 分析。
  - **技术栈**：OpenClaw / Node.js 23 / Python 3.13 / pandas / DeepSeek API / Discord Bot API
  - **关键成果**：bot 上线后在 Discord 中可自动触发 `csv_analyzer` skill，分析 1MB~10MB 级 CSV/Excel 文件（已测 SpaceX 90×77 one-hot 数据、Meta Capstone 51k 行销售数据），输出三段式业务级报告。
  - **工程化亮点**：SKILL.md 强触发词设计、编码回退机制（utf-8/gbk/latin-1）、session context 管理、env var secret 隔离、完整踩坑文档（TROUBLESHOOTING.md 10 大类）
  - **阶段 3（auction_king）完成后再补一句**：设计并实现 Discord 内多 AI 对手暗标竞拍游戏。
- **可选新增项目 4**：Meta DB Engineer Capstone（Global Super Store 数据建模 + Tableau）独立挂出

### 5. 专业技能分块调整
- ❌ **删除整行**：`EHS 领域知识：ISO 45001/14001、GB/AQ、双重预防机制、Hazop`
- ✅ **新增整行**：`AI / LLM 应用：LLM Agent 框架 (OpenClaw), Prompt Engineering, 自定义 Skill 开发, DeepSeek/OpenAI API 集成`
- ✅ **保留**：数据分析与编程、数据库设计与建模、工具与平台、软技能

### 6. 证书与奖项
- ✅ **保留**：Meta DB Engineer, IBM Data Science, Python for Everybody
- ❌ **删除**：`企业安全生产管理员证, 急救员证` ← 与目标岗无关
- ⚠️ **酌情保留**：`宁德市天湖人才` ← 综合素质体现，可留
- ⚠️ **压成一行**：`邦青优秀个人, 最佳潜力新人`

---

## 🏗 项目补强进度

- [x] **阶段 1**：OpenClaw 环境打通 ✅ 2026.04.22
- [x] **阶段 1.5**：~~ClawBot WeChat~~（Android 不支持）→ 改 Discord channel 打通 ✅ 2026.04.22
- [x] **阶段 2**：`csv_analyzer` skill 在 Discord 里可触发 + 返回正确 EDA 报告 ✅ 2026.04.22
- [ ] **阶段 3**：`auction_king` 游戏 skill（单人 + 3 AI 对手）
- [ ] **可选阶段 4**：`text_to_sql` skill（用 Meta capstone 的 Global Super Store 数据库）
- [ ] Meta DB Engineer Capstone repo 更新 README + 加截图
- [ ] Global Super Store Tableau 仪表盘截图整理
- [ ] 本项目 TROUBLESHOOTING.md + README + skills 推 GitHub（考虑独立 repo 名：`openclaw-discord-bot` 或 `openclaw-data-skills`）

---

## 🌐 外部平台同步

- [ ] **LinkedIn**：岗位方向改为"Data Analyst / AI Engineer"，skill tags 同步
- [ ] **GitHub 个人简介**：移除 EHS 措辞，强调数据 + AI
- [ ] **Coursera 主页**（如果分享）：Meta 证书 pin 到最显眼位置

---

## 📝 笔记

每次完成项目里程碑或简历改动时，来更新这个文件的 checklist。等所有项目做完，这份清单也就同步走完了一轮简历 + 全平台的转型。
