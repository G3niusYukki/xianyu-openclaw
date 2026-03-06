# 前端页面与设计映射

## 当前页面

| 页面 | 路由 | 数据来源 | 说明 |
|---|---|---|---|
| 工作台 | `/dashboard` | Python `/api/status` `/api/summary` `/api/recent-operations` | 真实总览 |
| 商品管理 | `/products` | Python `/api/xgj/products` | 商品列表与上下架 |
| 自动上架 | `/products/auto-publish` | Python `/api/listing/*` | AI 文案、图片、本地预览、发布 |
| 订单中心 | `/orders` | Python `/api/xgj/orders` | 真实订单、改价、发货 |
| 消息中心 | `/messages` | Python `/api/status` `/api/logs/content` | 真实统计和日志 |
| 店铺管理 | `/accounts` | Python `/api/accounts` | 真实账号状态和 Cookie |
| 系统配置 | `/config` | Python `/api/config*` | 统一配置入口 |
| 数据分析 | `/analytics` | Python `/api/trend` `/api/top-products` | 真实趋势和热门商品 |

## 设计约束

- 使用统一的 `xy-*` 设计 token。
- 不提供页面演示用 mock 数据。
- 无数据时展示空状态，而不是伪造样本。
- 视觉风格围绕“运营台”而不是通用 SaaS 模板。

## 已移除页面

以下旧页面已退出主线：

- `Login`
- `Register`
- `Review`
- `Pricing`
- `History`
- `Chat`
- `Detail`
- `Publish`
- `Settings`

这些页面来自旧的 code-review 产品壳层，与当前业务无关。
