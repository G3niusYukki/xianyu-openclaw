# XY-WAVE15-1904 前端设计落地报告（闲鱼关键页面）

## 1) 设计 Token 与页面规范对照表

| Token | 值 | 规范意图 | 首页 | 详情 | 发布 | 聊天 | 订单 | 证据ID |
|---|---|---|---|---|---|---|---|---|
| `--xy-bg` | `#f5f7fb` | 全局底色统一，降低视觉噪声 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `--xy-surface` | `#ffffff` | 卡片容器基底，保证信息可读性 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `--xy-brand-500` | `#ff7a00` | 主行动色（CTA） | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001,EVD-003 |
| `--xy-border` | `#e2e8f0` | 分割线与边框统一 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `--xy-shadow` | `0 10px 30px rgba(15,23,42,.08)` | 卡片层级感，避免模板扁平感 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `--xy-radius-lg` | `20px` | 主卡片圆角体系 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `--xy-duration-fast` | `140ms` | hover / tap 微反馈时长 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `--xy-duration-base` | `260ms` | 入场与状态切换时长 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001,EVD-002 |
| `--xy-ease-out` | `cubic-bezier(0.16,1,0.3,1)` | 入场/悬停减速曲线 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-001 |
| `.xy-enter` | `@keyframes xy-enter` | 页面进入动效（轻量） | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-002 |
| `@media (prefers-reduced-motion: reduce)` | 降低动画 | 无障碍与可访问性 | ✅ | ✅ | ✅ | ✅ | ✅ | EVD-002 |

## 2) 页面规范落地摘要（关键页面）

- 首页 `/`：
  - 「主价值叙事 + 快捷入口卡片」双层布局；主 CTA（发布/订单）优先。
- 详情 `/detail`：
  - 采用「主内容 + 侧边交易框」结构；收藏/聊一聊双行动按钮固定可感。
- 发布 `/publish`：
  - 任务流表单（图片区→标题/价格→描述→提交）；未接 API 前仅保留真实空状态。
- 聊天 `/chat`：
  - 左侧会话、右侧消息输入的经典 IM 结构；消息服务未接入时明确空态提示。
- 订单 `/orders`：
  - 状态前置（待付款/待发货/待收货/已完成）；主列表为空时显示可解释空态。

## 3) 证据ID清单

- **EVD-001**: `client/src/index.css`（设计 token 与基础组件类 `xy-card / xy-btn-*`）
- **EVD-002**: `client/src/index.css`（`xy-enter` 动效 + reduced motion 适配）
- **EVD-003**: `client/src/pages/Home.jsx`（首页主 CTA 与关键页面入口卡片）
- **EVD-004**: `client/src/pages/Detail.jsx`（详情页双栏规范）
- **EVD-005**: `client/src/pages/Publish.jsx`（发布任务流与无 mock 约束）
- **EVD-006**: `client/src/pages/Chat.jsx`（聊天布局规范）
- **EVD-007**: `client/src/pages/Orders.jsx`（订单状态前置与空态）
- **EVD-008**: `client/src/App.jsx`、`client/src/components/Navbar.jsx`（路由挂载与导航入口）
- **EVD-009**: 构建验证：`cd client && npm run build` 通过（vite build success）
