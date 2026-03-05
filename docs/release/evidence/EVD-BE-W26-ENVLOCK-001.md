# EVD-BE-W26-ENVLOCK-001 — 测试环境指纹固化与回归证据

## 1) ENV_MISMATCH 根因与修复

### 根因
- 仓库存在多套入口（`python3` / `pytest` / `venv` / `.venv` / `.venv312`），导致解释器、pytest、依赖集不一致。
- `setup.sh` 仍使用 `venv` + `python3`（本机为 3.9.6），与当前测试主环境（3.12）漂移。

### 修复
- 新增固定入口脚本：`scripts/qa/lock_test_env.sh`
  - 固定使用 `XY_VENV_DIR`（默认 `.venv312`）
  - 输出环境指纹（python/pytest路径与版本、requirements sha、pip freeze sha）
  - 统一用 `venv python -m pytest` 执行测试
- 收敛 setup 入口：`setup.sh`
  - 默认 `python3.12` + `.venv312`
  - 避免落回系统 `python3`（3.9）触发漂移
- README 本地开发测试入口更新为：
  - `bash scripts/qa/lock_test_env.sh -q tests/`

---

## 2) 环境指纹（非 mock）

命令：
```bash
bash scripts/qa/lock_test_env.sh --fingerprint-only
```

日志：`docs/release/evidence/EVD-BE-W26-ENVLOCK-001/01-env-fingerprint.log`

关键结果：
- venv: `.venv312`
- python: `3.12.12`
- pytest: `8.4.2`
- pytest path: `.venv312/lib/python3.12/site-packages/pytest/__init__.py`
- requirements sha256: `e7af862666d0a0c06530c2b9e6fce407d8c50792b25e4d51fcfa5772c725ab45`
- requirements.lock sha256: `519976f3c4e3fe7c4d81350d15788169339bd7d44a432a43f397c0354775adba`
- pip freeze sha256: `74e9364ac5aad79de680ffdc98caf5d34638e3c7abd02acadaedb9d510c4f419`

---

## 3) 回归测试证据

命令：
```bash
bash scripts/qa/lock_test_env.sh -q -o addopts='' \
  tests/test_lite_cookie_renewal.py \
  tests/test_lite_cookie_renewal_automation.py \
  tests/test_lite_stack.py
```

日志：`docs/release/evidence/EVD-BE-W26-ENVLOCK-001/02-regression.log`

结果：
- `25 passed in 4.03s`

---

## 4) 非 mock 门禁证据

命令：
```bash
./.venv312/bin/python -m src.cli doctor --strict --skip-gateway --skip-quote
rg -n "allow_mock" config/config.example.yaml src/core/startup_checks.py
```

日志：
- `docs/release/evidence/EVD-BE-W26-ENVLOCK-001/03-doctor-strict.log`
- `docs/release/evidence/EVD-BE-W26-ENVLOCK-001/04-nonmock-gate.log`

关键结果：
- Doctor 检查项显示：`报价Mock门禁: allow_mock=false（non-production）`
- 配置默认：`config/config.example.yaml` 中 `allow_mock: false`
- 启动门禁代码存在生产阻断逻辑：`src/core/startup_checks.py`

> 说明：doctor strict 非 0 的原因是本地未配置 `.env` / cookie / AI key，不属于 ENV_MISMATCH；与测试执行入口一致性无关。
