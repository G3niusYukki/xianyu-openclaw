"""
闲鱼账号管理技能文档
Xianyu Accounts Skill Documentation
"""

name = "xianyu-accounts"
description = "Manage multiple Xianyu accounts, scheduled tasks, and system monitoring"
usage = |
  User: "列出所有账号"
  User: "查看账号健康度"
  User: "创建定时擦亮任务"
  User: "查看告警"
  User: "运行健康检查"
---

# Xianyu Accounts Skill

多账号管理和系统监控技能。

## 功能

### 账号管理
- 列出所有账号
- 查看账号状态和健康度
- 切换当前账号
- 获取统一仪表盘

### 定时任务
- 创建定时擦亮任务
- 创建数据采集任务
- 立即运行任务
- 删除任务

### 系统监控
- 查看活跃告警
- 解除告警
- 运行健康检查

## 使用示例

### 列出账号
```
User: 列出所有账号
Action: list
```

### 查看健康度
```
User: 查看账号健康度
Action: health
```

### 创建定时任务
```
User: 每天上午9点擦亮商品
Action: create_task, task_type="polish", cron_expression="0 9 * * *"
```

### 查看告警
```
User: 有哪些告警
Action: alerts
```

### 运行健康检查
```
User: 运行健康检查
Action: health_check
```
