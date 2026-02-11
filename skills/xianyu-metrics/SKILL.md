---
name: xianyu-metrics
description: Query listing metrics and operational analytics
usage: |
  User: "查看今天的运营数据"
  User: "iPhone 15的浏览量"
  User: "生成昨天的日报"
---

# Xianyu Metrics Skill

Analytics and reporting for Xianyu marketplace operations.

## Capabilities

- **Dashboard**: View overall store metrics at a glance
- **Product Metrics**: Query specific listing performance
- **Operation Logs**: Review automation activity history
- **Daily Reports**: Generate operational summaries

## Usage Examples

### View Dashboard
```
User: 查看今天的运营数据
Action: dashboard
Result: Shows total products, views, wants, etc.
```

### Product Metrics
```
User: iPhone 15的浏览量
Action: product_metrics, product_id="xxx"
Result: Shows views, wants, inquiries for the product
```

### Daily Report
```
User: 生成昨天的日报
Action: daily_report, date="2024-01-15"
Result: Summary of yesterday's operations
```
