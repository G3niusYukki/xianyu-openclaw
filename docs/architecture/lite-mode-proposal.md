# API-first Runtime Proposal

这个文件替代旧的 Lite / Full / OpenClaw 方案说明。

## 运行模式

### 默认模式

- React 工作台
- Python 核心
- Node 可选代理

### 补充链路

- 商品 / 订单 / 配置 / 自动上架：优先 Open Platform API
- 消息：优先 Python WS
- 极少数站点态能力：保留站点侧补充实现

## 原则

- 不依赖 OpenClaw Gateway。
- 不要求 Chromium / Docker 才能首启。
- 浏览器能力只作为补充，不作为主路径。

## 对比旧方案

| 维度 | 旧口径 | 当前口径 |
|---|---|---|
| 主控制面 | Dashboard + Gateway 叙事 | React 工作台 |
| 核心后端 | 混合 | Python |
| Node | 混合业务 | 薄代理 |
| 商品/订单 | 浏览器和历史链路混用 | Open Platform API 优先 |
| 消息 | 多链路混用 | WS 优先，站点侧补充 |

## 迁移结论

- 仓库名保持不变。
- 内部仍会保留少量 legacy gateway/browser runtime 代码，供兼容和补充链路使用。
- 对外文档和默认启动方式以 API-first 为准。
