#!/usr/bin/env python3
"""
多账号管理与高级功能演示
Multi-Account and Advanced Features Demo

演示多账号管理、定时任务和监控告警功能
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def demo_accounts():
    """演示账号管理"""
    print("\n" + "="*60)
    print("演示1: 多账号管理")
    print("="*60)

    from src.modules.accounts.service import AccountsService

    service = AccountsService()

    print("\n📋 列出所有账号:")
    accounts = service.get_accounts()
    print(f"  账号数量: {len(accounts)}")
    for acc in accounts:
        print(f"    - {acc.get('name')}: {acc.get('id')} ({acc.get('status')})")

    print("\n🌡️ 账号健康度:")
    health_list = service.get_all_accounts_health()
    for health in health_list:
        score = health.get("health_score", 0)
        emoji = "✅" if score >= 80 else "⚠️" if score >= 50 else "❌"
        print(f"    {emoji} {health['account_id']}: {score}%")

    print("\n📊 统一仪表盘:")
    dashboard = service.get_unified_dashboard()
    print(f"  总账号数: {dashboard.get('total_accounts', 0)}")
    print(f"  活跃账号: {dashboard.get('active_accounts', 0)}")
    print(f"  总发布: {dashboard.get('total_products', 0)}")


async def demo_scheduler():
    """演示定时任务"""
    print("\n" + "="*60)
    print("演示2: 定时任务调度")
    print("="*60)

    from src.modules.accounts.scheduler import Scheduler

    scheduler = Scheduler()

    print("\n📅 创建定时擦亮任务...")
    polish_task = scheduler.create_polish_task(
        cron_expression="0 9 * * *",
        max_items=50
    )
    print(f"  ✅ 创建任务: {polish_task.name} ({polish_task.task_id})")
    print(f"     Cron: {polish_task.cron_expression}")

    print("\n📅 创建数据采集任务...")
    metrics_task = scheduler.create_metrics_task(
        cron_expression="0 */4 * * *",
        metrics_types=["views", "wants"]
    )
    print(f"  ✅ 创建任务: {metrics_task.name} ({metrics_task.task_id})")

    print("\n📋 任务列表:")
    tasks = scheduler.list_tasks()
    for task in tasks:
        status = "🟢" if task.enabled else "🔴"
        print(f"  {status} {task.name}: {task.task_type} ({task.cron_expression})")

    print("\n📊 调度器状态:")
    status = scheduler.get_scheduler_status()
    print(f"  总任务: {status.get('total_tasks', 0)}")
    print(f"  启用任务: {status.get('enabled_tasks', 0)}")


async def demo_monitor():
    """演示监控告警"""
    print("\n" + "="*60)
    print("演示3: 监控告警系统")
    print("="*60)

    from src.modules.accounts.monitor import Monitor, HealthChecker

    monitor = Monitor()

    print("\n🚨 触发测试告警...")
    alert = monitor.raise_alert(
        alert_type="browser_connection",
        title="浏览器连接测试",
        message="这是一条测试告警",
        source="demo",
        auto_resolve=True
    )
    print(f"  ✅ 告警已触发: {alert.alert_id}")

    print("\n📋 活跃告警:")
    alerts = monitor.get_active_alerts()
    print(f"  活跃告警数: {len(alerts)}")
    for a in alerts:
        level_emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}
        emoji = level_emoji.get(a.level, "📢")
        print(f"    {emoji} [{a.level}] {a.title}: {a.message}")

    print("\n📊 告警摘要:")
    summary = monitor.get_alert_summary()
    print(f"  总告警: {summary.get('total_alerts', 0)}")
    print(f"  活跃: {summary.get('active_alerts', 0)}")
    print(f"  已解除: {summary.get('resolved_alerts', 0)}")

    print("\n🏥 运行健康检查...")
    checker = HealthChecker()
    result = await checker.run_health_check()
    print(f"  浏览器: {result['checks']['browser']['status']}")
    print(f"  账号: {result['checks']['accounts']['status']}")


async def demo_distribution():
    """演示任务分配"""
    print("\n" + "="*60)
    print("演示4: 发布任务分配")
    print("="*60)

    from src.modules.accounts.service import AccountsService

    service = AccountsService()

    print("\n📦 分配10个发布任务到多个账号...")
    distribution = service.distribute_publish(count=10)

    print(f"  分配到 {len(distribution)} 个账号:")
    for d in distribution:
        acc = d["account"]
        print(f"    - {acc.get('name')}: {d['count']} 个发布任务")


async def demo_skill_usage():
    """演示技能使用"""
    print("\n" + "="*60)
    print("演示5: 技能调用示例")
    print("="*60)

    from skills.xianyu_accounts import XianyuAccountsSkill

    skill = XianyuAccountsSkill()
    skill.agent = MockAgent()

    print("\n📋 列出所有账号:")
    result = await skill.execute("list", {})
    print(f"  状态: {result.get('status')}")
    print(f"  账号数: {result.get('total', 0)}")

    print("\n📊 获取仪表盘:")
    result = await skill.execute("dashboard", {})
    print(f"  状态: {result.get('status')}")

    print("\n📅 创建定时任务:")
    result = await skill.execute("create_task", {
        "task_type": "polish",
        "cron_expression": "0 9 * * *",
        "max_items": 50
    })
    print(f"  状态: {result.get('status')}")
    print(f"  任务ID: {result.get('task_id', 'N/A')}")


class MockAgent:
    """模拟Agent"""

    def __init__(self):
        self.llm = MockLLM()


class MockLLM:
    """模拟LLM"""

    async def chat(self, prompt, model=None):
        return f"模拟响应: {prompt[:30]}..."


async def main():
    """主函数"""
    print("="*60)
    print("闲鱼自动化工具 - 多账号管理与高级功能演示")
    print("="*60)

    demos = [
        ("多账号管理", demo_accounts),
        ("定时任务", demo_scheduler),
        ("监控告警", demo_monitor),
        ("任务分配", demo_distribution),
        ("技能使用", demo_skill_usage),
    ]

    for name, demo_func in demos:
        try:
            await demo_func()
        except Exception as e:
            print(f"\n❌ {name} 演示失败: {e}")

    print("\n" + "="*60)
    print("演示完成！")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
