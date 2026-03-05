# QA回执同SHA绑定（W34 / G2）

- evidence_id: `EVD-BE-W34-G2-001`
- scope: `xianyu-only`
- gate_rule: `BLOCK_AND_ESCALATE`
- commit_sha: `1e40829f847410612c7e2967311d83995aea667c`

## 绑定对象
- QA回执：`docs/release/evidence/qa-close-loop-20260303-1040.md`
- QA回执文件SHA256：见 `06_qa_receipt_extract_and_binding.txt`

## G2验收映射
1. 动态provider非mock全链日志（原始命令）
   - `03_cmd_provider_dynamic_nonmock.raw.log`
   - 关键字段：`provider= remote_vendor`、`source= remote_vendor`、`allow_mock= False`
2. 原始命令输出（pytest + runtime + guard）
   - `02_cmd_pytest_remote_provider_edges.raw.log`
   - `03_cmd_provider_dynamic_nonmock.raw.log`
   - `04_cmd_nonmock_guard_scan.raw.log`
3. 与QA回执同SHA绑定
   - 代码SHA：`01_cmd_git_rev_parse.raw.log`
   - QA回执摘录+文件哈希：`06_qa_receipt_extract_and_binding.txt`

## 结论
- G2证据链要件已补齐：**非mock动态provider链路 + 原始命令输出 + QA回执绑定（同commit_sha记录）**。
- 若上游将“同SHA”严格定义为“QA回执正文显式包含同一commit字段”，则需QA补发带commit字段回执；当前包已提供可复核的文件哈希与commit并列绑定。
