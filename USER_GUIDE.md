# 闲鱼自动化工具 - 使用说明书

> 这份说明书面向从未接触过计算机技术的普通用户。

---

## 目录

1. [这个工具能帮我做什么？](#1-这个工具能帮我做什么)
2. [我需要准备什么？](#2-我需要准备什么)
3. [安装步骤](#3-安装步骤)
4. [获取闲鱼 Cookie](#4-获取闲鱼-cookie)
5. [启动工具](#5-启动工具)
6. [怎么用？直接对话就行](#6-怎么用直接对话就行)
7. [日常维护](#7-日常维护)
8. [自动化推进与飞书通知](#8-自动化推进与飞书通知)
9. [常见问题](#9-常见问题)
10. [名词解释](#10-名词解释)

---

## 1. 这个工具能帮我做什么？

如果你在闲鱼上卖东西，每天需要重复做很多事情：发布商品、写标题和描述、每天擦亮、调价格、看数据。

**这个工具让你用"说话"的方式完成所有操作。**

你只需要打开一个网页，像跟助手聊天一样说：

- "帮我发布一个 iPhone 15，价格 5999"
- "擦亮所有商品"
- "今天卖得怎么样"
- "把那个 MacBook 降价到 8000"

AI 助手会自动帮你在闲鱼上完成这些操作。

---

## 2. 我需要准备什么？

| 你需要 | 说明 |
|--------|------|
| 一台电脑或服务器 | Windows、macOS 或 Linux |
| 能上网 | 需要连接互联网 |
| 闲鱼账号 | 能正常登录的闲鱼账号 |
| AI 服务密钥 | 网关模型（Anthropic/OpenAI/Kimi/MiniMax/智谱ZAI 任选一个）+ 业务文案模型（DeepSeek/百炼/火山/智谱等可选） |
| Python 3.10+ | 仅在本地运行脚本（如一键向导、可视化后台）时需要 |
| Docker | 一个免费的软件，用来运行工具 |

---

## 3. 安装步骤

### 3.1 安装 Docker

**Windows 用户：**
1. 打开 https://www.docker.com/products/docker-desktop/
2. 下载 Docker Desktop for Windows
3. 双击安装，一路点 Next
4. 安装完成后重启电脑
5. 打开 Docker Desktop，等左下角状态变成绿色 "Running"

**macOS 用户：**
1. 打开 https://www.docker.com/products/docker-desktop/
2. 下载 Docker Desktop for Mac
3. 拖到 Applications 安装
4. 打开 Docker Desktop，等左下角状态变成绿色 "Running"

### 3.2 下载本工具

1. 打开 https://github.com/G3niusYukki/xianyu-openclaw
2. 点击绿色的 "Code" 按钮
3. 点击 "Download ZIP"
4. 解压到你想放的位置

### 3.3 获取 AI 密钥

工具需要 AI 服务来理解你的指令。建议分成两类：

- 网关模型（必填）：Anthropic / OpenAI / Moonshot(Kimi) / MiniMax / ZAI（智谱）
- 业务文案模型（可选）：DeepSeek / 阿里百炼 / 火山方舟 / MiniMax / 智谱

**Anthropic（推荐）：**
1. 打开 https://console.anthropic.com/
2. 注册账号
3. 在 API Keys 页面创建密钥
4. 复制密钥（以 `sk-ant-` 开头）

**DeepSeek（最便宜）：**
1. 打开 https://platform.deepseek.com/
2. 注册账号
3. 创建 API Key，复制密钥

### 3.4 配置

在工具文件夹中找到 `.env.example` 文件，复制一份改名为 `.env`。

用记事本打开 `.env`，填入：

```
ANTHROPIC_API_KEY=你的AI密钥
OPENCLAW_GATEWAY_TOKEN=随便设一个密码
AUTH_PASSWORD=你的登录密码
XIANYU_COOKIE_1=你的闲鱼Cookie（下一步教你获取）
```

---

## 4. 获取闲鱼 Cookie

**什么是 Cookie？** 简单理解：当你登录闲鱼后，浏览器保存了一个"通行证"。我们需要把这个通行证告诉工具，工具才能代替你操作。

### 获取步骤

1. 用 Chrome 浏览器打开 https://www.goofish.com
2. 登录你的闲鱼账号
3. 按 **F12** 打开开发者工具
4. 点击顶部的 **Network** 标签
5. 按 **F5** 刷新页面
6. 左边出现很多行，随便点一行
7. 右边找到 **Cookie:** 这一项
8. 全部复制（很长的一串文字）
9. 粘贴到 `.env` 文件的 `XIANYU_COOKIE_1` 后面

> Cookie 有有效期，通常 7-30 天后需要重新获取。

---

## 5. 启动工具

### 一键部署（推荐）

不想手动改 `.env` 的话，直接运行：

```bash
python3 -m src.setup_wizard
```

Windows 用户也可以先执行（自动创建虚拟环境并安装依赖）：

```bat
scripts\windows\setup_windows.bat
# 一键安装 + 自检 + 启动
scripts\windows\quickstart.bat
```

按提示一步一步输入：
- AI API Key
- OpenClaw 登录密码
- 闲鱼 Cookie

向导会自动生成 `.env`，并可直接帮你执行 `docker compose up -d`。

### 第一次启动

在工具文件夹中打开终端（命令行），执行：

```bash
docker compose up -d
```

等待几分钟下载和启动。

### 打开使用

浏览器访问：

```
http://localhost:8080
```

输入你在 `.env` 中设置的用户名（默认 admin）和密码登录。

### 可视化后台（运营看板）

如果你想看图表和操作日志，可单独启动后台页面：

```bash
python3 -m src.dashboard_server --port 8091
```

浏览器打开 `http://localhost:8091`，可看到趋势图、商品表现和最近操作记录。

### 启动前自检（推荐）

先执行 doctor，自动检查 Python、Cookie、数据库、网关连通性和首响配置：

```bash
python3 -m src.cli doctor --strict
```

### 关闭

```bash
docker compose down
```

### 再次启动

```bash
docker compose up -d
```

---

## 6. 怎么用？直接对话就行

登录后你会看到一个对话界面。像跟助手聊天一样说你想做什么。

### 发布商品

> "帮我发布一个 iPhone 15 Pro 256G，95新，价格 5999，换新手机了"

AI 会自动帮你生成标题和描述，然后在闲鱼上发布。

### 擦亮商品

> "帮我擦亮所有商品"

AI 会自动帮你擦亮全部在售商品。

### 调整价格

> "把那个 iPhone 的价格改成 5500"

### 查看数据

> "今天运营数据怎么样"
>
> "最近一周浏览量怎么变化的"

### 管理账号

> "我的账号还正常吗"
>
> "Cookie 过期了，帮我更新"

---

## 7. 日常维护

## 合规提醒（很重要）

- 只发布合法、真实、可交易的商品信息，不要发布假货、仿品或违规词内容。
- 不要引导买家去微信、QQ 等站外交易。
- 如果系统提示“命中禁词”或“操作过于频繁”，说明触发了合规保护，需要修改内容或稍后重试。
- 合规规则在 `config/rules.yaml`，可按你的店铺运营策略调整。
- `mode: block` 表示直接拦截，`mode: warn` 表示只记录告警但继续执行。

### 每天要做的

什么都不用做。你可以设置自动擦亮，AI 会按计划执行。

### 每周建议做的

- 打开对话，问问 "我的 Cookie 还有效吗"
- 如果过期了，重新获取 Cookie（见第 4 步）
- 查看周报：问 "这周运营情况怎么样"

### 更新工具

```bash
docker compose pull
docker compose up -d
```

这会自动获取 OpenClaw 最新版本。

---

## 8. 自动化推进与飞书通知

如果你希望系统自动持续处理询盘，并把告警推送到飞书，可以用下面命令：

```bash
python3 -m src.cli automation --action setup --enable-feishu --feishu-webhook "你的飞书webhook"
python3 -m src.cli automation --action status
python3 -m src.cli automation --action test-feishu
```

Windows 可以直接运行：

```bat
scripts\windows\automation_setup.bat 你的飞书webhook
scripts\windows\feishu_test.bat
scripts\windows\run_worker.bat 20 5
```

### 三大模块单独启动（售前/运营/售后）

如果你只想开某一部分能力，可以按模块启动：

```bash
# 1) 售前客服（自动首响 + 自动报价）
python3 -m src.cli module --action start --target presales --mode daemon --limit 20 --interval 5

# 2) 闲鱼运营（擦亮/数据采集调度）
python3 -m src.cli module --action start --target operations --mode daemon --init-default-tasks --interval 30

# 3) 售后客服（售后订单跟进）
python3 -m src.cli module --action start --target aftersales --mode daemon --limit 20 --interval 15 --issue-type delay
```

启动前建议先做模块检查：

```bash
python3 -m src.cli module --action check --target all --strict
```

查看运行状态：

```bash
python3 -m src.cli module --action status --target all --window-minutes 60
python3 -m src.cli module --action logs --target all --tail-lines 80
python3 -m src.cli module --action stop --target all
```

Windows 一键脚本：

```bat
scripts\windows\launcher.bat
scripts\windows\lite_quickstart.bat
scripts\windows\module_check.bat
scripts\windows\module_status.bat
scripts\windows\start_all_lite.bat
scripts\windows\start_presales.bat daemon 20 5
scripts\windows\start_operations.bat daemon 30
scripts\windows\start_aftersales.bat daemon 20 15 delay
```

---

## 9. 常见问题

### Q: 打不开 localhost:8080

确认 Docker Desktop 是否在运行（图标是绿色的），执行 `docker compose ps` 看容器是否正常。

### Q: 页面提示 `pairing required`

这是首次设备配对，执行：

```bash
docker compose exec -it openclaw-gateway openclaw devices list
docker compose exec -it openclaw-gateway openclaw devices approve <requestId>
```

### Q: 报错 `At least one AI provider API key env var is required`

说明网关没有读到可识别的 Key。请在 `.env` 至少填写一个：
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `MOONSHOT_API_KEY` / `MINIMAX_API_KEY` / `ZAI_API_KEY`。

### Q: AI 不回复

检查 `.env` 中的 AI 密钥是否正确，确认账户有余额。

### Q: 发布商品失败

最可能是 Cookie 过期了。重新获取 Cookie 并更新。

### Q: 怎么看日志

```bash
docker compose logs -f
```

---

## 10. 名词解释

| 名词 | 解释 |
|------|------|
| Cookie | 登录闲鱼后浏览器保存的"通行证" |
| Docker | 一个免费软件，让工具在任何电脑上都能运行 |
| OpenClaw | 一个 AI 助手框架，提供对话能力和浏览器控制 |
| API Key | AI 服务的"钥匙"，让工具能使用 AI |
| 擦亮 | 闲鱼功能，刷新商品让排名更靠前 |
| Gateway | OpenClaw 的核心服务，处理对话和浏览器控制 |
| Skills | 技能，教 AI 如何操作闲鱼的说明书 |

---

## 安全提示

- 不要把 Cookie 和 API 密钥分享给任何人
- 定期更新 Cookie
- 操作频率不要太高，避免被闲鱼限制
- 遵守闲鱼平台规则

---

**版本**: v4.6.0 | **更新日期**: 2026-02-27
