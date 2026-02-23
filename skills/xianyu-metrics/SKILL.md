---
name: xianyu_metrics
description: 查询闲鱼店铺运营数据、生成报表、导出数据
---

# 闲鱼数据分析

当用户想了解运营数据、查看报表、分析趋势时，使用此技能。

## 使用方法

使用 `bash` 工具执行以下命令：

### 查看运营仪表盘

```bash
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action dashboard
```

返回：在售商品数、总浏览量、总想要数、总营收等关键指标。

### 查看日报

```bash
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action daily
```

返回：今日新发布数、浏览量、想要数、成交数等。

### 查看趋势

```bash
# 查看最近 30 天的浏览量趋势
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action trend --metric views --days 30

# 查看最近 7 天的想要数趋势
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action trend --metric wants --days 7
```

可选指标（metric）：views（浏览量）、wants（想要数）、sales（成交数）、inquiries（咨询数）

### 导出数据

```bash
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action export --type products --format csv
```

## 示例

用户说："今天运营数据怎么样" →
```bash
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action dashboard
```

用户说："最近一周浏览量趋势" →
```bash
cd /home/node/.openclaw/workspace && python -m src.cli analytics --action trend --metric views --days 7
```

## 注意事项

- 所有命令输出 JSON 格式
- 向用户展示数据时，用表格或列表格式化，不要直接粘贴 JSON
- 如果数据量大，挑选关键指标展示并给出分析建议
