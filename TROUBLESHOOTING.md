# Troubleshooting & Lessons Learned

> 这份文件是这个项目从零到跑通整条 Discord + DeepSeek + Custom Skill 链路过程中**真实踩过的坑**。按"出场顺序 + 分类"整理，写给未来的自己 + 想复刻这条链路的同学。
>
> 技术栈：Windows 11 / PowerShell 7 / Node.js 23 / Python 3.13 / OpenClaw 2026.4.15 / DeepSeek API / Discord / Anaconda 共存的 dev 环境。

## 目录

1. [Node.js / PATH 纠缠](#1-nodejs--path-纠缠)
2. [API Key 的两次安全事故](#2-api-key-的两次安全事故)
3. [OpenClaw 配置：交互式命令集体卡死](#3-openclaw-配置交互式命令集体卡死)
4. [Gateway 三种启动姿势](#4-gateway-三种启动姿势)
5. [Discord 集成的四个隐形开关](#5-discord-集成的四个隐形开关)
6. [VPN 模式切换与 Node.js 进程](#6-vpn-模式切换与-nodejs-进程)
7. [Skill 开发：位置、Python、触发词](#7-skill-开发位置python触发词)
8. [Discord 使用 Gotchas](#8-discord-使用-gotchas)
9. [Windows 11 专属坑](#9-windows-11-专属坑)
10. [调试速查表](#10-调试速查表)

---

## 1. Node.js / PATH 纠缠

### 1.1 Anaconda 的 node 抢占 PATH

**症状**：

```powershell
PS> openclaw --version
openclaw: Node.js v22.12+ is required (current: v20.17.0).
PS> where.exe node
C:\Users\shenc\anaconda3\node.exe         ← 被它抢了
C:\Program Files\nodejs\node.exe
```

**原因**：Anaconda 默认把 `conda-forge::nodejs` 塞进了它自己的 bin 目录，而 Anaconda 的 PATH 条目在 Windows 系统 nodejs 之前。Anaconda 那份 node 是 v20，OpenClaw 要 v22.14+。

**修法（两步走）**：

1. **临时**（当前会话）：
   ```powershell
   $env:Path = "C:\Program Files\nodejs;" + $env:Path
   ```

2. **永久**：重命名 Anaconda 的 node.exe，让 PATH 查找自动跳过：
   ```powershell
   Rename-Item "C:\Users\shenc\anaconda3\node.exe" "node-conda.exe"
   ```

**教训**：在 Windows 上同时有 Anaconda + 独立 Node.js 时，**两者会为 `node` / `npm` 全局指挥权打架**。永久解法是改名或从 Anaconda 卸掉 node。

### 1.2 全局 npm 装错 prefix

**症状**：修好 PATH 之后 `openclaw --version` 还是报老版本：

```
openclaw: Node.js v22.12+ is required (current: v20.17.0).
```

**原因**：之前 `npm install -g openclaw` 是**用 Anaconda 的 npm** 跑的，装到了 Anaconda 的全局 prefix。launcher 脚本被硬编码成用 Anaconda 的 node。切 PATH 让 `node` 变新版，但 `openclaw` 的 shebang 还是指向老 node。

**修法**：

```powershell
# 用正确的 npm（系统级 Node 的）再装一次，覆盖原来的 launcher
npm install -g openclaw@latest

# 清理 Anaconda 那份（避免以后又被抢）
& "C:\Users\shenc\anaconda3\npm.cmd" uninstall -g openclaw
```

**教训**：`where.exe npm` 检查，如果有多个，**认清当前窗口 `npm` 是哪一个**再 install。

---

## 2. API Key 的两次安全事故

### 2.1 Key 被贴进 IDE 聊天

**原因**：调试过程中我（用户）直接把 `sk-...` 发给了 AI 助手。虽然只有我和 AI 看到，但 AI 的 chat 历史是持久化的，等于明文存档。

**教训**：
- **永远不要把 API key 贴到 AI 对话框、git commit、论坛提问里**
- 正确做法：Key 保存到 env var 或密码管理器，和 AI / 脚本打交道时只引用变量名
- 真出事了：立即去 provider 后台 revoke key，生成新的

### 2.2 env var 尾部隐藏换行 → curl 报 invalid header

**症状**：

```powershell
PS> curl.exe -sS "https://api.deepseek.com/v1/models" -H "Authorization: Bearer $env:DEEPSEEK_API_KEY"
invalid header:R0VUIC92MS9tb2RlbHMgSFRUUC8xLjENCkhvc3Q6IGFwaS5kZWVwc2Vlay5jb20NClVzZXItQWdlbnQ6...
```

**诊断**：把 base64 解出来，拼出原 HTTP 请求，看到：

```
Authorization: Bearer sk-20912a85...\n\r\n\r\n
                                    ↑↑ 这里只有 \n，不是 \r\n
```

Authorization 头末尾是 `\n`（LF）而非 `\r\n`（CRLF）→ 请求畸形 → 服务端拒收。

**根因**：env var 里存的 key 末尾带了个换行符，可能来自：
- 复制 key 时连带粘了尾部空白
- PowerShell here-string 设置时多了 newline

**修法**：设置时强制 `.Trim()`：

```powershell
[Environment]::SetEnvironmentVariable(
    "DEEPSEEK_API_KEY",
    "<key>".Trim(),
    "User"
)
# 关闭当前窗口 → 新开 → 验证长度
$env:DEEPSEEK_API_KEY.Length   # DeepSeek key 标准长度 = 35
```

**教训**：env var 存敏感凭证时**必须 Trim()**。验证长度是最简单的健全性检查（`sk-` + 32 hex = 35）。

---

## 3. OpenClaw 配置：交互式命令集体卡死

### 3.1 onboard / setup --non-interactive 都挂

**症状**：

```powershell
PS> openclaw onboard
🦞 OpenClaw 2026.4.15 ...
（卡死，无任何输出）

PS> openclaw setup --non-interactive --accept-risk --mode local
（同样卡死）
```

**推断的原因**：OpenClaw 的 onboard 流程依赖 terminal capabilities 或某个它自己判断为"有问题的网络请求"（比如 ClawHub 同步、Bonjour 服务注册），在受限网络下会 indefinite 等待。

**绕过方案**：跳过 onboard，**直接手写** `~/.openclaw/openclaw.json`。

**正确的配置结构**：

```json
{
  "gateway": { "mode": "local" },
  "agents": {
    "defaults": { "model": "deepseek/deepseek-chat" }
  },
  "models": {
    "providers": {
      "deepseek": {
        "baseUrl": "https://api.deepseek.com/v1",
        "api": "openai-completions",
        "auth": "api-key",
        "apiKey": {
          "source": "env",
          "provider": "default",
          "id": "DEEPSEEK_API_KEY"
        },
        "models": [
          { "id": "deepseek-chat", "name": "DeepSeek Chat" },
          { "id": "deepseek-reasoner", "name": "DeepSeek Reasoner" }
        ]
      }
    }
  }
}
```

**教训**：CLI 工具的"向导模式"在不稳定环境下脆弱。**手写 config + 用 `openclaw config validate` 验证**更稳。

### 3.2 `config set` 逐字段操作会失败（validation）

**症状**：

```powershell
PS> openclaw config set models.providers.deepseek.baseUrl "https://api.deepseek.com/v1"
Error: Config validation failed:
  models.providers.deepseek.models: Invalid input: expected array, received undefined
```

**原因**：OpenClaw 校验器认为 `models` 数组是 provider 的必填项，你设 `baseUrl` 时它还没有，所以**整条 provider 配置不完整就拒绝**。

**修法**：用批量 JSON 或者**一次性写整个文件**：

```powershell
$config = @'
{ ... 完整 JSON ... }
'@
Copy-Item "$env:USERPROFILE\.openclaw\openclaw.json" "$env:USERPROFILE\.openclaw\openclaw.json.bak"
$config | Set-Content "$env:USERPROFILE\.openclaw\openclaw.json" -Encoding utf8
openclaw config validate   # 必须通过才继续
```

### 3.3 agents 和 agent 之差

**症状**：

```powershell
PS> openclaw config validate
Error: Unrecognized key: "agent"
```

**原因**：我 JSON 用了 `"agent": { ... }`（单数），schema 要的是 `"agents": { "defaults": { ... } }`（复数 + defaults）。

**教训**：改 schema 严格的 config 前，先 `openclaw config schema > schema.json` 存一份看字段。

---

## 4. Gateway 三种启动姿势

| 命令 | 行为 | 场景 |
|---|---|---|
| `openclaw gateway install` | **装 Windows 开机启动项**，放到 `Startup\OpenClaw Gateway.cmd` | 生产 / 永久服务（会触发 AV 告警）|
| `openclaw gateway start` | 启动已安装的服务，**需先 install** | 已 install 之后再开关 |
| `openclaw gateway` | **前台直接跑**，日志打在当前窗口，`Ctrl+C` 退出 | **开发期首选**，推荐 |
| `openclaw gateway uninstall` | 撤销自启 + 清理脚本 | 改主意不想自启时 |

### 4.1 开发期别用 install

**症状**：装了自启 → 火绒弹窗 "新 cmd 加入开机启动"。

**修法**：撤掉，改前台：

```powershell
openclaw gateway uninstall   # 清掉 Startup\*.cmd
# 之后每次要用就：
openclaw gateway             # 前台跑，关窗口即停
```

### 4.2 修改配置后必须重启 gateway

**症状**：改完 `openclaw.json`，bot 行为没变。

**原因**：gateway 启动时把 config / skills / plugins 扫一遍缓存进内存。

**修法**：Ctrl+C 停 gateway，重启。唯一例外：**skills 的 SKILL.md 修改在新 session 即可生效，不必重启**（因为 SKILL.md 是每次对话动态读取）。

---

## 5. Discord 集成的四个隐形开关

全部打开才能让 bot 真在频道里响应。按顺序：

### 5.1 Discord Developer Portal — Privileged Intents

在 bot 的 **Bot** 页面下拉找到 **Privileged Gateway Intents**：

- ✅ **Message Content Intent** ← **不开的话 bot 看不到消息内容**，只看到是谁发的，永远装聋
- ✅ Server Members Intent（想让 bot 认识成员）
- ⬜ Presence Intent（不需要）

**保存后必须点页面底部 Save Changes**，很多人漏。

### 5.2 OAuth2 URL Generator — 勾对 Scope & Permission

- Scope：`bot` + `applications.commands`
- Bot Permissions：至少 `Send Messages` / `Read Message History` / `Attach Files` / `Embed Links`

**漏了 Attach Files 就无法处理 CSV / 图片附件**。

### 5.3 OpenClaw `plugins.allow` 白名单

```powershell
# 不加这个 discord 插件加载时会警告 "plugins.allow is empty"
openclaw config set plugins.allow '["discord"]' --strict-json
```

### 5.4 `channels.discord.groupPolicy = open`

**症状**：bot 显示 online，但 @ 它无反应。

**原因**：默认 `groupPolicy: "allowlist"` 意味着**只响应白名单服务器**，而你没加白名单 → bot 看到消息**主动忽略**。

**修法**：

```powershell
openclaw config set channels.discord.groupPolicy open
```

可选值：`open` / `disabled` / `allowlist`，**不接受 `any`**（我踩过这个坑）。

---

## 6. VPN 模式切换与 Node.js 进程

### 6.1 VPN 从 rule 切到 global 后，gateway 必须重启

**症状**：日志里 gateway 启动花 **196 秒**（正常 20-30 秒），然后"开始连 Discord"后就没动静了。

**原因**：gateway 是在 VPN 还是 rule 模式时启动的，当时 Discord 连不上 → Node.js 内部重试并挂起。后来改 global TUN，**已经启动的进程不会自动切换路由表**。

**修法**：VPN 改完模式**必须重启 gateway**。

### 6.2 TUN global 会让 DeepSeek 绕路

CLI 直连测试：DeepSeek 2 秒出结果。切 global TUN 后：Discord bot 回复 30-60 秒。

**原因**：TUN 全局模式下 DeepSeek 流量也甩给了 VPN 机房 → 机房再访问 DeepSeek → 返回。每 roundtrip 多 300-800ms，LLM 多轮调用累积起来就是几十秒。

**优化方向**（不是必做）：VPN 改 **rule 模式**，规则只把 `discord.com` / `gateway.discord.gg` 之类丢去代理，其他直连。

---

## 7. Skill 开发：位置、Python、触发词

### 7.1 Custom Skill 放哪

```
C:\Users\shenc\.openclaw\workspace\skills\<skill_name>\
    SKILL.md          ← 必需，带 YAML frontmatter
    scripts\          ← 可选，放可执行脚本
    assets\           ← 可选，放测试数据
```

**验证**：`openclaw skills list | grep <skill_name>` 看到 `ready` + `source: openclaw-workspace` 即成功。

### 7.2 Python 环境选哪个

**症状**：`ModuleNotFoundError: No module named 'pandas'`（默认 python 跑脚本报错）。

**原因**：`where.exe python` 出来是 `C:\Python313\python.exe`（干净的 3.13），没装 pandas。**不要用 Anaconda 的 python**（NumPy 1.x 和 2.x 混装 + pyarrow 版本冲突）。

**修法**：往默认 python 装依赖：

```powershell
python -m pip install pandas openpyxl tabulate
```

### 7.3 SKILL.md description 是 skill 的触发密码

Bot 会根据 description 关键词决定要不要用 skill。**弱触发词** = bot 自己写 Python 绕过去。

**弱的**：

```yaml
description: Analyze a CSV file...
```

**强的**：

```yaml
description: Deterministic Python-based EDA... ALWAYS use this skill FIRST when the user attaches a .csv / .tsv / .xlsx / .xls file or asks for "帮我看看" / "分析一下" / "看一下这个数据" / "what's in this data"
```

**三个加强手法**：
1. `ALWAYS use this skill FIRST` 强命令口吻
2. 中英文触发关键词**全列出来**
3. 说清楚 skill 比 freestyle **强在哪**（编码回退 / 确定性 / 速度）

### 7.4 Skill 修改不需要重启 gateway

SKILL.md 是每次新 session 时读取的。改完 SKILL.md，**在 Discord 发 `/new` 开新 session**，即可生效。

---

## 8. Discord 使用 Gotchas

### 8.1 绝不要往消息里粘贴 CSV 文本

**事故现场**：一次聊天粘贴了 461KB 的 train.csv 文本 → session 文件从 3KB 涨到 300KB → 单次请求 131,131 tokens 超过 DeepSeek 131,072 上限 → `Context overflow, try /reset`。

**原则**：

| 做法 | 结果 |
|---|---|
| ❌ 复制粘贴 CSV 进聊天 | 每字节进 context，几百 KB 瞬间爆 |
| ✅ 拖附件进聊天 | 文件存硬盘，bot 按需 exec 读取，**不进 context** |

### 8.2 附件下载到哪里

OpenClaw Discord 插件把附件下载到：

```
C:\Users\shenc\.openclaw\media\inbound\<uuid>.<ext>
```

Bot 的 exec 工具可以直接引用这个路径。

### 8.3 新频道 = 新 session

同一频道聊久了 session 会累积（`~/.openclaw/agents/main/sessions/<uuid>.jsonl`），越长越慢、越容易撞 context 上限。

**最佳实践**：
- **不同任务用不同频道** / 不同 `/new` 指令
- 定期检查大 session 文件：
  ```powershell
  Get-ChildItem "$env:USERPROFILE\.openclaw\agents\main\sessions" |
      Sort-Object Length -Descending | Select -First 5
  ```
- 大了就 archive：
  ```powershell
  Move-Item session.jsonl session.jsonl.archived
  ```

### 8.4 连发多条 @ 只回最后一条

OpenClaw 把短时间内的多条消息**合并成一个 thread**，只回复最新意图。不是 bug，是设计。

测试时**一次发一条，等回复了再发下一条**。

---

## 9. Windows 11 专属坑

### 9.1 PowerShell 里 `sc` ≠ Service Control

**症状**：

```powershell
PS> sc config WslService start= disabled
Set-Content : A positional parameter cannot be found that accepts argument 'start='
```

**原因**：PowerShell 里 `sc` 是 `Set-Content` 的别名，不是 Windows 服务控制工具。

**修法**：显式用 `sc.exe`：

```powershell
sc.exe config WslService start= disabled
```

### 9.2 WSL 服务 Administrator 也改不了

**症状**：

```powershell
PS> sc.exe config WslService start= disabled
[SC] ChangeServiceConfig FAILED 5: Access is denied.
```

**原因**：Windows 11 把 WSL 系列服务挂在 **TrustedInstaller** ACL 下，**连 Administrator 都没有直接改的权限**。

**解法**（如果真要动）：
- 调用它的上游应用（Docker/VSCode）关掉它们的"启动时启 WSL"选项
- 或改注册表 `HKLM:\SYSTEM\CurrentControlSet\Services\WslService` 的 `Start` 值（需要改 ACL）

---

## 10. 调试速查表

### 10.1 配置/环境

```powershell
# OpenClaw config 状态
openclaw config file               # 找到 config.json 位置
openclaw config validate           # 验证 schema
openclaw config schema             # 打印完整 schema
openclaw doctor                    # 综合体检

# Env 验证
$env:DEEPSEEK_API_KEY.Length       # 预期 35
$env:DISCORD_BOT_TOKEN.Length      # 预期 ~72
where.exe node python npm openclaw # 确认每个命令的来源
node --version                     # ≥ 22.14
```

### 10.2 Gateway

```powershell
openclaw gateway                   # 前台启动（开发）
# Ctrl+C 停
openclaw gateway uninstall         # 撤销自启

# 看 session 体积
Get-ChildItem "$env:USERPROFILE\.openclaw\agents\main\sessions" |
    Sort-Object Length -Descending | Select FullName, Length
```

### 10.3 Plugins / Channels / Skills

```powershell
openclaw plugins list              # 看插件启用状态
openclaw skills list               # 看 skill 发现
openclaw skills check              # 检查 skill 依赖

openclaw config get channels.discord
openclaw config get plugins.allow
openclaw config get agents.defaults.model
```

### 10.4 手动测试 skill（不走 gateway）

```powershell
python "$env:USERPROFILE\.openclaw\workspace\skills\csv_analyzer\scripts\analyze.py" `
       "$env:USERPROFILE\.openclaw\workspace\skills\csv_analyzer\assets\sample.csv"
```

这招用来隔离"skill 脚本本身有 bug"和"bot 没调 skill"。

### 10.5 测试 agent 走 gateway

```powershell
openclaw agent --to +10000000000 --message "1+1 等于几？只回数字"
```

session 会自动用 `+10000000000` 这个假号码开一个，不会污染 Discord 的 session。

---

## 总结：如果再来一次，最重要的 5 条

1. **装 OpenClaw 前**：确认 `node --version` ≥ 22.14 **且** `where.exe node` 第一条就是系统 Node，不是 Anaconda
2. **API key**：用 `[Environment]::SetEnvironmentVariable(... .Trim(), "User")`，**长度验证**，**永不贴聊天**
3. **OpenClaw 配置**：跳过 `onboard` / `setup`，直接手写 `openclaw.json`，`config validate` 通过再说
4. **Discord**：**Message Content Intent 打开** + `groupPolicy=open` + `plugins.allow` 加进去；VPN 切模式**必重启 gateway**
5. **Skill**：写在 `~/.openclaw/workspace/skills/`，SKILL.md description 要**强触发词**，用 `openclaw skills list` 验证 ready

---

*最后更新：2026-04-22 —— 从昨夜 00:20 到今天中午 12:00，12 小时实战总结。*
