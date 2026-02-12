# 🦞 闲鱼自动化工具 (Xianyu OpenClaw)

基于 [OpenClaw](https://github.com/openclaw/openclaw) 框架的闲鱼自动化运营工具。支持商品发布、智能做图、文案生成、一键擦亮、数据记录、多账号管理等全流程自动化功能。

## 📋 目录

- [项目概述](#项目概述)
- [功能特性](#功能特性)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [核心模块](#核心模块)
- [使用示例](#使用示例)
- [技能系统](#技能系统)
- [定时任务](#定时任务)
- [监控告警](#监控告警)
- [数据分析](#数据分析)
- [多账号管理](#多账号管理)
- [开发阶段总结](#开发阶段总结)
- [注意事项](#注意事项)
- [常见问题](#常见问题)
- [更新日志](#更新日志)
- [贡献指南](#贡献指南)
- [License](#license)

---

## 项目概述

闲鱼作为国内最大的二手交易平台，拥有庞大的用户群体。对于个人卖家和小型商家而言，闲鱼店铺的日常运营涉及大量重复性工作，包括商品上架、内容编辑、价格调整、信息擦亮等。这些工作耗时耗力且容易遗漏，严重制约了店铺的运营效率。

本项目基于OpenClaw框架，通过AI技术和浏览器自动化手段，实现闲鱼店铺运营的全面智能化。OpenClaw作为一款强大的个人AI助手框架，提供了完善的工具系统、技能体系和浏览器控制能力，为本项目的实施奠定了坚实的技术基础。

### 项目目标

1. **商品发布自动化** - AI生成标题描述，自动处理图片，一键发布商品
2. **店铺运营自动化** - 定时擦亮、自动调价、批量管理
3. **数据分析智能化** - 追踪关键指标，生成运营报表
4. **多账号统一管理** - 支持多个闲鱼账号切换和统一监控

---

## 功能特性

### 🛒 商品发布

- **AI文案生成** - 基于大语言模型自动生成吸引人的标题和描述
- **智能做图** - 自动调整图片尺寸、添加水印、批量处理
- **批量发布** - 支持多个商品顺序发布，模拟人工操作节奏
- **多图上传** - 支持批量上传多张图片，自动排序

### 📊 店铺运营

- **一键擦亮** - 自动刷新商品，提高搜索排名
- **价格调整** - 批量修改价格，支持固定金额和折扣模式
- **商品下架** - 批量下架商品，支持设置下架原因
- **重新上架** - 快速重新上架已下架商品

### 📈 数据分析

- **运营仪表盘** - 实时展示关键运营指标
- **趋势分析** - 追踪浏览量、想要数变化趋势
- **多维报表** - 支持日报、周报、月报生成
- **数据导出** - 支持CSV、JSON格式导出

### 👥 多账号管理

- **统一管理** - 支持多个闲鱼账号集中管理
- **健康监控** - 追踪各账号运营健康度
- **自动切换** - 按优先级自动轮询切换账号
- **任务分配** - 自动分配发布任务到多个账号

### ⏰ 定时任务

- **定时擦亮** - 每天自动擦亮商品
- **数据采集** - 定时采集商品指标数据
- **健康检查** - 定时检查系统运行状态

### 🚨 监控告警

- **异常监控** - 监控浏览器连接、发布失败等异常
- **自动恢复** - 支持自动尝试恢复
- **多级告警** - Info、Warning、Error、Critical四级告警
- **告警通知** - 支持日志和文件记录

---

## 项目结构

```
xianyu-openclaw/
├── src/                          # 源代码
│   ├── core/                     # 核心模块
│   │   ├── config.py            # 配置管理
│   │   ├── logger.py            # 日志系统
│   │   └── openclaw_controller.py  # OpenClaw浏览器控制
│   ├── modules/                 # 功能模块
│   │   ├── listing/            # 商品发布模块
│   │   │   ├── __init__.py
│   │   │   ├── models.py       # 数据模型
│   │   │   └── service.py      # 发布服务
│   │   ├── media/             # 媒体处理模块
│   │   │   ├── __init__.py
│   │   │   └── service.py     # 图片处理服务
│   │   ├── content/            # 内容生成模块
│   │   │   ├── __init__.py
│   │   │   └── service.py     # AI文案生成服务
│   │   ├── operations/         # 运营操作模块
│   │   │   ├── __init__.py
│   │   │   └── service.py     # 擦亮、调价等服务
│   │   ├── analytics/          # 数据分析模块
│   │   │   ├── __init__.py
│   │   │   ├── service.py     # 数据存储查询
│   │   │   ├── report_generator.py  # 报表生成
│   │   │   └── visualization.py    # 数据可视化
│   │   └── accounts/           # 账号管理模块
│   │       ├── __init__.py
│   │       ├── service.py      # 账号管理服务
│   │       ├── scheduler.py    # 定时任务调度
│   │       └── monitor.py      # 监控告警
│   └── main.py                # 程序入口
├── skills/                     # OpenClaw技能
│   ├── __init__.py           # 技能包入口
│   ├── registry.py           # 技能注册中心
│   ├── openclaw_integration.py  # OpenClaw集成示例
│   ├── xianyu-publish/       # 发布技能
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── SKILL.md
│   ├── xianyu-manage/         # 管理技能
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── SKILL.md
│   ├── xianyu-content/        # 内容生成技能
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── SKILL.md
│   ├── xianyu-metrics/        # 数据统计技能
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── SKILL.md
│   └── xianyu-accounts/       # 账号管理技能
│       ├── __init__.py
│       ├── skill.py
│       └── SKILL.md
├── examples/                   # 示例脚本
│   ├── __init__.py
│   ├── demo.py               # 基本功能演示
│   ├── demo_browser.py       # 浏览器自动化演示
│   ├── demo_analytics.py     # 数据分析演示
│   └── demo_advanced.py     # 高级功能演示
├── tests/                     # 测试文件
│   ├── __init__.py
│   ├── test_modules.py       # 模块测试
│   └── test_skills.py        # 技能测试
├── config/                    # 配置文件
│   ├── config.example.yaml   # 配置模板
│   ├── config.yaml           # 实际配置
│   ├── .env.example         # 环境变量模板
│   └── .env                 # 实际环境变量
├── data/                     # 数据目录
│   ├── processed_images/    # 处理后的图片
│   ├── agent.db             # SQLite数据库
│   ├── account_stats.json   # 账号统计
│   ├── scheduler_tasks.json  # 定时任务配置
│   └── alerts.json          # 告警记录
├── logs/                     # 日志目录
├── docs/                     # 文档目录
│   └── PROJECT_PLAN.md       # 项目计划书
├── requirements.txt          # Python依赖
├── README.md                # 本文档
└── .gitignore              # Git忽略配置
```

---

## 快速开始

### 环境要求

- **Python**: 3.10+
- **操作系统**: macOS / Linux / Windows (WSL2)
- **OpenClaw**: 用于浏览器自动化
- **依赖包**: 详见 requirements.txt

### 1. 安装Python依赖

```bash
# 克隆项目
git clone https://github.com/yourusername/xianyu-openclaw.git
cd xianyu-openclaw

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 安装Playwright浏览器（如果需要）
playwright install chromium
```

### 2. 配置项目

```bash
# 复制配置模板
cp config/config.example.yaml config/config.yaml
cp .env.example .env

# 编辑配置文件
vim config/config.yaml
vim .env
```

### 3. 配置说明

#### config.yaml 主要配置项

```yaml
# 应用配置
app:
  name: "xianyu-openclaw"
  version: "1.0.0"
  debug: false
  log_level: "INFO"

# OpenClaw连接配置
openclaw:
  host: "localhost"
  port: 9222
  timeout: 30

# AI服务配置
ai:
  provider: "deepseek"  # 或 "openai"
  api_key: "${DEEPSEEK_API_KEY}"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"

# 多账号配置
accounts:
  - id: "account_1"
    name: "主账号"
    cookie: "${XIANYU_COOKIE_1}"
    priority: 1
    enabled: true

# 定时任务配置
scheduler:
  enabled: true
  polish:
    enabled: true
    cron: "0 9 * * *"

# 媒体处理配置
media:
  max_width: 1500
  max_height: 1500
  output_quality: 85
  watermark:
    enabled: false
    text: "闲鱼助手"
```

#### .env 环境变量

```bash
# AI服务
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx

# 闲鱼账号Cookie（从浏览器DevTools获取）
XIANYU_COOKIE_1=your_cookie_here
XIANYU_COOKIE_2=your_second_cookie_here

# OpenClaw
OPENCLAW_HOST=localhost
OPENCLAW_PORT=9222
```

### 4. 获取闲鱼Cookie

1. 使用浏览器登录闲鱼
2. 打开开发者工具（F12）
3. 切换到Network标签
4. 刷新页面，找到任意请求
5. 在Request Headers中复制Cookie值
6. 将Cookie填入配置文件

### 5. 启动OpenClaw

```bash
# 启动OpenClaw网关
openclaw gateway --port 9222

# 或者使用默认端口
openclaw gateway
```

### 6. 运行演示

```bash
# 基本功能演示
python examples/demo.py

# 浏览器自动化演示
python examples/demo_browser.py

# 数据分析演示
python examples/demo_analytics.py

# 高级功能演示
python examples/demo_advanced.py

# 运行测试
python tests/test_modules.py
python tests/test_skills.py
```

---

## 配置说明

### 配置文件详解

#### 应用配置 (app)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 应用名称 | xianyu-openclaw |
| version | 版本号 | 1.0.0 |
| debug | 调试模式 | false |
| log_level | 日志级别 | INFO |
| data_dir | 数据目录 | data |
| logs_dir | 日志目录 | logs |

#### OpenClaw配置 (openclaw)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| host | OpenClaw服务地址 | localhost |
| port | OpenClaw服务端口 | 9222 |
| timeout | 请求超时时间 | 30秒 |
| retry_times | 重试次数 | 3 |

#### AI服务配置 (ai)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| provider | AI服务提供商 | deepseek |
| api_key | API密钥 | - |
| base_url | API地址 | - |
| model | 模型名称 | deepseek-chat |
| temperature | 温度参数 | 0.7 |
| max_tokens | 最大token数 | 1000 |

#### 媒体处理配置 (media)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| max_width | 最大宽度 | 1500 |
| max_height | 最大高度 | 1500 |
| output_quality | 输出质量 | 85 |
| watermark.enabled | 启用水印 | false |
| watermark.text | 水印文字 | 闲鱼助手 |
| watermark.position | 水印位置 | bottom-right |

---

## 核心模块

### 1. 商品发布模块 (listing)

```python
from src.modules.listing.service import ListingService
from src.modules.listing.models import Listing

# 初始化服务
listing_service = ListingService()

# 创建商品
listing = Listing(
    title="iPhone 15 Pro Max 256GB",
    description="出闲置，95新，配件齐全",
    price=6999.0,
    original_price=8999.0,
    category="数码手机",
    images=["path/to/img1.jpg", "path/to/img2.jpg"],
    tags=["苹果", "iPhone", "95新"]
)

# 发布商品
result = await listing_service.create_listing(listing)

if result.success:
    print(f"发布成功: {result.product_url}")
else:
    print(f"发布失败: {result.error_message}")

# 批量发布
results = await listing_service.batch_create_listings(
    [listing1, listing2, listing3],
    delay_range=(5, 10)  # 发布间隔5-10秒
)
```

### 2. 媒体处理模块 (media)

```python
from src.modules.media.service import MediaService

# 初始化服务
media_service = MediaService()

# 批量处理图片
processed = media_service.batch_process_images(
    ["img1.jpg", "img2.jpg", "img3.jpg"],
    output_dir="data/processed_images",
    add_watermark=True
)

# 验证图片
is_valid, message = media_service.validate_image("image.jpg")
if not is_valid:
    print(f"图片无效: {message}")

# 压缩图片
media_service.compress_image("input.jpg", "output.jpg", quality=80)
```

### 3. 内容生成模块 (content)

```python
from src.modules.content.service import ContentService

# 初始化服务
content_service = ContentService()

# 生成标题
title = content_service.generate_title(
    product_name="MacBook Pro",
    features=["M3芯片", "16GB内存", "512GB SSD"],
    category="电脑办公"
)
print(f"生成的标题: {title}")

# 生成描述
description = content_service.generate_description(
    product_name="iPhone 15",
    condition="95新",
    reason="换新手机",
    tags=["苹果", "5G"]
)
print(f"生成的描述:\n{description}")

# 生成关键词
keywords = content_service.generate_seo_keywords("iPhone 15", "数码手机")
print(f"关键词: {keywords}")

# 生成完整内容
content = content_service.generate_listing_content({
    "name": "iPhone 15 Pro",
    "features": ["256GB", "原色钛金属"],
    "category": "数码手机",
    "condition": "99新",
    "reason": "用不上"
})
```

### 4. 运营操作模块 (operations)

```python
from src.modules.operations.service import OperationsService

# 初始化服务
operations_service = OperationsService()

# 擦亮单个商品
result = await operations_service.polish_listing("item_123456")
print(f"擦亮结果: {'成功' if result['success'] else '失败'}")

# 批量擦亮
result = await operations_service.batch_polish(
    max_items=50  # 最多擦亮50个商品
)
print(f"擦亮数量: {result['success']}/{result['total']}")

# 更新价格
result = await operations_service.update_price(
    product_id="item_123456",
    new_price=5499.0,
    original_price=5999.0
)

# 批量更新价格
updates = [
    {"product_id": "item_1", "new_price": 100, "original_price": 120},
    {"product_id": "item_2", "new_price": 200, "original_price": 250},
]
results = await operations_service.batch_update_price(updates)

# 下架商品
result = await operations_service.delist(
    product_id="item_123456",
    reason="不卖了"
)

# 重新上架
result = await operations_service.relist("item_123456")
```

### 5. 数据分析模块 (analytics)

```python
from src.modules.analytics.service import AnalyticsService
from src.modules.analytics.report_generator import ReportGenerator
from src.modules.analytics.visualization import DataVisualizer

# 初始化服务
analytics = AnalyticsService()

# 获取仪表盘数据
stats = await analytics.get_dashboard_stats()
print(f"总操作数: {stats['total_operations']}")
print(f"在售商品: {stats['active_products']}")
print(f"总营收: {stats['total_revenue']}")

# 获取日报
daily_report = await analytics.get_daily_report()
print(f"发布数: {daily_report['new_listings']}")
print(f"浏览量: {daily_report['total_views']}")

# 生成周报
weekly_report = await ReportGenerator().generate_weekly_report()
print(f"周报摘要: {weekly_report['summary']}")

# 生成月报
monthly_report = await ReportGenerator().generate_monthly_report(
    year=2024,
    month=1
)
print(f"月营收: {monthly_report['summary']['total_revenue']}")

# 获取趋势数据
trends = await analytics.get_trend_data("views", days=30)
print(f"趋势数据点数: {len(trends)}")

# 导出数据
filepath = await analytics.export_data(
    data_type="products",
    format="csv"
)
print(f"导出路径: {filepath}")

# 清理旧数据
result = await analytics.cleanup_old_data(days=90)
print(f"删除日志: {result['logs_deleted']}")
```

### 6. 账号管理模块 (accounts)

```python
from src.modules.accounts.service import AccountsService
from src.modules.accounts.scheduler import Scheduler
from src.modules.accounts.monitor import Monitor, HealthChecker

# 账号管理
accounts_service = AccountsService()

# 获取所有账号
accounts = accounts_service.get_accounts()
for acc in accounts:
    print(f"{acc['name']}: {acc['status']}")

# 获取当前账号
current = accounts_service.get_current_account()
print(f"当前账号: {current['name']}")

# 获取账号健康度
health = accounts_service.get_account_health("account_1")
print(f"健康分数: {health['health_score']}%")

# 验证Cookie
is_valid = accounts_service.validate_cookie("account_1")
print(f"Cookie有效: {is_valid}")

# 统一仪表盘
dashboard = accounts_service.get_unified_dashboard()
print(f"总账号数: {dashboard['total_accounts']}")

# 分配发布任务
distribution = accounts_service.distribute_publish(count=10)
for d in distribution:
    print(f"{d['account']['name']}: {d['count']}个任务")

# 定时任务调度
scheduler = Scheduler()

# 创建定时擦亮任务
task = scheduler.create_polish_task(
    cron_expression="0 9 * * *",  # 每天上午9点
    max_items=50
)

# 立即运行任务
result = await scheduler.run_task_now(task.task_id)

# 获取调度器状态
status = scheduler.get_scheduler_status()
print(f"总任务数: {status['total_tasks']}")

# 监控告警
monitor = Monitor()

# 触发告警
alert = monitor.raise_alert(
    alert_type="browser_connection",
    title="浏览器连接失败",
    message="无法连接到OpenClaw",
    auto_resolve=True
)

# 获取活跃告警
alerts = monitor.get_active_alerts()
for alert in alerts:
    print(f"[{alert.level}] {alert.title}")

# 运行健康检查
checker = HealthChecker()
result = await checker.run_health_check()
print(f"浏览器状态: {result['checks']['browser']['status']}")
```

---

## 使用示例

### 示例1：发布一个商品

```python
import asyncio
from src.modules.listing.service import ListingService
from src.modules.listing.models import Listing
from src.modules.media.service import MediaService
from src.modules.content.service import ContentService

async def publish_product():
    # 初始化服务
    listing_service = ListingService()
    media_service = MediaService()
    content_service = ContentService()

    # 准备商品信息
    product_info = {
        "name": "iPhone 15 Pro",
        "category": "数码手机",
        "features": ["256GB", "原色钛金属", "国行"],
        "condition": "99新",
        "reason": "换新手机",
        "price": 6999.0
    }

    # 生成标题和描述
    title = content_service.generate_title(
        product_name=product_info["name"],
        features=product_info["features"],
        category=product_info["category"]
    )
    description = content_service.generate_description(
        product_name=product_info["name"],
        condition=product_info["condition"],
        reason=product_info["reason"],
        tags=product_info["features"]
    )

    # 处理图片
    processed_images = media_service.batch_process_images(
        ["raw/iphone1.jpg", "raw/iphone2.jpg"],
        add_watermark=True
    )

    # 创建商品
    listing = Listing(
        title=title,
        description=description,
        price=product_info["price"],
        category=product_info["category"],
        images=processed_images,
        tags=product_info["features"]
    )

    # 发布
    result = await listing_service.create_listing(listing)

    if result.success:
        print(f"✅ 发布成功!")
        print(f"   链接: {result.product_url}")
    else:
        print(f"❌ 发布失败: {result.error_message}")

asyncio.run(publish_product())
```

### 示例2：批量擦亮所有商品

```python
import asyncio
from src.modules.operations.service import OperationsService

async def batch_polish():
    operations_service = OperationsService()

    print("🚀 开始批量擦亮...")
    result = await operations_service.batch_polish(max_items=100)

    print(f"\n📊 擦亮完成:")
    print(f"   成功: {result['success']}个")
    print(f"   失败: {result['failed']}个")
    print(f"   总计: {result['total']}个")

asyncio.run(batch_polish())
```

### 示例3：生成周报

```python
import asyncio
from src.modules.analytics.report_generator import ReportGenerator
from src.modules.analytics.visualization import DataVisualizer

async def generate_weekly_report():
    generator = ReportGenerator()
    visualizer = DataVisualizer()

    # 生成周报
    report = await generator.generate_weekly_report()

    print("="*50)
    print("📊 周运营报告")
    print("="*50)
    print(f"周期: {report['period']['start']} ~ {report['period']['end']}")
    print(f"发布商品: {report['summary']['new_listings']}个")
    print(f"擦亮次数: {report['summary']['polished_count']}次")
    print(f"总浏览量: {report['summary']['total_views']}")
    print(f"总想要数: {report['summary']['total_wants']}")
    print("="*50)

asyncio.run(generate_weekly_report())
```

### 示例4：多账号统一管理

```python
import asyncio
from src.modules.accounts.service import AccountsService
from src.modules.accounts.scheduler import Scheduler

async def multi_account_management():
    accounts_service = AccountsService()
    scheduler = Scheduler()

    # 查看所有账号状态
    print("📋 账号列表:")
    for acc in accounts_service.get_accounts():
        health = accounts_service.get_account_health(acc["id"])
        status = "✅" if health["health_score"] >= 80 else "⚠️" if health["health_score"] >= 50 else "❌"
        print(f"  {status} {acc['name']}: {health['health_score']}%")

    # 创建定时任务
    print("\n⏰ 创建定时擦亮任务...")
    polish_task = scheduler.create_polish_task(
        cron_expression="0 9 * * *",
        max_items=30
    )
    print(f"  ✅ 创建成功: {polish_task.name}")

    # 分配发布任务
    print("\n📦 分配10个发布任务...")
    distribution = accounts_service.distribute_publish(count=10)
    for d in distribution:
        print(f"  → {d['account']['name']}: {d['count']}个")

asyncio.run(multi_account_management())
```

---

## 技能系统

### 可用技能

| 技能名称 | 功能描述 |
|---------|---------|
| xianyu-publish | 发布商品到闲鱼 |
| xianyu-manage | 管理店铺商品（擦亮、下架、调价） |
| xianyu-content | 生成标题、描述、关键词 |
| xianyu-metrics | 查询运营数据、生成报表 |
| xianyu-accounts | 多账号管理、定时任务、监控 |

### 使用技能

```python
from skills import load_skill

# 加载发布技能
skill = load_skill("xianyu-publish")

# 执行发布
result = await skill.execute("publish", {
    "product_name": "iPhone 15",
    "price": 5000,
    "condition": "95新"
})
print(f"发布结果: {result}")

# 加载管理技能
skill = load_skill("xianyu-manage")

# 执行擦亮
result = await skill.execute("polish", {
    "product_id": "item_123456"
})

# 加载内容生成技能
skill = load_skill("xianyu-content")

# 生成标题
result = await skill.execute("generate_title", {
    "product_name": "MacBook Pro",
    "features": ["M3", "16GB"]
})

# 加载数据统计技能
skill = load_skill("xianyu-metrics")

# 获取仪表盘
result = await skill.execute("dashboard", {})

# 加载账号管理技能
skill = load_skill("xianyu-accounts")

# 列出账号
result = await skill.execute("list", {})
```

### 技能注册

```python
from skills import SkillsRegistry, list_skills, get_skill

# 列出所有技能
skills = list_skills()
print(f"可用技能: {skills}")

# 获取技能描述
skill_info = get_skill("xianyu-publish")
print(f"技能名称: {skill_info.name}")
print(f"技能描述: {skill_info.description}")
```

---

## 定时任务

### 创建定时任务

```python
from src.modules.accounts.scheduler import Scheduler

scheduler = Scheduler()

# 创建定时擦亮任务
polish_task = scheduler.create_polish_task(
    cron_expression="0 9 * * *",  # 每天上午9点
    max_items=50
)

# 创建数据采集任务
metrics_task = scheduler.create_metrics_task(
    cron_expression="0 */4 * * *",  # 每4小时
    metrics_types=["views", "wants"]
)

# 自定义任务
custom_task = scheduler.create_task(
    task_type="custom",
    name="我的任务",
    cron_expression="0 10 * * 1",  # 每周一上午10点
    params={"action": "my_action"}
)
```

### 管理任务

```python
# 列出所有任务
tasks = scheduler.list_tasks()
for task in tasks:
    print(f"{task.name}: {task.cron_expression}")

# 立即运行任务
result = await scheduler.run_task_now(task_id)

# 更新任务
scheduler.update_task(task_id, enabled=False)

# 删除任务
scheduler.delete_task(task_id)

# 获取调度器状态
status = scheduler.get_scheduler_status()
```

### Cron表达式说明

| 表达式 | 说明 |
|--------|------|
| `* * * * *` | 每分钟 |
| `0 * * * *` | 每小时 |
| `0 9 * * *` | 每天上午9点 |
| `0 9 * * 1` | 每周一上午9点 |
| `0 9 1 * *` | 每月1号上午9点 |
| `0 */4 * * *` | 每4小时 |

---

## 监控告警

### 告警类型

| 类型 | 说明 | 默认阈值 |
|------|------|---------|
| browser_connection | 浏览器连接失败 | 3次/10分钟 |
| publish_failure | 发布操作失败 | 5次/60分钟 |
| account_locked | 账号被锁定 | 1次/0分钟 |
| rate_limit | 触发限流 | 10次/5分钟 |

### 使用监控

```python
from src.modules.accounts.monitor import Monitor, HealthChecker

monitor = Monitor()

# 手动触发告警
alert = monitor.raise_alert(
    alert_type="browser_connection",
    title="浏览器连接失败",
    message="无法连接到OpenClaw服务",
    source="manual",
    auto_resolve=True  # 5分钟后自动解除
)

# 获取告警
alerts = monitor.get_active_alerts()
for alert in alerts:
    print(f"[{alert.level}] {alert.title}")

# 解除告警
monitor.resolve_alert(alert_id)

# 获取告警摘要
summary = monitor.get_alert_summary()
print(f"活跃告警: {summary['active_alerts']}")

# 运行健康检查
checker = HealthChecker()
result = await checker.run_health_check()
```

### 注册回调

```python
async def alert_callback(alert):
    print(f"收到告警: {alert.title}")
    # 发送通知、记录日志等

monitor.register_callback(alert_callback)
```

---

## 数据分析

### 报表类型

| 报表类型 | 说明 | 数据范围 |
|---------|------|---------|
| 日报 | 每日运营汇总 | 当天数据 |
| 周报 | 周度运营分析 | 7天数据 |
| 月报 | 月度运营分析 | 30天数据 |
| 商品报告 | 单品表现分析 | 指定商品 |
| 对比报告 | 多商品对比 | 指定商品 |

### 生成报表

```python
from src.modules.analytics.report_generator import ReportGenerator, ReportFormatter

generator = ReportGenerator()

# 生成日报
daily = await generator.generate_daily_report()

# 生成周报
weekly = await generator.generate_weekly_report()

# 生成月报
monthly = await generator.generate_monthly_report(
    year=2024,
    month=1
)

# 生成商品报告
product_report = await generator.generate_product_report(
    product_id="item_123456",
    days=30
)

# 生成对比报告
comparison = await generator.generate_comparison_report(
    products=["item_1", "item_2", "item_3"]
)

# 格式化输出
markdown = ReportFormatter.to_markdown(daily)
slack = ReportFormatter.to_slack(daily)
```

### 数据可视化

```python
from src.modules.analytics.visualization import DataVisualizer, ChartExporter

visualizer = DataVisualizer()

# 生成柱状图
chart = visualizer.generate_bar_chart(
    data=[
        {"label": "商品A", "value": 100},
        {"label": "商品B", "value": 80},
        {"label": "商品C", "value": 60},
    ],
    label_key="label",
    value_key="value",
    title="商品浏览量"
)

# 生成折线图
trend_chart = visualizer.generate_line_chart(
    data=trend_data,
    label_key="date",
    value_key="views",
    title="浏览量趋势"
)

# 导出报表
exporter = ChartExporter()
filepath = await exporter.export_report(
    report=daily,
    format="markdown"
)
```

---

## 多账号管理

### 添加账号

```python
from src.modules.accounts.service import AccountsService

accounts_service = AccountsService()

# 添加新账号
accounts_service.add_account(
    account_id="account_2",
    name="副账号",
    cookie="your_cookie_here",
    priority=2
)

# 启用/禁用账号
accounts_service.enable_account("account_2")
accounts_service.disable_account("account_2")

# 刷新Cookie
accounts_service.refresh_cookie(
    account_id="account_1",
    new_cookie="new_cookie_here"
)
```

### 账号切换

```python
# 切换当前账号
accounts_service.set_current_account("account_1")

# 获取下一个账号（轮询）
next_account = accounts_service.get_next_account()

# 获取Cookie
cookie = accounts_service.get_cookie("account_1")
```

### 健康监控

```python
# 获取单个账号健康度
health = accounts_service.get_account_health("account_1")
print(f"健康分数: {health['health_score']}%")
print(f"发布数: {health['total_published']}")
print(f"错误数: {health['total_errors']}")

# 获取所有账号健康度
all_health = accounts_service.get_all_accounts_health()

# 验证Cookie有效性
is_valid = accounts_service.validate_cookie("account_1")
```

---

## 开发阶段总结

本项目历经6个阶段完成开发，以下是各阶段的核心产出：

### 第一阶段：基础架构搭建 ✅

**时间**: 第1-2周

**核心产出**:
- 项目目录结构建立
- Python依赖环境配置 (requirements.txt)
- YAML配置文件体系 (config/config.yaml)
- 环境变量配置 (.env)
- 核心配置管理模块 (src/core/config.py)
- 统一日志系统 (src/core/logger.py)
- 浏览器控制器框架 (src/core/openclaw_controller.py)

**关键代码量**: ~800行

### 第二阶段：浏览器自动化集成 ✅

**时间**: 第3-5周

**核心产出**:
- 增强版OpenClaw浏览器控制器
  - 元素定位与操作 (click, type_text, find_element等)
  - 文件上传功能 (upload_file, upload_files)
  - 页面导航与等待 (navigate, wait_for_selector)
  - 随机延迟模拟人类行为
- 商品发布自动化服务 (src/modules/listing/service.py)
  - 完整发布流程：导航→上传→填写→提交
  - 批量发布支持
- 运营操作自动化服务 (src/modules/operations/service.py)
  - 擦亮、调价、下架等功能

**关键代码量**: ~2000行

### 第三阶段：技能层封装 ✅

**时间**: 第6-7周

**核心产出**:
- 4个OpenClaw技能
  - xianyu-publish: 商品发布技能
  - xianyu-manage: 店铺管理技能
  - xianyu-content: 内容生成技能
  - xianyu-metrics: 数据统计技能
- 技能注册机制 (skills/registry.py)
- 技能文档 (SKILL.md)
- OpenClaw集成示例 (skills/openclaw_integration.py)

**关键代码量**: ~1500行

### 第四阶段：数据分析与报表 ✅

**时间**: 第8-9周

**核心产出**:
- 增强版AnalyticsService (src/modules/analytics/service.py)
  - 操作日志记录
  - 商品指标追踪
  - 数据查询接口
- 报表生成器 (src/modules/analytics/report_generator.py)
  - 日报、周报、月报
  - 商品表现报告
  - 多商品对比报告
- 数据可视化 (src/modules/analytics/visualization.py)
  - ASCII图表生成
  - CSV/JSON导出
  - Markdown报表格式化

**关键代码量**: ~1500行

### 第五阶段：多账号管理与高级功能 ✅

**时间**: 第10-12周

**核心产出**:
- 增强版AccountsService (src/modules/accounts/service.py)
  - 多账号配置管理
  - 账号健康度追踪
  - Cookie验证
  - 统一仪表盘
  - 任务分配
- 定时任务调度器 (src/modules/accounts/scheduler.py)
  - Cron表达式支持
  - 定时擦亮
  - 定时数据采集
  - 任务执行历史
- 监控告警系统 (src/modules/accounts/monitor.py)
  - 多级告警 (Info/Warning/Error/Critical)
  - 自动恢复机制
  - 健康检查
  - 告警回调支持
- xianyu-accounts技能

**关键代码量**: ~2000行

### 第六阶段：测试与文档 ✅

**时间**: 第13-15周

**核心产出**:
- 单元测试 (tests/test_modules.py, tests/test_skills.py)
- 功能演示脚本
  - examples/demo.py
  - examples/demo_browser.py
  - examples/demo_analytics.py
  - examples/demo_advanced.py
- 完整项目文档 (PROJECT_PLAN.md)

**关键代码量**: ~1000行

---

## 项目统计

| 指标 | 数量 |
|------|------|
| 总开发阶段 | 6个 |
| 核心模块 | 6个 |
| 服务类 | 12个 |
| 技能 | 5个 |
| 配置文件 | 5个 |
| 示例脚本 | 4个 |
| 测试文件 | 2个 |
| 文档 | 3份 |
| 预估代码行数 | ~10000行 |

---

## 注意事项

### 合规使用

1. **遵守平台规则** - 请合理使用自动化功能，遵守闲鱼平台规则
2. **Cookie安全** - 定期更新Cookie以保持登录状态
3. **测试验证** - 建议使用测试账号先进行功能验证
4. **隐私保护** - 注意保护个人隐私信息，不要泄露Cookie

### 安全建议

1. **本地运行** - 建议在本地环境运行，不要部署到公网服务器
2. **权限控制** - 限制配置文件访问权限
3. **日志管理** - 定期清理日志文件
4. **监控告警** - 开启监控告警，及时发现异常

### 性能优化

1. **延迟设置** - 合理设置操作延迟，避免触发限流
2. **批量处理** - 使用批量操作提高效率
3. **资源清理** - 定期清理旧数据和日志
4. **健康检查** - 定期运行健康检查

---

## 常见问题

### Q1: 无法连接OpenClaw

```bash
# 检查OpenClaw是否运行
openclaw status

# 启动OpenClaw
openclaw gateway --port 9222

# 检查端口
lsof -i :9222
```

### Q2: Cookie过期

```bash
# 重新获取Cookie
# 1. 登录闲鱼
# 2. 打开开发者工具
# 3. 复制新的Cookie
# 4. 更新配置文件
```

### Q3: 发布失败

1. 检查Cookie是否有效
2. 检查商品信息是否完整
3. 检查图片是否合规
4. 查看日志获取详细错误

### Q4: 限流警告

```python
# 降低操作频率
from src.modules.operations.service import OperationsService

# 增加操作间隔
operations_service.delay_range = (5, 10)  # 5-10秒
```

### Q5: 数据导出失败

```python
# 检查数据目录权限
ls -la data/

# 确保目录存在
mkdir -p data/export
```

---

## 更新日志

### v1.1.0 (2024-02-12) 🚀 全面代码质量与架构优化

**阶段1：紧急修复（P0优先级）**
- ✅ 修复asyncio依赖错误（Python标准库不应作为外部依赖）
- ✅ 修复19处裸except语句（吞噬KeyboardInterrupt和SystemExit等）
- ✅ 修复2处asyncio.run()误用（会导致运行时错误）
- ✅ 实现敏感信息脱敏（Cookie等敏感数据保护）

**阶段2：短期改进（P1优先级）**
- ✅ 配置验证与Schema定义（Pydantic配置模型）
- ✅ 修复并发安全问题（添加asyncio.Lock保护共享资源）
- ✅ SQL注入防护（指标白名单验证）
- ✅ 添加AI调用超时控制（防止无限期挂起）

**阶段3：中期优化（P2优先级）**
- ✅ 依赖版本管理（版本锁定、依赖指南）
- ✅ 引入抽象接口层（9个核心服务接口）
- ✅ 改进单例模式（线程安全的Double-checked locking）
- ✅ 统一错误处理（7个装饰器、扩展异常类）

**阶段4：长期改进（P3优先级）**
- ✅ 完善测试覆盖（1200+行测试代码）
- ✅ 性能优化（异步缓存、批量处理、数据库索引优化）
- ✅ 代码质量工具（Black、isort、Ruff、Mypy、pytest-cov）
- ✅ 文档完善（依赖指南、优化总结报告）

**新增核心模块**：
- `src/core/config_models.py` - 配置模型与验证
- `src/core/error_handler.py` - 统一异常处理（扩展）
- `src/core/service_container.py` - 依赖注入容器
- `src/core/performance.py` - 性能优化工具
- `src/modules/interfaces.py` - 服务接口抽象层

**新增测试文件**：
- `pytest.ini` - pytest配置
- `tests/conftest.py` - 测试fixtures
- `tests/test_config.py` - 配置测试
- `tests/test_interfaces.py` - 接口测试
- `tests/test_error_handler.py` - 异常处理测试
- `tests/test_integration.py` - 集成测试

**新增配置和脚本**：
- `requirements.lock` - 依赖锁定文件
- `DEPENDENCIES.md` - 依赖管理指南
- `pyproject.toml` - 项目统一配置
- `scripts/check_code_quality.sh` - 代码质量检查脚本
- `scripts/format_code.sh` - 代码格式化脚本

**统计**：
- 新增文件：16个
- 修改文件：14个
- 新增代码：~2150行
- 修改代码：~215行
- 修复问题：23+
- 新增接口：9个
- 新增装饰器：7个
- 新增测试：1200+行

**详细改进报告**：详见 [IMPROVEMENTS.md](IMPROVEMENTS.md)

---

### v1.0.0 (2024-02-11)

- ✨ 初始版本发布
- 🛒 商品发布功能
- 📊 数据分析功能
- 👥 多账号管理功能
- ⏰ 定时任务功能
- 🚨 监控告警功能

---

## 贡献指南

### 贡献方式

1. **Bug报告** - 通过Issue报告Bug
2. **功能建议** - 通过Issue提出新功能
3. **代码贡献** - 提交Pull Request
4. **文档改进** - 完善文档和示例

### 开发规范

1. 代码风格遵循PEP 8
2. 提交前运行测试
3. 编写清晰的提交说明
4. 保持文档同步更新

---

## License

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 联系方式

- 项目地址: https://github.com/yourusername/xianyu-openclaw
- 问题反馈: https://github.com/yourusername/xianyu-openclaw/issues
- 功能建议: https://github.com/yourusername/xianyu-openclaw/discussions

---

**Happy Automating! 🦞**
