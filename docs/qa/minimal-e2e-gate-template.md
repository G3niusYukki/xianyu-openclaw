# 最小E2E闭环放行证据（统一模板）

- 版本/分支：`<git-commit>`
- 执行时间：`<yyyy-mm-dd hh:mm tz>`
- 执行人：`<name>`
- 环境：`<local/ci>`
- 当前判定：`GO | NO_GO`

---

## 1) 闭环范围（固定口径）

必须覆盖链路：**询价 → 改价 → 回调 → 结果回写**

- 询价：`MessagesService._generate_reply_with_quote`
- 改价：`PriceExecutionService.create_job/execute_job`
- 回调：`OrderFulfillmentService.upsert_order`（支付状态同步）
- 结果回写：`OrderFulfillmentService.trace_order`（订单状态+快照）

## 2) 统一覆盖率口径（单一来源）

- 口径定义：**行覆盖率（line coverage）**
- 采集命令：
  - `pytest --cov=src --cov-report=term-missing --cov-report=json:coverage_qa_check.json`
- 门槛：
  - 全仓最低：`>= 35%`（项目既有门槛）
  - 放行建议：核心链路相关模块维持当前基线，不得回退
- 证据文件：
  - `coverage_qa_check.json`
  - `qa_report.txt`

## 3) 最小E2E用例执行结果（单测ID固定）

- 用例：`tests/test_e2e_minimal_closed_loop.py::test_minimal_e2e_inquiry_reprice_callback_writeback`
- 命令：
  - `.venv/bin/pytest -q -o addopts='' tests/test_e2e_minimal_closed_loop.py::test_minimal_e2e_inquiry_reprice_callback_writeback`
- 结果：`PASS | FAIL`
- 失败摘要：`<如果失败填写>`

## 4) Go / No-Go 门槛清单（任一不满足即 NO_GO）

1. [ ] 最小E2E用例通过（询价→改价→回调→回写）
2. [ ] 改价执行结果落库：`price_update_jobs.status=success`
3. [ ] 订单回调状态映射正确：`已付款 -> paid`
4. [ ] 结果回写完整：`orders.quote_snapshot_json` 非空且可追溯
5. [ ] 覆盖率报告可产出且无回退异常
6. [ ] 无阻断级缺陷（P0/P1）

## 5) 可直接复跑步骤（copy & run）

```bash
cd "/Users/brianzhibo/Documents/New project/xianyu-openclaw"

# 1) 跑最小闭环
.venv/bin/pytest -q -o addopts='' tests/test_e2e_minimal_closed_loop.py::test_minimal_e2e_inquiry_reprice_callback_writeback

# 2) 跑统一覆盖率口径
.venv/bin/pytest --cov=src --cov-report=term-missing --cov-report=json:coverage_qa_check.json > qa_report.txt

# 3) 快速核验门槛证据
.venv/bin/python - <<'PY'
import json
from pathlib import Path

cov = json.loads(Path('coverage_qa_check.json').read_text(encoding='utf-8'))
print('total_line_coverage=', round(cov['totals']['percent_covered'], 2))
print('report_exists=', Path('qa_report.txt').exists())
PY
```

## 6) 当前判定

- 判定：`<GO | NO_GO>`
- 依据：`<对照门槛逐条说明>`
