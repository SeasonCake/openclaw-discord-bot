# SETUP —— 阶段 1：环境打通

从零到"能在微信里和 AI 聊天"。每一步都**可独立验证**，出问题不要跳过。

---

## 0. 前置检查

Node 版本要 ≥ 22.16（22.22 或 24 都行）：

```powershell
node --version
npm --version
```

Python 版本 ≥ 3.9（给 csv_analyzer skill 用，现在可以先不管）：

```powershell
python --version
```

---

## 1. 买 DeepSeek API key

1. 注册：<https://platform.deepseek.com/>
2. 充值（5-10 元足够你玩几个月，`deepseek-chat` 百万 token 才几块钱）
3. 进 **API Keys** 页面，点 **Create new API key**，复制保存（只显示一次）

**保存位置建议**：项目里不要硬写 key。可以放到 `%USERPROFILE%\.deepseek_key.txt`，用的时候再引用。**绝对不能 commit 到 git**。

---

## 2. 安装 OpenClaw CLI

```powershell
npm install -g openclaw@latest
openclaw --version
```

看到版本号（例如 `2026.4.x`）就 OK。

---

## 3. 配置 OpenClaw 使用 DeepSeek

DeepSeek API 与 OpenAI 兼容，走自定义 provider 即可。

首次运行 onboarding 会引导你配置：

```powershell
openclaw onboard
```

根据提示选择 Provider。如果默认列表里没有 DeepSeek，可以**跳过选择**，之后手动改配置文件：`%USERPROFILE%\.openclaw\openclaw.json`，加入：

```json
{
  "providers": {
    "deepseek": {
      "baseURL": "https://api.deepseek.com/v1",
      "apiKey": "<你的 DeepSeek key>"
    }
  },
  "agent": {
    "model": "deepseek/deepseek-chat"
  }
}
```

> ⚠️ 实际字段名以 OpenClaw 当前版本 `openclaw config --help` 输出为准。如果上面这个 schema 报错，用 `openclaw doctor` 看具体要什么。

验证：

```powershell
openclaw agent --message "你好，回复一个字"
```

能看到 bot 回复就算通了。

---

## 4. 安装 ClawBot 微信插件

**Windows 推荐走手动安装**（`npx` 在 Windows 上有已知 bug）：

```powershell
openclaw plugins install "@tencent-weixin/openclaw-weixin"
openclaw config set plugins.entries.openclaw-weixin.enabled true
openclaw channels login --channel openclaw-weixin
```

终端会出现一个二维码。

---

## 5. 微信端启用 ClawBot 插件

- 微信版本必须 **iOS 8.0.70+**（Android 目前不支持）
- 打开微信 → **我** → **设置** → **插件** → 找到 **ClawBot** → 启用
- 用微信扫第 4 步终端里的二维码，确认授权

绑定成功后，AI agent 会像一个联系人出现在你微信里。

---

## 6. 测试

在微信里找到那个 bot 联系人，发一句：

> 你好，介绍一下自己

应该能回复。如果不回：

```powershell
openclaw doctor
openclaw gateway status
```

一般是 gateway 没启动或者 API key 错误。

---

## 故障排除

| 症状 | 排查 |
|---|---|
| `openclaw: command not found` | npm 全局路径不在 PATH；`npm config get prefix` 然后把那个路径加进 PATH |
| `requires OpenClaw >=2026.3.22` | 你 OpenClaw 版本旧；`npm i -g openclaw@latest` |
| 微信扫码后提示"授权失败" | 微信版本低于 8.0.70，或者 ClawBot 插件没开 |
| Bot 不回消息 | 查 `openclaw logs` 或 `openclaw gateway logs`；常见是 API key 错误 / 余额不足 |

---

## 阶段 1 完成后

回 [README.md](./README.md) 更新 checklist，然后进入**阶段 2：安装 csv_analyzer skill**（文档之后补）。
