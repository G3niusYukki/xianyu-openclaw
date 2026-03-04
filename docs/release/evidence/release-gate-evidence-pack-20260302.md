# 发布门禁证据包（可执行清单 + 回滚演练证据）

- 任务ID：XY-ALLIN-SRE-20260302-2335
- 生成时间：2026-03-02 23:38 (GMT+8)
- 工作目录：`/Users/brianzhibo/Documents/New project/xianyu-openclaw`
- 当前分支：`fix/workflow-e2e-gate-clean-20260302`
- 当前提交：`b17f80b`

---

## 1) 可执行门禁清单（Copy & Run）

```bash
cd "/Users/brianzhibo/Documents/New project/xianyu-openclaw"

# A. 预检（运行时/配置/依赖）
.venv/bin/python -m src.cli module --action check --target presales --strict

# B. 最小E2E门禁
.venv/bin/pytest -q -o addopts='' tests/test_e2e_minimal_closed_loop.py::test_minimal_e2e_inquiry_reprice_callback_writeback

# C. 全量回归 + 覆盖率统一口径
.venv/bin/python -m pytest --tb=short -q --cov=src --cov-report=json:coverage_qa_check.json 2>&1 | tee qa_report.txt

# D. 回滚/恢复演练（受控）
.venv/bin/python -m src.cli module --action status --target presales --window-minutes 30
.venv/bin/python -m src.cli module --action recover --target presales --stop-timeout 6
.venv/bin/python -m src.cli module --action status --target presales --window-minutes 30
.venv/bin/python -m src.cli module --action logs --target presales --tail-lines 80
```

---

## 2) 已落地证据

### 2.1 QA门禁证据（已有）
- 文件：`docs/qa-release-verdict.md`
- 关键结论：
  - `663 passed in 91.22s`
  - 覆盖率 `98.91%`
  - QA判定：`Go（有条件）`

### 2.2 SRE稳定性审查（已有）
- 文件：`docs/reviews/xy-audit-05-sre.md`
- 关键结论：
  - 恢复链路（token_error / cookie_update_required / risk_control / recover）已具备
  - 缺口：30分钟恢复SOP与告警闭环需补齐

### 2.3 回滚演练证据（本次新增）
- 文件：`docs/release/evidence/rollback-drill-20260302-233707.log`
- 演练命令与结果摘要：
  - `module check --strict`：`ready=true`，无 critical blocker
  - 演练前状态：`pid=31988 alive=false`
  - 执行 `module recover`：
    - stop: `pid_not_alive`（符合幂等）
    - cleanup: 删除 `data/module_runtime/presales.json`
    - start: `started=true pid=47804`
    - recovered: `true`
  - 演练后状态：`pid=47804 alive=true`
  - 日志证据包含：
    - `Connected to Goofish WebSocket transport`
    - `FAIL_SYS_USER_VALIDATE` / `cookie update` 风险信号
- 环境恢复动作（避免副作用）：
  - 已执行：`.venv/bin/python -m src.cli module --action stop --target presales --stop-timeout 6`
  - 结果：`stopped=true pid=47804`

---

## 3) 门禁结论（本轮）

- **发布建议：No-Go（条件未满足）**
- 理由：
  1. 代码质量门禁（测试/覆盖率）已满足；
  2. 回滚命令幂等性与可执行性已有演练证据；
  3. 但线上放行仍缺 **P0可观测闭环证据**（告警通道启用+恢复超时告警+30分钟SOP实操记录）。

---

## 4) 上线前最小补齐项（P0）

1. 启用并验证4类通知：启动/告警/恢复/心跳（留存消息截图或消息ID）。
2. 补齐 `incident-presales-30min` 值班SOP（0-5/5-10/10-20/20-30分钟动作）。
3. 将覆盖率与diff-cover门槛收敛到CI强制门禁（防止本地与CI口径漂移）。
4. 再做一次“故障注入→recover→恢复确认”演练并记录RTO。

---

## 5) 放行判定建议

- **短结论**：当前不建议直接上线生产流量。
- **可放行条件**：完成上述P0项后，进入“小流量灰度 + 30分钟观察窗口”，观察无异常再全量。
