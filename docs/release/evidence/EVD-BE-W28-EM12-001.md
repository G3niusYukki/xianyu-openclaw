# EVD-BE-W28-EM12-001（W28 / E-M1 & E-M2 后端证据）

- taskId: `XY-WAVE28-2233-BE-EM1-EM2-EVIDENCE`
- scope: `xianyu-only`
- gate_rule: `BLOCK_AND_ESCALATE`
- evidence_id: `EVD-BE-W28-EM12-001`
- 生成时间: `2026-03-05 22:4x CST`

## E-M1：commit SHA + git diff + remote_mock=0

### 已补齐
1. commit SHA（后端相关基线）
   - `5326313f325da3d293483e0d4f48f31f8ad37095`
   - 证据文件：`docs/release/evidence/EVD-BE-W28-EM12-001/01-commit-sha.txt`
2. git diff/stat
   - 证据文件：`docs/release/evidence/EVD-BE-W28-EM12-001/01-git-diff-stat.txt`

### 阻塞项（BLOCK）
- 执行 `rg -n "remote_mock" src` 结果为 **4**（非 0）
  - 证据文件：`docs/release/evidence/EVD-BE-W28-EM12-001/01-remote-mock-src.txt`
- 对照：`rg -n "remote_mock" server/src` 结果为 **0**
  - 证据文件：`docs/release/evidence/EVD-BE-W28-EM12-001/01-remote-mock-server-src.txt`

> 判定：按验收口径（`src` 必须 remote_mock=0）当前不满足，E-M1 维持 BLOCK。

---

## E-M2：provider 非mock链路日志 + QA回执绑定

### 已补齐
1. provider 非mock链路日志（remote provider -> `remote_vendor`）
   - 证据文件：`docs/release/evidence/EVD-BE-W28-EM12-001/02-provider-nonmock.log`
   - 关键结果：
     - `provider= remote_vendor`
     - `source= remote_vendor`
     - `total_fee= 12.5`

2. QA回执绑定
   - QA主回执：`docs/release/evidence/qa-close-loop-20260303-1040.md`
   - 关键回执摘录：`docs/release/evidence/EVD-BE-W28-EM12-001/03-qa-receipt-extract.txt`
   - 绑定点（同一证据链）：
     - QA任务ID：`XY-CLOSELOOP-QA-20260303-1040`
     - 最小E2E：PASS
     - 关键回归：PASS（21/21）
     - 预检：PASS（ready=true）

> 判定：E-M2 所需“非mock provider链路 + QA回执绑定”已形成可复核材料。

---

## 总结（按 gate_rule）

- E-M1：**BLOCK**（`src` 下 `remote_mock` 计数=4，不满足=0）
- E-M2：**READY**（已补齐）

最终状态：**BLOCK_AND_ESCALATE**（不可宣告全量通过）。