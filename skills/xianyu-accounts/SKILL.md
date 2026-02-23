---
name: xianyu_accounts
description: 管理闲鱼账号：查看列表、健康度检查、Cookie 刷新
---

# 闲鱼账号管理

当用户想要查看或管理闲鱼账号时，使用此技能。

## 使用方法

使用 `bash` 工具执行以下命令：

### 查看所有账号

```bash
cd /home/node/.openclaw/workspace && python -m src.cli accounts --action list
```

返回：所有已配置账号的名称、状态、优先级等信息。

### 检查账号健康度

```bash
cd /home/node/.openclaw/workspace && python -m src.cli accounts --action health --id <account_id>
```

返回：账号健康分数、发布数、错误数等指标。

### 验证 Cookie 有效性

```bash
cd /home/node/.openclaw/workspace && python -m src.cli accounts --action validate --id <account_id>
```

返回：Cookie 是否仍然有效。

### 刷新 Cookie

```bash
cd /home/node/.openclaw/workspace && python -m src.cli accounts --action refresh-cookie --id <account_id> --cookie "新的cookie值"
```

## 示例

用户说："我的账号还正常吗" →
```bash
cd /home/node/.openclaw/workspace && python -m src.cli accounts --action list
```
然后对每个账号执行健康检查。

用户说："Cookie 过期了，我更新一下" →
要求用户提供新的 Cookie 值，然后：
```bash
cd /home/node/.openclaw/workspace && python -m src.cli accounts --action refresh-cookie --id account_1 --cookie "用户提供的cookie"
```

## 注意事项

- Cookie 是敏感信息，不要在回复中完整展示
- 如果 Cookie 过期，提醒用户：打开浏览器 -> 登录闲鱼 -> F12 -> Network -> 复制 Cookie
- 健康度低于 50% 的账号建议暂停使用
