# Lite Mode 架构方案

> 花羊羊🌸 · 羊村CPO · 2026-02-28

---

## 1. Lite Mode 定义

### 是什么

Lite Mode 是 xianyu-openclaw 的轻量运行模式——**零 Docker、零 Chromium、零 OpenClaw Gateway**，一条命令启动闲鱼自动回复+报价服务。

### 核心能力

| 能力 | 说明 |
|------|------|
| 自动回复 | 买家消息实时响应，意图规则+LLM兜底 |
| 智能议价 | 按议价次数动态调整策略，温度递增 |
| 快递报价 | 规则快提+LLM兜底提取→多快递比价→模板输出 |
| 运营数据 | 轻量Web看板，消息统计/报价成功率/响应耗时 |
| 人工接管 | 单会话关键词切换，超时自动恢复 |

### 不需要什么

- ❌ OpenClaw Gateway（无技能路由，直接代码调用）
- ❌ Docker（纯 Python 进程）
- ❌ Chromium/CDP（无浏览器自动化）
- ❌ 配对流程（Cookie 直注入）

### 启动方式

```bash
# 方式一：开发模式
git clone ... && cd xianyu-openclaw
cp .env.example .env  # 填 Cookie + AI Key
python -m src.lite

# 方式二：pip 安装
pip install xianyu-openclaw
xianyu-lite start
```

### 不是什么

Lite Mode **不替代** Full Mode。它不能发布商品、擦亮、调价、管理多账号——这些依赖浏览器自动化的操作仍需 Full Mode。Lite Mode 是给"只想自动回消息和报价、不想折腾 Docker"的用户准备的。

---

## 2. 架构设计

### 2.1 双模式全景对比

```
┌─────────────────────────────────────────────────────────────────┐
│                      xianyu-openclaw                            │
│                                                                 │
│  ┌─────────────────────┐     ┌──────────────────────────────┐  │
│  │     Full Mode       │     │        Lite Mode              │  │
│  │                     │     │                               │  │
│  │  OpenClaw Gateway   │     │  WebSocket Client             │  │
│  │  ├─ Skill Router    │     │  ├─ 闲鱼 WS 直连              │  │
│  │  ├─ Web UI (:8080)  │     │  ├─ 心跳/重连/ACK             │  │
│  │  └─ CDP Browser     │     │  └─ Token 刷新                │  │
│  │     ├─ 发布/擦亮    │     │                               │  │
│  │     ├─ 调价/下架    │     │  Lite Web UI (:8066)          │  │
│  │     └─ 页面操控     │     │  ├─ 消息看板                   │  │
│  │                     │     │  ├─ Cookie 管理                │  │
│  │                     │     │  └─ 报价统计                   │  │
│  └──────────┬──────────┘     └──────────────┬────────────────┘  │
│             │                               │                   │
│             └───────────┬───────────────────┘                   │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   共享核心层                              │   │
│  │                                                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │   │
│  │  │ 报价引擎  │ │ 合规策略  │ │ 数据分析  │ │ 上下文管理 │  │   │
│  │  │ quote/   │ │compliance│ │analytics │ │ context/  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 信息提取  │ │ 安全过滤  │ │ 模板渲染  │               │   │
│  │  │ extract/ │ │ safety/  │ │ template │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模式能力矩阵

| 能力 | Full Mode | Lite Mode |
|------|:---------:|:---------:|
| 自动回复 | ✅ (WS/DOM) | ✅ (WS直连) |
| 快递报价 | ✅ | ✅ |
| 议价策略 | ✅ | ✅ |
| 合规拦截 | ✅ | ✅ |
| 商品发布 | ✅ | ❌ |
| 批量擦亮 | ✅ | ❌ |
| 调价/下架 | ✅ | ❌ |
| AI文案生成 | ✅ | ❌ |
| OpenClaw技能 | ✅ | ❌ |
| 多账号管理 | ✅ | ❌（单账号） |
| Web管理界面 | ✅ (Gateway UI) | ✅ (内置轻量) |
| Docker依赖 | ✅ | ❌ |
| Chromium依赖 | ✅ | ❌ |

### 2.3 共享层详细设计

以下模块 Full/Lite 共用，**零代码分叉**：

**报价引擎** (`src/modules/quote/`)
- 现有的 Provider 模式（Rule/CostTable/API/Remote）全部复用
- QuoteCache、Circuit Breaker、fallback 链不变
- 新增：从 AutoAgent 移植 Excel 自适应导入器作为 `ExcelProvider`

**合规策略** (`src/modules/compliance/`)
- stop_words 拦截、rate_limit、审计日志不变
- Lite 模式下同样走 `compliance --action check` 校验

**上下文管理** (`src/modules/context/`)
- 新建共享模块，从 AutoAgent 的 `ChatContextManager` 重构而来
- SQLite + WAL 模式，双层去重，滑动窗口100条
- 议价计数器独立存储

**信息提取** (`src/modules/extract/`)
- 新建共享模块
- `FastExtractor`：正则快速提取（移植 `_extract_info_fast`）
- `LLMExtractor`：LLM兜底提取（移植 `_extract_info_with_llm`）
- `ContextExtractor`：上下文补齐
- 调用链：Fast → Context补齐 → LLM兜底

**安全过滤** (`src/core/safety.py`)
- 输出过滤链（微信/QQ/支付宝等外泄词拦截）
- 可配置规则，YAML 驱动

### 2.4 Lite 独有模块

```
src/lite/
├── __init__.py
├── __main__.py          # python -m src.lite 入口
├── ws_client.py         # 闲鱼 WebSocket 客户端
├── api_client.py        # 闲鱼 HTTP API (get_token/get_item_info)
├── message_handler.py   # 消息处理管线
├── cookie_manager.py    # Cookie 加载/热重载/持久化
├── manual_mode.py       # 人工接管管理器
├── web/
│   ├── app.py           # FastAPI 轻量管理界面
│   ├── static/          # 前端资源
│   └── templates/       # Jinja2 模板
└── config.py            # Lite 专用配置（端口/心跳间隔等）
```

### 2.5 Lite 消息处理管线

```
闲鱼 WebSocket 消息
  │
  ▼
ws_client.py: 接收 → JSON解析 → ACK确认
  │
  ▼
message_handler.py:
  ├─ decrypt() 解密（Base64 → JSON/MessagePack）
  ├─ 过滤：非聊天消息/过期消息/输入状态 → 丢弃
  ├─ 卖家消息？
  │   ├─ 回显过滤（recent_sent_messages 匹配）
  │   ├─ 人工接管切换（关键词检测）
  │   └─ 其他 → 记录为卖家发言
  ├─ 双层去重（精确+内容）
  ├─ 人工模式检查 → 跳过
  ├─ 加入上下文
  ├─ 获取商品信息（DB缓存 → API）
  │
  ▼
意图路由:
  ├─ 快递关键词命中 → 信息提取 → 报价引擎 → 模板输出
  ├─ 议价关键词命中 → 议价Agent（temperature递增）
  ├─ 意图规则命中 → 规则回复（虚拟商品/代下单等）
  └─ 兜底 → 默认回复 或 LLM生成
  │
  ▼
合规检查 → 安全过滤 → send_msg() → WebSocket发出
```

### 2.6 配置体系

Lite 模式复用 `config/settings.yaml`，新增 `lite` 段：

```yaml
lite:
  enabled: true
  web_port: 8066
  ws:
    url: "wss://wss-goofish.dingtalk.com/"
    heartbeat_interval: 15
    heartbeat_timeout: 20
    reconnect_delay: 5
    reconnect_backoff: 1.5       # 指数退避
    reconnect_max_delay: 60
  cookie:
    source: "cookie.txt"         # cookie.txt | .env | env
    hot_reload: true
    poll_interval: 30
  manual_mode:
    toggle_keyword: "。"
    timeout_minutes: 60
  message:
    expire_seconds: 300
    dedup_ttl_hours: 24          # 内容去重过期时间
```

---

## 3. 从 AutoAgent 移植清单

### 3.1 WebSocket 协议层

**来源**: `XianyuApis.py` + `main.py (XianyuLive类)`
**目标**: `src/lite/ws_client.py` + `src/lite/api_client.py`

| 移植内容 | 改造 |
|----------|------|
| WS连接 `wss://wss-goofish.dingtalk.com/` | 保持 |
| `/reg` 注册消息格式（app-key, token, UA, device_id） | 保持 |
| `/!` 心跳包 + 超时检测 | 加指数退避重连 |
| `/r/MessageSend/sendByReceiverScope` 发送 | 保持 |
| `/r/SyncStatus/ackDiff` 同步差异 | 保持 |
| ACK确认（code:200 + mid/sid） | 保持 |
| `get_token()` 签名+重试 | 递归→循环重试，加最大次数 |
| `get_item_info()` 商品详情 | 保持，加缓存 |
| `hasLogin()` 登录校验 | 递归→循环重试 |
| Token刷新→重连联动 | 保持，加flag机制 |
| `generate_sign(t, token, data)` MD5签名 | 保持 |
| `generate_device_id(user_id)` | 保持 |

**重连策略升级**：
```python
# AutoAgent: 固定5秒
await asyncio.sleep(5)

# Lite Mode: 指数退避 + jitter
delay = min(base_delay * (backoff ** attempt) + random.uniform(0, 1), max_delay)
await asyncio.sleep(delay)
```

### 3.2 MessagePack 解码器

**来源**: `xianyu_utils.py → MessagePackDecoder`
**目标**: `src/core/msgpack.py`

- 完整移植纯 Python MessagePack 解码器（零外部依赖）
- 移植 `decrypt()` 多级解码链：Base64 → JSON → MessagePack → hex dump
- 移植 `trans_cookies()` Cookie 解析
- 移植 `generate_mid()` / `generate_uuid()` 消息ID生成

**改造**：加类型注解，加 `__all__` 导出控制。

### 3.3 Cookie 管理

**来源**: `utils/config_loader.py` + `XianyuApis.update_cookies_file()`
**目标**: `src/lite/cookie_manager.py`

| 功能 | 说明 |
|------|------|
| 三级优先级加载 | cookie.txt → .env → 环境变量 |
| validate_cookies() | 必须包含 `unb` 字段 |
| 热重载 | 文件mtime变化检测 → 自动刷新 → 触发Token刷新 → WS重连 |
| Web更新 | POST /api/cookie 更新 → 同时写cookie.txt和.env |
| 去重持久化 | clear_duplicate_cookies() + 回写 |

**改造**：路径硬编码改为配置注入；加 `CookieManager` 类封装（不用裸函数+全局变量）。

### 3.4 双层消息去重

**来源**: `ChatContextManager` 的 `message_replies` + `message_content_replies`
**目标**: `src/modules/context/dedup.py`（共享层）

| 层 | 机制 | 用途 |
|----|------|------|
| 精确去重 | MD5(chat_id + create_time + content) | 防WS重复投递 |
| 内容去重 | MD5(chat_id + normalized_content) | 防用户重复发送 |

**改造**：
- MD5 → SHA-256
- 内容去重加 TTL（默认24小时），过期后允许重新回复
- 精确去重保留7天自动清理

### 3.5 规则优先+LLM兜底的信息提取

**来源**: `XianyuAgent.py → _extract_info_fast / _extract_info_with_llm / _extract_info_from_context`
**目标**: `src/modules/extract/`（共享层）

```
src/modules/extract/
├── __init__.py
├── fast.py          # 正则快速提取（地址/重量/尺寸/快递/禁寄）
├── llm.py           # LLM兜底提取（动态城市列表+可用快递注入）
├── context.py       # 上下文补齐（从历史消息补全缺失字段）
└── models.py        # ExtractedInfo dataclass
```

**关键移植细节**：
- 尺寸正则模式统一为常量（当前重复3处）
- 斤→kg双重转换保留（prompt指示+后处理校验）
- 动态城市列表注入（`_get_related_cities` 只注入20个相关城市）
- temperature=0.1 + max_tokens=200

### 3.6 禁寄双重检查

**来源**: `XianyuAgent.py` 禁寄逻辑
**目标**: `src/modules/extract/prohibited.py`（共享层）

```
Layer 1: LLM提取 → is_prohibited + reason
Layer 2: 当前消息关键词校验
  ├─ 包含禁寄词 → 确认禁寄
  └─ 不包含 → 判定上下文污染 → 覆盖为非禁寄
```

关键词列表外置到 `config/prohibited_keywords.yaml`。

### 3.7 人工接管模式

**来源**: `main.py (XianyuLive)` 人工模式逻辑
**目标**: `src/lite/manual_mode.py`

| 功能 | 说明 |
|------|------|
| 关键词切换 | 卖家发送"。"→ 该会话切换人工/自动 |
| 超时恢复 | 默认1小时后自动恢复自动模式 |
| 卖家回显过滤 | recent_sent_messages + 精确/路线/价格模糊匹配 |

**改造**：关键词和超时时间从配置读取。

### 3.8 省市映射表外置

**来源**: `XianyuAgent.py` 的 200+行城市列表 + 500+行 `_city_to_province` 映射
**目标**: `src/data/geo/cities.json`（共享层）

```json
{
  "provinces": {
    "浙江": ["杭州", "宁波", "温州", "绍兴", ...],
    "广东": ["广州", "深圳", "东莞", "佛山", ...],
    ...
  },
  "special": {
    "内蒙古": "内蒙古",
    "广西": "广西",
    ...
  }
}
```

新建 `GeoResolver` 类：
- 从 JSON 加载，运行时构建反向索引（城市→省份）
- 支持模糊匹配（去后缀/包含/别名）
- 替代硬编码在代码中的700+行映射表

---

## 4. 不移植清单

| AutoAgent 设计 | 理由 |
|----------------|------|
| **5353行单文件 main.py** | 架构反模式。拆为独立模块。 |
| **3000+行内嵌HTML** | `render_template_string()` 内嵌HTML无法维护。Lite Web UI 用 Jinja2模板+静态文件分离。 |
| **全局变量共享状态** | `_xianyu_live_instance` / `_bot_instance` 全局变量。改为依赖注入。 |
| **死代码路由系统** | `IntentRouter`/`PriceAgent`/`TechAgent`/`ClassifyAgent` 已退化为死代码。不移植，用 xianyu-openclaw 现有的意图规则配置替代。 |
| **Flask Web服务器** | 单线程Flask + daemon线程。Lite用 FastAPI + uvicorn（异步原生）。 |
| **日志正则指标解析** | `get_auto_reply_metrics()` 通过正则扫日志。改用内存计数器 + Prometheus 格式。 |
| **递归重试** | `hasLogin()` 递归重试可能栈溢出。改为循环重试+最大次数。 |
| **议价次数双重递增 Bug** | main.py L818-822 重复递增议价计数。修复，不复现。 |
| **同步阻塞 bot.generate_reply()** | 虽用 `to_thread` 包装但消息串行处理。Lite用 `asyncio.create_task()` 并行处理。 |
| **固定5秒重连** | 无指数退避。改为退避+jitter。 |
| **last_intent/last_agent 状态** | 被设置但从不消费的死代码。不移植。 |
| **`format_mode='llm'` 但不外发** | LLM格式化结果只写日志，配置项无效。不移植。 |
| **硬编码快递名识别（6家）** | Excel导入器只识别6家快递。改为配置驱动。 |

---

## 5. 实施路线图

### Phase 1（第1周）：核心WS连接+自动回复

**目标**：能收到闲鱼消息并自动回复。

| 天 | 任务 | 产出 |
|----|------|------|
| D1 | 创建 `src/lite/` 目录结构 + `__main__.py` 入口 | `python -m src.lite --help` 能运行 |
| D1 | 移植 `src/core/msgpack.py`（MessagePack解码器+decrypt） | 单元测试通过 |
| D2 | 移植 `src/lite/api_client.py`（get_token/get_item_info/签名） | Token获取成功 |
| D2 | 移植 `src/lite/cookie_manager.py`（三级加载+校验） | Cookie解析正确 |
| D3 | 移植 `src/lite/ws_client.py`（连接/注册/心跳/ACK/收发消息） | WS连接成功，能收到消息 |
| D3 | 实现指数退避重连+Token刷新→重连联动 | 断线后自动恢复 |
| D4 | 移植 `src/modules/context/`（上下文管理+双层去重） | 消息不重复处理 |
| D4 | 实现 `src/lite/message_handler.py`（解密→过滤→路由→回复） | 收到消息→默认回复 |
| D5 | 移植人工接管+卖家回显过滤 | 发"。"能切换模式 |
| D5 | 端到端测试：Cookie→WS→收消息→默认回复→发送 | 完整链路跑通 |

**验收标准**：
- [x] `python -m src.lite` 一条命令启动
- [x] 成功连接闲鱼WS，收到买家消息
- [x] 自动发送默认回复
- [x] 断线5次内均自动重连
- [x] 卖家发"。"可切换人工模式
- [x] 同一消息不重复回复

### Phase 2（第2周）：报价引擎集成+议价

**目标**：买家问价能自动报价，能议价。

| 天 | 任务 | 产出 |
|----|------|------|
| D1 | 新建 `src/modules/extract/`（信息提取共享模块） | FastExtractor单测通过 |
| D1 | 移植 `src/data/geo/cities.json` + `GeoResolver` | 城市→省份映射正确 |
| D2 | 移植LLM提取+禁寄双重检查 | LLMExtractor+prohibited单测通过 |
| D2 | 对接现有报价引擎（`src/modules/quote/`） | 提取结果→QuoteRequest→QuoteResult |
| D3 | 移植Excel自适应导入器作为 `ExcelProvider` | 导入韵达Excel成功报价 |
| D3 | 实现议价Agent（temperature递增策略） | 第1次议价温和，第3次强硬 |
| D4 | message_handler集成：快递关键词→提取→报价→模板回复 | 端到端报价跑通 |
| D4 | 意图规则集成（虚拟商品/代下单等配置化回复） | 命中规则直接回复 |
| D5 | 集成测试：多轮对话（问价→补参→报价→议价） | 完整对话流跑通 |

**验收标准**：
- [x] 买家发"杭州到北京 5kg"→返回多快递报价
- [x] 买家只发"寄到北京"→追问重量和出发地
- [x] 禁寄物品正确拦截
- [x] 议价3次后语气明显变化
- [x] Excel导入→SQLite→报价链路完整

### Phase 3（第3周）：轻量Web UI+数据看板

**目标**：提供可视化管理界面。

| 天 | 任务 | 产出 |
|----|------|------|
| D1 | 搭建 FastAPI + Jinja2 框架（`src/lite/web/`） | localhost:8066 能访问 |
| D1 | 实现 Cookie 管理页（查看/更新/上传） | Web更新Cookie→热重载生效 |
| D2 | 实现消息看板（最近对话/实时消息流SSE） | 实时看到消息收发 |
| D2 | 实现服务控制（启动/挂起/恢复状态切换） | Web控制服务状态 |
| D3 | 实现报价统计（成功率/耗时P50/P90/命中率） | 内存计数器+看板展示 |
| D3 | 实现路线管理（导入Excel/查看路线覆盖） | Web导入Excel |
| D4 | 实现日志查看（文件浏览+实时流） | 在线看日志 |
| D4 | pip打包配置（setup.py/pyproject.toml + entry_point `xianyu-lite`） | `pip install` 可用 |
| D5 | 文档更新 + README Lite Mode 章节 + 端到端验收 | 文档完整 |

**验收标准**：
- [x] `pip install xianyu-openclaw && xianyu-lite start` 首次体验 <2分钟
- [x] Web UI 可管理 Cookie、查看消息、查看统计
- [x] 报价成功率、响应耗时可视化
- [x] Excel 价格表可通过 Web 导入

---

## 6. 启动体验对比

### Before（Full Mode）

```
# 前置：安装 Docker Desktop（几百MB下载，Windows可能要开WSL2）

git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
cp .env.example .env
vim .env                    # 填 AI Key + Cookie + 密码 + Gateway Token
docker compose up -d        # 拉镜像 ~2GB，首次5-10分钟
                            # 等 openclaw-gateway 启动...
                            # 等 Chromium 下载...
                            # 等 Python 依赖安装...
docker compose exec -it openclaw-gateway openclaw devices list
docker compose exec -it openclaw-gateway openclaw devices approve <requestId>
                            # 配对完成
# 打开 http://localhost:8080
# 总耗时：15-30 分钟（首次）
```

**痛点**：Docker不熟练的用户常卡在 WSL2/Hyper-V、镜像拉取超时、配对流程。

### After（Lite Mode）

```
pip install xianyu-openclaw        # ~30秒
cp .env.example .env
vim .env                           # 只需填2项：Cookie + AI Key
python -m src.lite                 # 3秒启动

# 输出：
# 🐟 xianyu-openclaw Lite Mode v4.6.0
# ✅ Cookie 有效 (用户: xxx)
# ✅ WebSocket 已连接
# ✅ 报价引擎就绪 (4家快递, 1,247条路线)
# ✅ Web管理界面: http://localhost:8066
# 📡 开始监听消息...

# 总耗时：2 分钟
```

### 体验对比表

| 维度 | Full Mode | Lite Mode |
|------|-----------|-----------|
| 前置依赖 | Docker 20.10+ | Python 3.10+ |
| 磁盘占用 | ~3GB（镜像+Chromium） | ~50MB（pip包） |
| 首次启动 | 15-30分钟 | 2分钟 |
| 配置项 | 6+ 必填 | 2 必填（Cookie + AI Key） |
| 配对流程 | 需要 | 不需要 |
| 内存占用 | ~800MB（Gateway+Chromium+Python） | ~100MB（纯Python） |
| 技术门槛 | 需要Docker知识 | 会 `pip install` 就行 |

---

## 附录：文件变更清单

### 新增文件

```
src/lite/                        # Lite Mode 独有
src/core/msgpack.py              # MessagePack 解码器（共享）
src/modules/extract/             # 信息提取模块（共享）
src/modules/context/             # 上下文管理模块（共享）
src/data/geo/cities.json         # 省市映射数据（共享）
config/prohibited_keywords.yaml  # 禁寄关键词配置
```

### 修改文件

```
config/settings.yaml             # 新增 lite 配置段
setup.py / pyproject.toml        # 新增 xianyu-lite entry_point
README.md                        # 新增 Lite Mode 章节
```

### 不动的文件

```
src/modules/quote/               # 报价引擎原样复用
src/modules/compliance/          # 合规策略原样复用
src/core/                        # 现有核心模块不变
skills/                          # OpenClaw 技能不变
docker-compose.yml               # Full Mode 不受影响
```
