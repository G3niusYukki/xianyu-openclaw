# 上线与回滚清单

## 1. 发布前检查
- 后端依赖安装完成：`./.venv/bin/pip install -r requirements.txt`
- 前端依赖安装完成：`npm install --prefix web/frontend`
- 后端测试通过：`./.venv/bin/pytest -q tests/test_config.py tests/test_modules.py tests/test_integration.py tests/test_tasks_api.py`
- 前端构建通过：`npm run build --prefix web/frontend`
- API 健康检查通过：`GET /api/health`
- 关键接口烟测通过：
  - `POST /api/products/publish`
  - `POST /api/operations/polish/batch`
  - `GET /api/analytics/products/performance`
  - `GET /api/accounts/health`
  - `POST /api/tasks` + `POST /api/tasks/{task_id}/run`

## 2. 运行时配置检查
- `config/config.yaml` 或 `config/config.example.yaml` 配置合法
- 环境变量已配置：
  - `OPENAI_API_KEY`/`DEEPSEEK_API_KEY`（按实际 provider）
  - `XIANYU_COOKIE_1` 等账号 cookie
- `data/` 目录可写
- `logs/` 目录可写

## 3. 依赖产物策略
- 保留并提交前端锁文件：`web/frontend/package-lock.json`
- 不提交依赖目录：`web/frontend/node_modules/`（已在 `.gitignore` 忽略）
- Python 依赖通过 `requirements.txt` + `requirements.lock` 管控

## 4. 上线后验证
- 打开前端页面：
  - `/publish` 发布一次测试商品
  - `/operations` 执行一次批量擦亮
  - `/analytics` 读取趋势与报表
  - `/accounts` 新增/编辑/禁用账号
- 检查数据库文件和日志是否持续写入
- 检查任务创建、立即执行、启停、删除流程

## 5. 回滚步骤
- 代码回滚到上一稳定版本（tag 或 commit）
- 恢复 `config` 到上一版本备份
- 恢复 `data/agent.db` 与 `data/scheduler_tasks.json`（如有结构不兼容）
- 重启服务并执行 `/api/health` 与关键接口烟测
- 若前端异常，回滚前端构建产物到上一版本
