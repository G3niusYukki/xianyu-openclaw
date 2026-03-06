# 项目计划

## 目标

把仓库收敛到一条明确主线：

1. 去掉 OpenClaw 作为运行前提。
2. 保留 Python 作为唯一核心业务引擎。
3. 商品、订单、配置、自动上架优先走闲管家 / Open Platform API。
4. API 无法覆盖的能力，才保留 WS 或站点侧补充链路。
5. React 页面全部接真实接口，不提供展示型 mock。

## 当前架构

- `client/`：React 运营工作台
- `server/`：Node 薄代理与 webhook 校验
- `src/`：Python 核心业务与 Dashboard API

## 已完成

- 用 PR #41 的工作台信息架构替换旧 `client/server` SaaS 壳层。
- 配置中心改成前端直连 Python 配置接口。
- 商品、订单、自动上架前端全部切到真实 Python 接口。
- 消息中心移除本地伪发送，只展示真实统计和日志。
- Node 收窄为 `config` 代理和 `xgj` webhook / proxy。
- 删除旧 `review/payment/auth` 路由和对应测试。

## 下一阶段

### Phase 1

- 继续增强 Python 配置 contract。
- 补齐多店铺切换和真实账号映射。
- 为自动上架链路补更多集成测试。

### Phase 2

- 评估是否将 Node webhook 验签逻辑下沉到 Python。
- 收敛历史 Dashboard HTML 与新 React 工作台之间的重复能力。

### Phase 3

- 对消息链路做 API-first + WS fallback 的统一状态面板。
- 清理剩余“Legacy Gateway / OpenClaw”内部命名。

## 非目标

- 不恢复旧 code-review SaaS 逻辑。
- 不把 Node 重新做成主业务后端。
- 不为了页面演示引入 mock 数据。
