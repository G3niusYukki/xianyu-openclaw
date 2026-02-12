# 依赖管理指南
# Dependency Management Guide

## 依赖文件说明

### requirements.txt
主依赖文件，定义项目所需的Python包及其版本范围。

- 使用范围约束（`>=X.Y.Z,<A.B.C`）确保兼容性
- 允许小版本更新以获取bug修复
- 防止大版本更新导致的破坏性变更

### requirements.lock
依赖锁定文件，记录经过测试的确切版本。

- 确保所有环境使用完全相同的依赖版本
- 提高可复现性
- 用于生产环境部署

## 安装依赖

### 开发环境
```bash
# 安装主依赖（允许小版本更新）
pip install -r requirements.txt

# 或者安装锁定版本（推荐用于CI/CD）
pip install -r requirements.lock
```

### 生产环境
```bash
# 安装锁定版本，确保完全一致
pip install -r requirements.lock
```

## 更新依赖

### 更新到最新兼容版本
```bash
# 安装pip-tools（如果未安装）
pip install pip-tools

# 编译锁定文件（会自动更新到最新兼容版本）
pip-compile requirements.txt --output-file requirements.lock

# 查看变化
git diff requirements.lock
```

### 更新特定包
```bash
# 更新特定包到最新版本
pip install --upgrade package_name

# 重新编译锁定文件
pip-compile requirements.txt --output-file requirements.lock
```

### 审查依赖更新
```bash
# 查看过期的包
pip list --outdated

# 安全审计
pip-audit

# 或使用safety
pip install safety
safety check
```

## 最佳实践

1. **开发时**：使用`requirements.txt`安装，允许小版本更新
2. **测试时**：使用`requirements.lock`确保测试一致性
3. **部署时**：必须使用`requirements.lock`确保生产环境一致性
4. **定期更新**：每月检查一次依赖更新，测试后再合并
5. **安全优先**：及时更新有安全漏洞的依赖

## 虚拟环境管理

### 使用venv
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Linux/Mac:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 安装依赖
pip install -r requirements.lock
```

### 使用poetry（可选）
```bash
# 安装poetry
pip install poetry

# 初始化项目
poetry init

# 添加依赖
poetry add pyyaml
poetry add --group dev pytest

# 安装所有依赖
poetry install
```

## 依赖版本说明

| 包名 | 最小版本 | 最大版本 | 说明 |
|------|---------|---------|------|
| pyyaml | 6.0.1 | <7.0.0 | YAML配置解析 |
| pydantic | 2.5.0 | <3.0.0 | 数据验证 |
| httpx | 0.25.0 | <0.30.0 | 异步HTTP客户端 |
| openai | 1.12.0 | <2.0.0 | OpenAI API客户端 |

## 故障排查

### 版本冲突
```bash
# 查看依赖树
pipdeptree

# 找出冲突的包
pip check
```

### 清理缓存
```bash
# 清理pip缓存
pip cache purge

# 或删除旧版本包
pip-autoremove
```
