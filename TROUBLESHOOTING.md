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
11. [Skill 部署：junction 被拒 + 环境变量继承](#11-skill-部署junction-被拒--环境变量继承)
12. [v3 重构期：PowerShell heredoc、additive API、state machine 坑](#12-v3-重构期powershell-heredocadditive-apistate-machine-坑)

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

## 11. Skill 部署：junction 被拒 + 环境变量继承

第二阶段（`auction_king` skill）开发时，为了保持"**git 仓库是唯一真相，workspace 只是部署目标**"的干净结构，第一反应是用 Windows 目录 junction（`mklink /J`）把 workspace 下的 skill 目录指向 git 仓库里的源码。结果撞上两个非常隐蔽的坑。

### 11.1 OpenClaw 拒绝 junction/symlink 跳出 workspace 根（安全特性）

**现象**：

```powershell
cmd /c mklink /J "C:\Users\shenc\.openclaw\workspace\skills\auction_king" `
                 "c:\xiangmuyunxing\biancheng\2026\projects\openclaw-discord-bot\skills\auction_king"
# Junction created ...（看起来很成功）

openclaw skills list --verbose
# [skills] Skipping escaped skill path outside its configured root:
#   source=openclaw-workspace
#   root=~/.openclaw\workspace\skills
#   reason=symlink-escape
#   requested=~/.openclaw\workspace\skills\auction_king
#   resolved=c:\xiangmuyunxing\biancheng\2026\projects\...\skills\auction_king
#
# 结果：auction_king 在列表里完全不出现，更别说 ready。
```

**根因**：OpenClaw 在扫描 `workspace/skills` 时会 `realpath` 解析每个条目的真实路径，**如果解析后的路径跳出配置的 root，就直接跳过**。这是一个**故意的安全设计**（防止恶意 skill 通过 symlink 引入 workspace 外的代码），并不是 bug。junction 在 Windows 上和 POSIX symlink 表现一致，同样被拒。

**解法**：放弃 junction，用真实复制。推荐 `robocopy` 做快速增量同步，并且把开发用不到的目录排除掉：

```powershell
# 删掉之前的 junction（只删链接本身，不影响源文件）
Remove-Item "C:\Users\shenc\.openclaw\workspace\skills\auction_king" -Force

robocopy `
    "C:\xiangmuyunxing\biancheng\2026\projects\openclaw-discord-bot\skills\auction_king" `
    "C:\Users\shenc\.openclaw\workspace\skills\auction_king" `
    /E /XD state __pycache__ .pytest_cache tests /NFL /NDL /NJH /NJS
```

**副作用**：每次改源码（SKILL.md / Python / 数据）都要重新 robocopy 一次才能让 gateway 看到。为此我在 `tools/deploy-skill.ps1` 写了一键同步脚本：

```powershell
.\tools\deploy-skill.ps1 auction_king
# 脚本内部就是上面那条 robocopy，加了自动清理旧 target + 打印统计
```

**教训**：任何类 Unix 工具链在 Windows 移植时，"symlink 能工作"和"symlink 被允许"是两回事。企业级安全约束往往默认拒绝 symlink 跨 root，看日志比看"看起来执行成功"更重要。

### 11.2 Gateway 子进程继承不到临时 `$env:` 变量

**现象**：

`auction_king` 的 `llm_narrator.py` 依赖两个环境变量：

- `DEEPSEEK_API_KEY` — 已经用 `[Environment]::SetEnvironmentVariable(..., "User")` 持久化过了
- `AUCTION_KING_USE_LLM=1` — 只在 dev PowerShell 里临时 `$env:AUCTION_KING_USE_LLM = "1"` 过

**结果**：Discord 触发 skill 时跑的 `python game.py start`，`os.environ.get("AUCTION_KING_USE_LLM")` 返回 None → fallback 到模板。LLM 台词层**静默失效**，但脚本正常跑完，没有任何错误提示。

**根因**：Gateway（`openclaw gateway`）早就常驻进程了，它的环境变量快照是**启动那一刻**的。之后任何 `$env:` 临时设置都只属于那个 PowerShell 窗口，**不会反向注入已在运行的 gateway 进程**。gateway 再 spawn 的 Python 子进程继承的是 gateway 自己的快照。

**解法**：

```powershell
# 错误姿势（只在当前窗口生效，gateway 看不到）
$env:AUCTION_KING_USE_LLM = "1"

# 正确姿势（永久写入用户 env，未来所有新进程都继承）
[System.Environment]::SetEnvironmentVariable("AUCTION_KING_USE_LLM", "1", "User")

# 设完必须重启 gateway 才能拿到新变量
# （Ctrl+C 旧的 → 重开 `openclaw gateway`）
```

**验证姿势**：

```powershell
# 从 User scope 直接读（不通过 $env: 这一层）
[System.Environment]::GetEnvironmentVariable("AUCTION_KING_USE_LLM", "User")
# 应返回 "1"
```

**教训**：任何需要让**子进程看到**的 env var，必须用 `SetEnvironmentVariable(..., "User")`（或 "Machine"，视权限而定），然后**重启**依赖它的常驻进程。`$env:` 只适合脚本内部临时覆盖，完全不适合配置 skill / plugin 运行时。

### 11.3 连带发现：LLM 台词层失效是静默的

上面这条 "env 没继承 → LLM fallback 到模板" 的失效**没有任何警告提示**。这是我在 `llm_narrator.py` 里的刻意设计（为了让 key 缺失时不要把整个游戏 crash 掉），但副作用是**不容易发现**。

修法：在 gateway 启动日志或者 game.py 初次跑时，如果 LLM disabled，打印一行明显的告警：

```python
# 在 llm_narrator.is_enabled() 里
if not _enabled and not _warned:
    print("[llm_narrator] AUCTION_KING_USE_LLM != '1' → running in template fallback mode.",
          file=sys.stderr)
    _warned = True
```

已列入 3.4.1 小修单。

---

## 12. v3 重构期：PowerShell heredoc、additive API、state machine 坑

> 场景：`auction_king` 3.6b 跑通后继续迭代 v3（standard 模式多轮竞价）。从 Phase B1（mode-aware state）→ B2（reactive AI）→ C（sub-round 引擎 + CLI dispatch）中，又踩到几个值得写下来的坑。

### 12.1 PowerShell 多行 commit message：**别用 bash heredoc**

我写过一次：

```powershell
# ❌ bash 风格，PowerShell 直接 ParserError
git commit -m @`"line1
line2
line3`"@
```

PowerShell **没有** `@"` 这种转义写法（那个反引号让它彻底看不懂了）。正确写法是 PowerShell 原生 **here-string**：

```powershell
# ✅ PowerShell here-string：开引号 @" 必须单独一行，收尾 "@ 也必须顶格
$msg = @"
第一行标题

第二行正文，想写多少行都行
也可以包含 "英文引号" 和 `反引号`
"@
git commit -m $msg
```

要点：
- `@"` 后面**直接换行**，内容从下一行开始
- `"@` 必须**顶格**（行首没有空格），否则解释器认不出来
- 单引号 here-string `@'...'@` 不做变量插值，适合粘贴带 `$` 的字符串

> 每次写多行 commit 我都会忘一次。**Claude 的默认模板是 bash heredoc**，在 PowerShell 下 100% 报错，需要手动改。

### 12.2 大重构的救命设计：**Add, Don't Subtract**

v3 要把「单轮密封」改成「最多 4 轮反应式竞价」。最容易犯的错是**直接改** `BidContext` / `decide_bid` / `_resolve_round`——v2 的 simulate + 已跑过的 demo 会瞬间全挂。

我采用的模式（后来在 B1/B2/C 三个 commit 都救了我一次）：

| v2（保留不动） | v3（新加） |
| --- | --- |
| `BidContext` | `BidContextV3`（继承式扩展，带 `to_v2()` 降级） |
| `Bidder.bid_sealed()` | `Bidder.decide_bid_v3()`，默认 sub_round 1 fallback 回 `bid_sealed` |
| `compute_ai_bid` | `compute_ai_bid_v3`（独立入口，game_seed 同一套） |
| `_resolve_round` (quick) | `standard_engine.apply_sub_round_bids / check_item_end / finalize_item / advance` |
| `cmd_bid` | `_cmd_bid_quick` + `_cmd_bid_standard` + mode dispatch |

三条守则：
1. **新增文件优先**：`standard_engine.py` 单独一个模块，v2 调用链零感知
2. **cmd 层分流**：`cmd_bid → _is_standard_mode(state) ? _standard : _quick`，两条路径互不穿透
3. **回归测试随新增一起写**：B1 加 30 个 state 测试，B2 加 34 个 AI 测试，C 加 19 个引擎测试——每次重构后 `pytest` 全绿才能 commit

结果：v3 全部完成后，v2 quick 模式的 103 个老测试**一个没动，零修改**。demo 随时能切回 `--mode quick` 保命。

### 12.3 State machine 真实 bug：history 里只存 `new_bids` 漏掉持位者 → squash 误判

**现象**：standard 模式 sub_round 2，人类 $900 raise，艺姐（前领跑）持位 $761。
- 预期：pool={人类 $900, 艺姐 $761}，比率 1.18× < 1.5× 阈值 → 继续 sub_round 3
- 实际：人类一 raise 系统就直接宣告成交，完全没给 sub_round 3 机会

**根因**：`apply_sub_round_bids` 写 history 时只存了 `new_bids = {人类: 900}`（本 sub_round 的新出价），**没存完整 pool**。`check_item_end` 读 `last["bids"]` 只看到人类一人，于是走了「池里只有领跑一人 → 碾压成立」的退路。

艺姐的 $761 作为「领跑者持位」**既不是新出价也不在 withdrawn**，凭空消失了。

**修复**：把 history 结构从
```python
{"sub_round": ..., "bids": {...new only...}, ...}
```
改成
```python
{
  "sub_round": ...,
  "new_bids": {...本 sub_round 新出价...},
  "pool": {...新出价 + 前领跑者持位 bid...},  # ← 新增
  "prev_leader": "艺姐", "prev_max_bid": 761,   # ← 新增，方便调试
  ...
}
```
然后 `check_item_end` 统一从 `last["pool"]` 读。

**教训**：
- **state transition function 必须记录决策所需的完整快照**，不能依赖「旁边那个字段还在」——因为字段在同一个 apply 里已经被覆盖了（`current_max_bid` 800 变 900 后，前一任 leader 的 761 就再也找不回来了）
- **真实游戏 playthrough > 单元测试**：这个 bug 34 个 B2 AI 测试 + 30 个 B1 state 测试全绿的情况下依然溜过，是靠 `python game.py start/bid ...` 手动跑了一件才暴露
- **暴露后立刻写回归测试**：`test_regression_held_leader_counted_in_squash_check` 用真实 seed=42 的数据锁死 1.18× 案例，下次再改 state 结构时立刻报警

### 12.4 Simulate 跑 100 局巨慢：LLM 在 loop 里默默 fire

v2 回归测试跑 `simulate --n-games 100` 发现卡了几分钟没动静。用 `Get-Process python` 看它确实在跑，CPU 也在烧——但就是慢。

排查后发现：`AUCTION_KING_USE_LLM` 默认跟着当前 session 的 env 走。我前面调 `llm_narrator` 时设了 `$env:AUCTION_KING_USE_LLM = "1"`，后面 simulate 继承了这个值 → **每局结算都去请求一次 DeepSeek**，100 局 = 几百次 API 调用。

修：

```powershell
# 跑 simulate 前临时关掉
$env:AUCTION_KING_USE_LLM = "0"; python scripts/game.py simulate --n-games 100
```

后来我把它做成了习惯：**batch/simulate 开跑前永远显式设 `USE_LLM=0`**。

### 12.5 SKILL.md 反泄漏：「不要做 X」不够，要贴真实泄漏文字当 ❌ 反例

**现象**（v3 部署到 Discord 首测当晚）：

```
Qilindage — 6:25 PM
@openclaw_bidking 算了

openclaw_bidking APP — 6:26 PM
The user said "500" — in the context of an active bidding round, treat as bid --amount 500.
"算了" means they want to withdraw from this item in standard mode.
```

Bot 没调 `withdraw` 工具，**把自己的思考过程原文发到 Discord 了**，每轮还得等 ~1 分钟。用户正确诊断：速度慢和输出冗余是同一个问题的两面——LLM 花额外 token 生成元推理 → 既慢又丑。

**SKILL.md 里明明早就写了**：

> Paste stdout back verbatim. Do NOT add your own commentary.

但这句话太抽象，agent 模型把「不加评论」理解成「不加 AI 角色台词」，**没意识到自己的 chain-of-thought 也是 commentary**。

**修复姿势**（不是加更多规则，是加**具体反例**）：

```markdown
## ⚠️ IRON RULE — NO REASONING TEXT EVER

**You are a silent router. Users must NEVER see your reasoning.**

Forbidden output patterns (every one of these was observed in the wild):
- ❌ `The user said "500" — treat as bid --amount 500.`
- ❌ `"算了" means they want to withdraw from this item in standard mode.`
- ❌ `The user wants to start a standard mode game. Let me load the skill.`
- ❌ `好的，我来帮你开局`
- ❌ `看起来 Kai 领先了`
- ❌ `Based on the context, I'll run...`

The ONLY thing the user sees from you is `stdout` of the CLI command, pasted verbatim.
```

把每条观察到的真实泄漏文字**原文贴进去**做 ❌ 反例，比抽象的 "no commentary" 强十倍。部署后立刻验证：

```
@openclaw_bidking 算了，太贵了
openclaw_bidking APP — 6:39 PM
Sub-round 2 揭晓（晚清鼻烟壶）
  · Kai：$618（持位） 👑
  · 退出：你、Miles、老周头
...
```

泄漏消失、withdraw 正确触发、响应时间从 ~60s 降到 ~15s。

**教训**：
- **LLM skill routing**：抽象规则（"be concise / don't comment"）对 agent 模型效果差；**贴真实 bad output 作 ❌ 示范**效果最强——模型对「不要生成长得像这样的东西」比「不要做 X」更敏感
- **Discord 上看到的意外文字 = 免费的 bad example 库**：每次 bot 说了不该说的话，复制那句话贴进 SKILL.md 顶部，下一次就修掉了
- **UX 问题和延迟问题常常同源**：LLM 多说话 → Discord 显示多出来的文字 + token 生成时间增加。砍掉前者自动修后者
- **扩触发词是配套动作**：这次加了 `算了 / 不要了 / 太贵了 / 不玩了` 进 withdraw 映射。如果只加 IRON RULE 不加触发词，LLM 还是会在「没识别到这是 withdraw」时兜到推理兜底

### 12.6 LLM 行为护栏要分三层：工具前 / 工具后 / 出错时（不是一刀切"少说话"）

12.5 的 IRON RULE 上线后，第二天玩到第 3-4 件就发现**两个新的失败模式**：

**失败模式 A：工具调用前的 preamble 没被 IRON RULE 覆盖**

```
@openclaw_bidking 现在什么情况
openclaw_bidking APP:
This is an Auction King game query. Let me read the skill file and check the current game state.
The user is asking about the current game state. Let me check.
找不到 session auction_qilindage。要开一局吗？
```

前两行是**调用工具之前**的"我要去干啥"。IRON RULE 主要贴的 ❌ 都是「处理中 / 解释参数」，漏了这种"我要开始处理了"的 pre-tool-call 自述。

**失败模式 B：timeout 之后 bot 自作主张 `--force` 开新局**

```
@openclaw_bidking 下一件吧，太离谱了，竞拍价
→ LLM idle timeout
@openclaw_bidking 500
→ 🏛️ 竞拍之夜开始！（新一局，完全不同的物品/对手）
Hmm, the session file seems to have been lost. Let me check if there's a state file...
```

Bot 看到上一个 `bid` 似乎失败（实际只是 timeout），**自动决定**「那开个新局吧」并 `start --force`，覆盖掉玩家已经打到第 3 件的存档。IRON RULE 管的是"正常路径别推理"，**出错路径的兜底逻辑**完全没护栏。

**修两条之后，第三个失败模式立刻冒出来**：

**失败模式 C：模型开始 paraphrase CLI 输出**

```
# 实际 stdout（18 行完整结构）：
Sub-round 2 揭晓（齐白石风格小品）
  · Kai：$891 👑
  · 你：$800（持位）
  · 退出：Miles、阿鬼
📣 当前领跑：Kai $891（次高 $800，领先 1.11×）
📢 齐白石风格小品 — Sub-round 3/4
   当前领跑：Kai $891
   最低加价：$936（或 withdraw 退出）
   你的预算：$2937

# 模型实际发到 Discord（1 行俏皮话）：
Kai 反超了！要加价到 $936+，还是放弃？
```

再严重点的还自己加 `😂` 和 "明智！" 点评。**IRON RULE + ZERO-PREAMBLE 把"少说话"训练得太凶，模型把原则泛化到"CLI 输出我也精简一下吧"**——classic LLM alignment over-generalization。

**根因**：我之前把"不要泄漏 / 少说话"当成一条规则写。实际上**三种情境的"正确形状"完全不同**：

| 情境 | 该做什么 | 该是什么形状 |
|---|---|---|
| **工具调用前** | 闭嘴直接 call | **零字符** |
| **工具调用后** | 复制粘贴 stdout | **完整 N 行**（N = stdout 行数）|
| **工具出错时** | 一句症状 + 短问 | **一行** |

把这三条**分开命名**写进 SKILL.md：**ZERO-PREAMBLE RULE** / **VERBATIM PASTE RULE** / **ERROR RECOVERY RULE**。每条贴**对应情境**的真实 ❌ 反例（pre-tool-call 的自述、paraphrase 成一句话的战报、auto-restart 的兜底诊断）。

部署后立刻跑一局 standard 5/5 件，全程零超时、零 paraphrase、完整结构：

```
🏆 最终排名
  🥇 阿鬼   $3034  (+$70)
  🥈 Miles  $2964  (+$0)
  🥉 艺姐   $2964  (+$0)
  4️⃣ 你    $2514  ($-450)
```

（玩家真实输掉、AI 两次"捡漏"成功——本来设计的"阿鬼 = 专设陷阱"人设第一次在数据层兑现。）

**教训**：

- **LLM 护栏不能合并命名**：如果叫"IRON RULE"一条兜底所有情境，模型会把它往最省力的方向 collapse——大概率是"啥都少说"，然后 paraphrase 掉你最想保留的部分（CLI 结构）。拆成 3 条独立命名、给每条配独立 ❌ 反例，模型才能区分"这种情境下的正确长度"
- **LLM alignment over-generalization 是真的**：训练模型"在 A 少说话"→ 它学会"在 B C D 也少说话"。**反制靠"明确说明 B 情境要长"**，不能只靠"A 要短"
- **Error path ≠ happy path**：正常调用、异常调用、工具失败是**三个完全不同的 phase**，各自要单独 audit。之前只审 happy path 的护栏，error path 一炸（比如 `--force` 覆盖存档）损失可能比 happy path 丑一点严重得多
- **新护栏上线必跑 end-to-end**：一局 standard 5/5 件 ≈ 10 分钟 Discord，是最好的 acceptance test。单元测试永远抓不到"模型 paraphrase 成俏皮话"这种行为——只有真人玩 + 真人看才能 flag
- **存档 dedupe 也是护栏的一部分**：顺带加了 DUPLICATE MESSAGE DEDUPE（用户手抖连发两个 `700`，跑一次就行，别跑两次）。这种"手机 Discord 常见现象"在写代码时绝对想不到，必须靠真实使用暴露

**最终状态**：SKILL.md 顶部现在是 4 条命名护栏（IRON / ZERO-PREAMBLE / VERBATIM PASTE / ERROR RECOVERY），加一条 DUPLICATE DEDUPE。每条都有贴在 Discord 上实拍到的 ❌ 反例。

---

## 13. `csv_analyzer` 图片双发：OpenClaw 在 Windows CRLF 下解析 fenced code block 的 bug

> 场景：`csv_analyzer` 在 Discord 上每次生成 EDA 图表都**回传两张一模一样的 PNG**。前两次修法都没对症——第一次以为是 `plot.py` 的 stdout echo 了路径被 channel 扫到，删掉 path echo 后**还是双发**；第二次以为是 LLM 在 reply 里写了两次 `MEDIA:`，把 `SKILL.md` 的 reply 模板改成"只许一条 `MEDIA:` 线"后**还是双发**。

### 真正的根因（和预期完全不一样）

OpenClaw 2026.4.15 的 `pi-embedded-runner` 会**扫描每一次工具调用的 stdout/输出文本**，从中提取 `MEDIA:<path>` 指令并队列到 `state.pendingToolMediaUrls`；等到最终 reply 的 `MEDIA:<path>` 到来时，用 `new Set([...final, ...pending])` 合并——**不同字符串的 path 不会被 Set 去重**。

这个"扫描工具输出"的逻辑**本来**会被 markdown fence 保护（源码 `parse-CwkQk8aD.js` 里 `parseFenceSpans` → `isInsideFence` 把 ` ``` ` 之间的行跳过不扫）。但它有一个**关键 bug**：fence 检测的正则是 `/^( {0,3})(`{3,}|~{3,})(.*)$/`——**没有加 `m` flag 且 `.` 不匹配 `\r`**，所以任何 CRLF 行尾的 ` ``` ` 都匹配不上，parseFenceSpans **直接返回 0 个 fence span**，整个文件被当成"没有任何 fence"扫一遍。

于是事情变成这样：

1. 用户上传 CSV，LLM 调用 `read SKILL.md` 加载技能说明
2. `SKILL.md` 里有一行 reply 模板示例（在 ` ``` ` 里）写着 `MEDIA:C:\Users\shenc\.openclaw\media\inbound\b4c90b0e-..._eda.png`
3. Fence 检测炸了（CRLF bug），示例 path 被当成真的 MEDIA 指令提取，塞进 `pendingToolMediaUrls`
4. LLM 继续跑 `plot.py`，最终 reply 写了 `MEDIA:C:\Users\shenc\.openclaw\media\inbound\67bfd1f2-..._eda.png`（真的 path）
5. `consumePendingToolMediaIntoReply` 合并：`Set(["67bfd1f2-...eda.png", "b4c90b0e-..._eda.png"])`——**两个不同字符串**，Set 根本不 dedupe
6. 两个 URL 都进 `sendMediaWithLeadingCaption` 的 for 循环，每个都 `loadWebMedia + saveMediaBuffer` 存一个 outbound UUID file，发两次 Discord 附件

### 诊断过程（走了多少弯路）

- **错误假设 #1**：`plot.py` 的 stdout 里 echo 了 `print(f"EDA 图表已生成：{output}")`，channel 从 stdout 捞到路径又附件一次。删掉这行 print 后——**还是双发**
- **错误假设 #2**：LLM 在 reply 里写了两次 `MEDIA:`。把 `SKILL.md` 改成"模板里只允许一条 `MEDIA:` 线"——**还是双发**
- **错误假设 #3**：OpenClaw 的 Discord 插件有更底层的自动扫描机制，比如监控 `inbound/` 目录新文件。**验证方法**：看 `~/.openclaw/media/outbound/` 有几个 PNG——确实是**两个同字节的 UUID PNG，同一秒写入**
- **转折点**：扒 OpenClaw 源码（`node_modules/openclaw/dist/parse-CwkQk8aD.js` + `pi-embedded-runner-DN0VbqlW.js`），找到 `collectEmittedToolOutputMediaUrls` 会扫所有工具的 stdout
- **坐实 root cause**：写了个 10 行的 node 脚本，直接 import `splitMediaFromOutput` 跑 deployed SKILL.md——返回 `mediaUrls.length === 1`，里面就是那个 `b4c90b0e-..._eda.png` 的示例 path。再跑一遍 `parseFenceSpans`——返回 **0 fence spans**（但源文件有 6 个 ` ``` `）
- **最小可复现 demo**：`"```\r".match(/^( {0,3})(`{3,}|~{3,})(.*)$/) === null`——JavaScript 默认 `.` 不匹配 `\r`，这条 regex 在 Windows CRLF 文件里永远匹配不到 `\r\n` 的关闭行

### 修法（两层防御）

**第一层（内容层，治本）**：把 `SKILL.md` 所有 `MEDIA:<有扩展名的真实 Windows path>` 示例全部替换成 `<...>` 占位符。示例永远不要写可被 `isValidMedia()` 当真的字符串——任何带 `.png` / `.jpg` 扩展名、且符合 `C:\...` / `/...` 格式的，都会在 fence bug 触发时被解析成真指令。

**第二层（编码层，兜底）**：长期看文件应该存成 LF 换行——但 `robocopy` + `git` + PowerShell 默认都是 CRLF，强行切 LF 容易反复回归。所以我们不依赖这层，只用第一层。

**验证姿势**：

```powershell
# 从 workspace 读 deployed SKILL.md，跑 OpenClaw 自己的 parser
# 如果有任何 mediaUrls 被提取出来，就是 bug 还在
node -e "
import('file:///C:/Users/shenc/AppData/Roaming/npm/node_modules/openclaw/dist/parse-DUsQk5Kg.js')
  .then(m => {
    const fs = require('fs');
    const txt = fs.readFileSync('C:/Users/shenc/.openclaw/workspace/skills/csv_analyzer/SKILL.md', 'utf8');
    const r = m.splitMediaFromOutput(txt);
    console.log('leaked urls:', JSON.stringify(r.mediaUrls || []));
  })
"
# 预期输出：leaked urls: []
```

### 教训

- **不要在 SKILL.md 里写看起来像真指令的示例**。LLM 读 SKILL.md 时，OpenClaw 会扫它 stdout 找 `MEDIA:`。任何看起来像真 path 的字符串（有扩展名、有 `C:\` 前缀、不含空格）都有可能**被当成真指令注入**到当前 turn 的 outbound 队列里。占位符要用 `<...>` / 带空格 / 无扩展名
- **不是每次"我改了还复现"都意味着改的方向错**——有时候改对了但改小了。这次我前两次修的 `plot.py stdout` 和 reply template 都是**正确的护栏**（长期该保留），只是**不是根因**。根因在 SKILL.md 自己的示例上+框架 fence 检测 bug
- **扒框架源码比猜更快**。`pi-embedded-runner` + `parse-CwkQk8aD.js` 加起来 400 行看完，root cause 自动浮出来；之前在"外部行为"层面瞎猜一下午没进展
- **写 10 行 node 脚本直接跑框架的 parser** 是最稳的 bug 定位法。看 `send` / `deliver` / `dispatch` 的源码调用链容易绕晕，但直接把问题输入喂进真正的 parser 函数、看它输出什么，结论立判
- **Windows 上任何跨文件格式边界的事情都要先问 CRLF**。`\r` 是 Windows 生态里最喜欢躲在一米之外朝你开冷枪的字符——正则、JSON parser、shell here-doc、Python `readlines()`、Git diff...踩过八百次还是容易忘

### 上游 bug 记一笔

OpenClaw 2026.4.15 `dist/fences-u7A-b4Xc.js` 的 `parseFenceSpans` 应该改成：

```js
// 当前（broken on CRLF）
const match = line.match(/^( {0,3})(`{3,}|~{3,})(.*)$/);

// 修法 A：先 trimEnd line 再 match
const match = line.replace(/\r$/, "").match(/^( {0,3})(`{3,}|~{3,})(.*)$/);

// 修法 B：regex 允许 \r
const match = line.match(/^( {0,3})(`{3,}|~{3,})(?:[^\r\n]*)\r?$/);
```

够一条上游 PR 了，等这个项目整体稳定后可以提。

---

## 总结：如果再来一次，最重要的 12 条

1. **装 OpenClaw 前**：确认 `node --version` ≥ 22.14 **且** `where.exe node` 第一条就是系统 Node，不是 Anaconda
2. **API key**：用 `[Environment]::SetEnvironmentVariable(... .Trim(), "User")`，**长度验证**，**永不贴聊天**
3. **OpenClaw 配置**：跳过 `onboard` / `setup`，直接手写 `openclaw.json`，`config validate` 通过再说
4. **Discord**：**Message Content Intent 打开** + `groupPolicy=open` + `plugins.allow` 加进去；VPN 切模式**必重启 gateway**
5. **Skill**：写在 `~/.openclaw/workspace/skills/`，SKILL.md description 要**强触发词**，用 `openclaw skills list` 验证 ready
6. **Skill 部署**：**不要用 junction/symlink**（会被 OpenClaw 安全机制拒绝）；用 robocopy 真实复制 + 一键脚本 `tools/deploy-skill.ps1`；**env var 只认 `SetEnvironmentVariable(..., "User")` + 重启 gateway**
7. **PowerShell 多行字符串**：`@"..."@` here-string，`@"` 后换行、`"@` 顶格；**不要用 bash heredoc 风格**
8. **大重构 = Add, Don't Subtract**：新增 `BidContextV3` / `decide_bid_v3` / `standard_engine.py`，v2 路径零改动；cmd 层按 mode 分流；回归测试随新增一起写
9. **State machine 写 history 要存完整 pool（不是只存增量）**；真实 playthrough 能挖出单元测试漏掉的 state 遗漏 bug；simulate/batch 前显式设 `USE_LLM=0`
10. **SKILL.md 反 LLM 泄漏**：抽象规则（"no commentary"）无效；把真实观察到的 bad output 原文贴进去作 ❌ 反例效果最强；UX 和延迟常常同源，砍掉冗余推理同时修两件事
11. **LLM 行为护栏分三层，不能合并**：工具前要"零字符"、工具后要"完整粘贴"、出错时要"一句问"。命名成三条独立规则（ZERO-PREAMBLE / VERBATIM PASTE / ERROR RECOVERY）各自配 ❌ 反例，不要用一条大规则兜底——LLM 会把它 collapse 成"啥都少说"顺带 paraphrase 掉你最想保留的 CLI 结构。Error path ≠ happy path，各自 audit。真人玩一局 5/5 件 > 跑 100 个单元测试。
12. **SKILL.md 示例里不要写任何长得像"真指令"的字符串**：OpenClaw 会扫所有工具（包括 `read`）的输出找 `MEDIA:`，Windows CRLF 下 fence 检测 bug 会把 fenced 示例当真提取。占位符必须明显不是真 path（用 `<...>`、带空格、无扩展名），否则两个不同 path 会同时进 outbound 队列、Set 不 dedupe、Discord 收到双发附件。任何"我改了还复现"先扒框架源码、写 10 行 node 脚本直跑 parser——比猜行为快一个数量级。

---

*最后更新：2026-04-23 凌晨 —— 第 13 节：`csv_analyzer` Discord 图片双发，定位到 OpenClaw `parseFenceSpans` 在 Windows CRLF 下的 regex bug + `SKILL.md` 示例 path 被 `read` 工具输出扫描当真提取。修法是把示例里 `MEDIA:` 的真实 path 全换成占位符，并给上游留了一条 PR 建议。*
