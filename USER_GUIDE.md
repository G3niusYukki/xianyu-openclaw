# 用户指南

这份文档面向第一次使用当前项目的卖家或运营人员。

## 1. 这个工具能做什么

- 读取工作台状态、Cookie 健康、消息摘要和订单摘要
- 用 AI 生成商品标题、描述和模板图
- 通过闲管家接口创建商品、上架、下架、改价、发货
- 管理账号、Cookie、自动化模块和系统配置
- 查看真实运行日志和部分诊断结果

1. [这个工具能帮我做什么？](#1-这个工具能帮我做什么)
2. [我需要准备什么？](#2-我需要准备什么)
3. [安装步骤](#3-安装步骤)
4. [获取闲鱼 Cookie](#4-获取闲鱼-cookie)
5. [启动工具](#5-启动工具)
6. [管理面板各页面功能](#6-管理面板各页面功能)
7. [日常维护](#7-日常维护)
8. [自动化推进与飞书通知](#8-自动化推进与飞书通知)
9. [常见问题](#9-常见问题)
10. [名词解释](#10-名词解释)

## 2. 你需要准备什么

- 一台能联网的电脑
- 一个能正常登录的闲鱼账号
- 从浏览器复制出的闲鱼 Cookie
- 一个 AI API Key
- 一个闲管家 Open Platform 应用的 `AppKey/AppSecret`

如果你在闲鱼上卖东西，每天需要重复做很多事情：发布商品、写标题和描述、调价格、看数据。

**这个工具通过管理面板帮你完成这些操作。**

你只需要打开管理面板网页，在对应页面完成：发布商品、管理订单、查看消息、配置账号和 AI 服务、查看运营数据等。

---

## 2. 我需要准备什么？

| 你需要 | 说明 |
|--------|------|
| 一台电脑或服务器 | Windows、macOS 或 Linux |
| 能上网 | 需要连接互联网 |
| 闲鱼账号 | 能正常登录的闲鱼账号 |
| AI 服务密钥（可选） | DeepSeek / 阿里百炼 / 火山方舟 / OpenAI 等，可在管理面板配置 |
| Python 3.10+ | Python 后端运行所需 |
| Node.js 18+ | Node.js 后端和 React 前端运行所需 |

---

## 3. 安装步骤

### 3.1 下载本工具

1. 打开 https://github.com/G3niusYukki/xianyu-openclaw
2. 点击绿色的 "Code" 按钮
3. 点击 "Download ZIP"
4. 解压到你想放的位置

或者用命令行：

```bash
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
```

### 3.2 安装运行环境

**安装 Python 3.10+：**
- Windows：从 https://www.python.org/downloads/ 下载安装，安装时勾选 "Add to PATH"
- macOS：`brew install python@3.12` 或从官网下载

**安装 Node.js 18+：**
- 从 https://nodejs.org/ 下载 LTS 版本安装

### 3.3 安装项目依赖

```bash
# Python 依赖
python3 -m venv .venv
source .venv/bin/activate    # Windows 用: .venv\Scripts\activate
pip install -r requirements.txt

# Node.js 依赖
cd server && npm install && cd ..
cd client && npm install && cd ..
```

### 3.4 获取 AI 密钥

工具需要 AI 服务来理解买家消息并生成回复。推荐使用国产模型，价格便宜且无需翻墙。

**DeepSeek（推荐，便宜好用）：**
1. 打开 https://platform.deepseek.com/
2. 注册账号
3. 创建 API Key，复制密钥

**阿里百炼（备选）：**
1. 打开 https://dashscope.console.aliyun.com/
2. 注册账号
3. 创建 API Key，复制密钥

### 3.5 配置

在工具文件夹中找到 `.env.example` 文件，复制一份改名为 `.env`。

用记事本打开 `.env`，填入：

```
# 闲鱼 Cookie（下一步教你获取）
XIANYU_COOKIE_1=你的闲鱼Cookie

# AI 服务配置（可选，也可在管理面板中配置）
AI_PROVIDER=deepseek
AI_API_KEY=你的DeepSeek密钥
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
```

---

### 3.6 中国大陆网络受限环境

如果 pip 安装超时，使用国内镜像源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

或在用户目录创建 `pip.ini`（Windows）/ `pip.conf`（macOS/Linux）：

```ini
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
```

---

## 4. 获取闲鱼 Cookie

**什么是 Cookie？** 简单理解：当你登录闲鱼后，浏览器保存了一个"通行证"。我们需要把这个通行证告诉工具，工具才能代替你操作。

### 获取步骤（推荐）

1. 用 Chrome 浏览器打开 https://www.goofish.com
2. 登录你的闲鱼账号
3. 按 **F12** 打开开发者工具
4. 点击顶部的 **Network** 标签
5. 按 **F5** 刷新页面
6. 左边出现很多请求，点击任意 `goofish.com` 请求
7. 右边 `Request Headers` 找到 **Cookie:** 这一项
8. 复制完整 Cookie 值（`a=...; b=...; ...` 这一整串）
9. 粘贴到 `.env` 的 `XIANYU_COOKIE_1=` 后面，或到管理面板 `/cookie` 更新

### 三种可用粘贴格式（面板都支持）

1. 请求头字符串：`name=value; name2=value2; ...`
2. 浏览器 Cookie 表格文本（Name/Value/Domain 那种复制结果）
3. `cookies.txt`（Netscape）或 JSON 导出

### 插件一键导入（Get-cookies.txt-LOCALLY）

1. 打开本项目面板：`http://127.0.0.1:8091/cookie`
2. 点击“下载内置插件包”（项目已内置源码，可离线交付）
3. 解压后在浏览器扩展管理页加载 `Get-cookies.txt-LOCALLY/src`
4. 打开闲鱼页面，用插件导出 `cookies.txt` / JSON / ZIP
5. 回到 Cookie 页，选择“插件导出文件”，点击“插件一键导入并更新”
6. 系统会自动识别并写入 `XIANYU_COOKIE_1`

### 关键字段（建议至少包含）

- `_tb_token_`
- `cookie2`
- `sgcookie`
- `unb`

### 常见问题排查

1. 更新后仍无法用：通常是 Cookie 已过期，重新登录后再复制。
2. 解析失败：先在 `/cookie` 页面点“智能解析”，再点“更新Cookie”。
3. 字段缺失：说明复制不完整，必须复制完整 Cookie 行。
4. 账号掉线：浏览器先确认闲鱼页面处于登录态，再重新获取。

> Cookie 有有效期，通常 7-30 天后需要重新获取。
> Cookie 等同账号登录态，不要分享给他人。

---

## 5. 启动工具

### 本地开发模式（推荐）

在工具文件夹中打开终端（命令行），执行一键启动脚本：

```bash
# macOS / Linux
./start.sh

# Windows
start.bat
```

脚本会自动启动 Node.js 后端、React 前端和 Python 后端。如需 Lite 直连模式（消息自动回复），可另开终端执行 `python3 -m src.lite`。

### 打开使用

浏览器访问以下地址：

| 服务 | 地址 | 说明 |
|------|------|------|
| 管理面板 | http://localhost:5173 | React 前端，配置和管理 |
| Python 看板 | http://localhost:8091 | 趋势图、商品表现、操作日志 |
| 后端健康检查 | http://localhost:3001/health | Node.js 后端状态 |

### Docker 模式（可选）

如果你更喜欢 Docker，也可以用 Docker Compose 一键启动：

```bash
docker compose up -d
```

### 关闭

```bash
# 本地模式：在运行 start.sh / start.bat 的终端按 Ctrl+C 停止

# Docker 模式
docker compose down
```

---

## 6. 管理面板各页面功能

启动后访问 http://localhost:5173 打开管理面板首页。各页面功能简要说明如下：

| 页面 | 路径 | 功能 |
|------|------|------|
| 工作台 | /dashboard | 概览数据、快捷入口 |
| 商品管理 | /products | 商品列表、上下架、编辑 |
| 自动发布 | /products/auto-publish | 配置自动发布任务 |
| 订单 | /orders | 订单列表、状态管理 |
| 消息 | /messages | 买家消息、自动回复配置 |
| 账号 | /accounts | 多账号管理、Cookie 配置 |
| 系统配置 | /config | AI 服务、全局参数配置 |
| 数据分析 | /analytics | 运营数据、趋势图表 |

---

## 7. 日常维护

## 合规提醒（很重要）

- 只发布合法、真实、可交易的商品信息，不要发布假货、仿品或违规词内容。
- 不要引导买家去微信、QQ 等站外交易。
- 如果系统提示“命中禁词”或“操作过于频繁”，说明触发了合规保护，需要修改内容或稍后重试。
- 合规规则在 `config/rules.yaml`，可按你的店铺运营策略调整。
- `mode: block` 表示直接拦截，`mode: warn` 表示只记录告警但继续执行。

### 每天要做的

按需在管理面板查看订单、消息和运营数据即可。

### 每周建议做的

- 检查 Cookie 是否有效（见第 4 步）
- 如过期则重新获取 Cookie
- 在数据分析页面查看运营情况

### 更新工具

```bash
git pull
pip install -r requirements.txt
cd server && npm install && cd ..
cd client && npm install && cd ..
```

然后重新启动服务即可。Docker 模式用 `docker compose up -d --build` 重建。

---

## 8. 自动化推进与飞书通知

系统支持自动处理询盘、订单跟进等自动化能力，并可配置飞书告警通知。具体配置方式请参考项目文档或管理面板中的相关设置。

---

## 9. 常见问题

### Q: 打不开 localhost:5173

1. 确认 Node.js 服务是否在运行（终端中有没有报错）
2. 执行 `npm run dev` 重新启动
3. 如果端口被占用，检查是否有其他进程占用 5173 端口

### Q: AI 不回复

1. 检查 `.env` 中的 `AI_API_KEY` 是否正确
2. 确认 API Key 余额充足
3. 检查 `AI_BASE_URL` 是否可以访问

### Q: Cookie 失效 / 发布商品失败

最可能是 Cookie 过期了。重新从浏览器获取 Cookie，更新到 `.env` 或通过 Dashboard（http://localhost:8091/cookie）在线更新。

### Q: 怎么看日志

```bash
# 本地模式：直接在运行终端查看输出

# Docker 模式
docker compose logs -f
```

---

## 10. 名词解释

| 名词 | 解释 |
|------|------|
| Cookie | 登录闲鱼后浏览器保存的"通行证" |
| API Key | AI 服务的"钥匙"，让工具能使用 AI |
| WebSocket | 一种实时通信协议，用来监听闲鱼消息 |
| 闲管家 | 闲鱼开放平台，提供商品和订单管理 API |
| Dashboard | 数据看板，用来查看运营数据和操作日志 |
| Lite 模式 | 轻量运行模式，直连闲鱼 WebSocket 收发消息 |

---

## 安全提示

- 不要把 Cookie 和 API 密钥分享给任何人
- 定期更新 Cookie
- 操作频率不要太高，避免被闲鱼限制
- 遵守闲鱼平台规则

---

**版本**: v6.2.1 | **更新日期**: 2026-03-07
