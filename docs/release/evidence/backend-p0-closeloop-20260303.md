# 后端 P0 收口证据（并发一致性 / 幂等 / 防重入）

- taskId: `XY-CLOSELOOP-BE-20260303-1040`
- 执行时间: `2026-03-03 10:41 CST`
- 仓库: `/Users/brianzhibo/Documents/New project/xianyu-openclaw`
- 基线提交: `c50f2b9`

## 1) 证据范围与结论

本次仅对后端 P0 指定三项进行可审计验证：

1. **并发一致性（workflow claim/lease CAS）**
2. **幂等（执行完成后重复调用回放，不重复副作用）**
3. **防重入（双触发下 CAS 门控，单次实际执行）**

### 总体判定（本次范围内）

- 并发一致性：**已闭环**
- 幂等：**已闭环**
- 防重入：**已闭环**

---

## 2) 代码证据（实现层）

### A. Workflow 并发认领/状态写入保护

- `src/modules/messages/workflow.py:394` `claim_jobs()`
  - `BEGIN IMMEDIATE` + 条件更新：`WHERE id=? AND status='pending'`
  - 只允许一个执行方从 `pending -> running`
- `src/modules/messages/workflow.py:434` `complete_job()`
  - 条件更新：`WHERE id=? AND status='running' AND lease_until=?`
- `src/modules/messages/workflow.py:457` `fail_job()`
  - 同 lease 条件守卫，避免过期 lease/重复写入覆盖状态

### B. 价格执行 CAS 防重入 + 幂等回放

- `src/modules/orders/price_execution.py:174` 注释与逻辑：
  - 仅允许 `pending -> running` 的 CAS 更新
  - 非 claimed 分支直接 `replay_job(job_id)`（幂等回放）
- `src/modules/orders/price_execution.py:187`
  - 仅 claimed 路径记录 `execution_started`

---

## 3) 测试证据（命令 + 结果）

### 3.1 执行命令（原样）

```bash
.venv/bin/pytest --no-cov -q \
  tests/test_workflow.py::test_workflow_claim_is_not_reentrant_under_double_claim \
  tests/test_workflow.py::test_workflow_complete_and_fail_require_matching_lease \
  tests/test_workflow.py::test_workflow_fail_is_not_reentrant_after_complete \
  tests/test_price_execution.py::test_execute_job_cas_gate_prevents_reentrant_double_run \
  tests/test_price_execution.py::test_execute_job_idempotent_replay_after_finished
```

### 3.2 结果摘要

- `collected 5 items`
- `5 passed in 0.26s`

### 3.3 原始输出文件

- `docs/release/evidence/backend-p0-closeloop-20260303/pytest-p0-concurrency-idempotency-nocov.log`
- `docs/release/evidence/backend-p0-closeloop-20260303/context.txt`
- `docs/release/evidence/backend-p0-closeloop-20260303/sha256.txt`

### 3.4 说明（覆盖率门槛）

仓库 `pytest.ini` 默认启用 `--cov-fail-under=35`。仅执行 5 个定向用例时，总覆盖率会失败（非功能失败）。

为验证 P0 机制本身，使用 `--no-cov` 获取可执行结论；对应失败日志亦保留：

- `docs/release/evidence/backend-p0-closeloop-20260303/pytest-p0-concurrency-idempotency.log`

---

## 4) “已闭环 / 未闭环”边界声明

## 已闭环（本次 task 范围）

1. **并发一致性（workflow）**
   - 双 claim 不会重复认领；lease 不匹配无法 complete/fail 覆盖状态。
2. **防重入（price execution）**
   - 双并发 execute 同一 job，实际外部 `update_price` 只执行一次（`ops.calls == 1`）。
3. **幂等（price execution）**
   - 已完成 job 再执行返回回放，不增加 attempts，不新增重复执行事件。

## 未闭环（本次未覆盖，需单列）

1. **生产级高并发压测证据**（多进程/多实例争抢、长时运行）尚未提供。
2. **真实外部依赖 E2E 证据**（非 Dummy operations_service）尚未纳入本次收口包。
3. **发布门禁全量覆盖率达标**（`--cov-fail-under=35`）不属于本次 5 个定向 P0 用例的通过条件，需在全量/门禁流水线单独完成。

> 结论口径：
> - **后端 P0 机制层（并发一致性、幂等、防重入）= 已闭环**；
> - **发布级/生产级证据层 = 未闭环（需补压测与真实链路证据）**。
