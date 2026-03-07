# 闲鱼管家 - 虚拟商品卖家自动化工具

闲鱼虚拟商品卖家的全流程自动化工具。通过 WebSocket 直连闲鱼消息通道，结合 AI 实现自动回复、自动报价、商品管理和订单履约。

## 服务关系

## 核心功能

- **WebSocket 消息监听与 AI 自动回复** - 直连闲鱼 WebSocket，实时接收买家消息，AI 识别意图后自动回复
- **自动报价** - 支持规则匹配、成本表查询、远程 API 三种报价模式，多源容灾
- **商品自动上架** - AI 生成标题/描述/标签，图片处理，通过闲管家 API 发布到闲鱼
- **订单管理与自动发货** - 闲管家 API 对接，虚拟商品自动发卡密，实物订单自动发货
- **Cookie 自动续期与健康监控** - 定时探测 Cookie 有效性，失效告警，自动续期
- **前端管理面板** - 配置管理、商品列表、订单跟踪、消息查看、数据分析

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Python 后端 | Python 3.10+ / asyncio / WebSocket / SQLite | Lite 模式核心：消息监听、AI 回复、报价、Cookie 管理、Dashboard（8091 端口） |
| Node.js 后端 | Express / Sequelize / PostgreSQL | 闲管家 API 代理、用户认证、配置管理、回调接收（3001 端口） |
| React 前端 | React 18 / Vite / TailwindCSS | 管理面板：商品、订单、消息、配置、数据分析（开发端口 5173） |
| 闲管家开放平台 | REST API / 签名认证 | 商品发布、改价、订单发货、快递查询 |
| AI 服务 | OpenAI 兼容接口 | 支持 DeepSeek、阿里百炼、火山方舟、MiniMax、智谱等国产模型 |

- 商品、订单、配置、自动上架优先走闲管家 / Open Platform API。
- 消息等 API 无法完整覆盖的能力，保留 Python 侧 WS 或站点补充链路。
- Node 不是业务真相源；配置和运行状态以 Python 为准。

## 快速开始

### 前提条件

- Python 3.10+
- Node.js 18+
- 闲鱼账号 Cookie（[获取方法](#获取闲鱼-cookie)）
- AI 服务 API Key（DeepSeek / 阿里百炼 / OpenAI 等，任选一个）

### 推荐：本地开发模式

```bash
# 1. 克隆项目
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw

# 2. 安装 Python 依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 安装 Node.js 依赖
cd server && npm install && cd ..
cd client && npm install && cd ..

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入闲鱼 Cookie 和 AI API Key

# 5. 启动全部服务（Node.js 后端 + React 前端）
npm run dev
```

Python 后端（Lite 模式）需要单独启动：

```bash
# 启动 Python Dashboard + WebSocket 消息监听
python -m src.dashboard_server --port 8091
# 或启动 Lite 直连运行时
python -m src.lite
```

启动后访问：

| 服务 | 地址 |
|------|------|
| React 前端 | http://localhost:5173 |
| Python Dashboard | http://localhost:8091 |
| Node.js 后端健康检查 | http://localhost:3001/health |

### 可选：Docker 模式

```bash
cp .env.example .env
# 编辑 .env，填入必要配置（包括 DB_PASSWORD）
docker compose up -d
```

Docker Compose 会启动 PostgreSQL、Node.js 后端、Python 后端和 React 前端四个容器。

> 详细步骤请参考 [QUICKSTART.md](QUICKSTART.md)。

---

## 配置说明

编辑 `.env` 文件，填入以下关键环境变量：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `XIANYU_COOKIE_1` | 是 | 闲鱼主账号 Cookie |
| `XIANYU_COOKIE_2` | 否 | 第二个账号 Cookie |
| `AI_PROVIDER` | 是 | AI 服务商（`deepseek` / `aliyun_bailian` / `volcengine_ark` 等） |
| `AI_API_KEY` | 是 | AI 服务 API Key |
| `AI_BASE_URL` | 是 | AI 服务接口地址（OpenAI 兼容） |
| `AI_MODEL` | 否 | 模型名称，默认 `deepseek-chat` |
| `AUTH_PASSWORD` | 是 | 前端管理面板登录密码 |
| `DB_PASSWORD` | Docker 模式必填 | PostgreSQL 数据库密码 |
| `ENCRYPTION_KEY` | 否 | Cookie 加密密钥（留空自动生成） |

业务配置文件位于 `config/config.yaml`，包括消息回复策略、报价规则、合规策略等。

---

## 目录结构

```
xianyu-openclaw/
├── src/                            # Python 后端
│   ├── cli.py                      # CLI 入口
│   ├── lite.py                     # Lite 直连运行时（WebSocket）
│   ├── dashboard_server.py         # Python Dashboard（8091 端口）
│   ├── core/                       # 核心模块：配置、加密、日志、启动检查
│   ├── modules/
│   │   ├── messages/               # 消息监听与自动回复
│   │   ├── quote/                  # 自动报价引擎
│   │   ├── listing/                # 商品发布服务
│   │   ├── operations/             # 擦亮、调价、下架
│   │   ├── orders/                 # 订单管理
│   │   ├── virtual_goods/          # 虚拟商品发货（卡密）
│   │   ├── accounts/               # 多账号与 Cookie 管理
│   │   ├── analytics/              # 数据分析
│   │   ├── content/                # AI 内容生成
│   │   ├── compliance/             # 合规策略（禁词、限流、审计）
│   │   └── ticketing/              # 工单与售后
│   └── integrations/
│       └── xianguanjia/            # 闲管家开放平台 API 客户端
├── server/                         # Node.js 后端（Express）
│   └── src/
│       ├── app.js                  # 入口
│       ├── routes/                 # API 路由（认证、配置、闲管家代理）
│       ├── models/                 # Sequelize 数据模型
│       └── middleware/             # 认证中间件
├── client/                         # React 前端（Vite）
│   └── src/
│       ├── pages/                  # 页面：Dashboard、商品、订单、消息、配置
│       ├── components/             # 通用组件
│       └── api/                    # API 调用层
├── config/                         # 配置模板（config.yaml、合规策略）
├── data/                           # 运行时数据（SQLite、日志）
├── scripts/                        # 工具脚本（启动、备份、部署）
│   ├── windows/                    # Windows 批处理脚本
│   └── unix/                       # macOS/Linux 脚本
├── docker-compose.yml              # Docker 编排
├── requirements.txt                # Python 依赖
├── package.json                    # Node.js 根配置（含 dev 启动脚本）
└── .env.example                    # 环境变量模板
```

---

## 获取闲鱼 Cookie

1. 用 Chrome 打开 https://www.goofish.com 并登录
2. 按 **F12** 打开开发者工具
3. 切换到 **Network** 标签
4. 按 **F5** 刷新页面
5. 点击任意一个请求
6. 在右侧 **Request Headers** 中找到 `Cookie:` 一行
7. 全部复制，粘贴到 `.env` 的 `XIANYU_COOKIE_1=` 后面

Cookie 有效期通常 7-30 天，过期后需重新获取。也可通过 Dashboard（http://localhost:8091/cookie）在线更新。

---

## CLI 命令参考

```bash
# 诊断检查
python -m src.cli doctor --strict

# 消息自动回复
python -m src.cli messages --action auto-reply --limit 20

# 模块管理
python -m src.cli module --action start --target presales --mode daemon
python -m src.cli module --action status --target all

# 商品操作
python -m src.cli publish --title "..." --price 5999
python -m src.cli polish --all --max 50

# 订单操作
python -m src.cli orders --action deliver --order-id o1 --item-type virtual

# 数据分析
python -m src.cli analytics --action dashboard
```

---

## 本地开发

```bash
# Python 后端
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.cli --help

# Node.js + React
npm run dev              # 同时启动 server 和 client
npm run dev:server       # 仅启动 Node.js 后端
npm run dev:client       # 仅启动 React 前端

# 测试
pytest tests/
ruff check src/
```

---

## 合规边界

- 仅支持闲鱼站内合规交易，不发布违法、侵权或导流到站外的信息
- 默认启用合规护栏：内容禁词拦截、发送频率限制、审计日志记录
- 合规规则文件：`config/compliance_policies.yaml`
- 所有外发消息检查均写入审计库，可通过 `compliance --action replay` 回放

---

## 参与贡献

欢迎贡献代码，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全问题

发现漏洞请私下报告，详见 [SECURITY.md](SECURITY.md)。

## 开源许可

[MIT](LICENSE)
