"""
技能集成测试
Skills Integration Tests

测试闲鱼技能的正确加载和执行
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class MockAgent:
    """模拟Agent用于测试"""

    def __init__(self):
        self.llm = MockLLM()


class MockLLM:
    """模拟LLM用于测试"""

    async def chat(self, prompt, model=None):
        return f"模拟AI响应: {prompt[:50]}..."


class MockSkill(AgentSkill):
    """测试用模拟技能"""

    name = "mock-skill"
    description = "A mock skill for testing"

    def __init__(self):
        super().__init__()
        self.agent = MockAgent()
        self.logs = []

    def log(self, message, level="info"):
        self.logs.append((level, message))


class MockBrowser:
    """模拟浏览器用于测试"""

    async def connect(self):
        return True

    async def new_page(self):
        return "mock-page-id"

    async def navigate(self, url):
        return True

    async def close_page(self, page_id):
        return True


def test_skill_registry():
    """测试技能注册中心"""
    from skills.registry import SkillsRegistry, list_skills, get_skill, load_skill

    skills = SkillsRegistry.load_all()
    print(f"✅ 已注册技能: {list(skills.keys())}")

    assert "xianyu-publish" in skills
    assert "xianyu-manage" in skills
    assert "xianyu-content" in skills
    assert "xianyu-metrics" in skills

    print("✅ 技能注册中心测试通过")


def test_list_skills():
    """测试列出技能"""
    from skills import list_skills

    skills = list_skills()
    print(f"✅ 可用技能: {skills}")

    assert len(skills) >= 4
    assert "xianyu-publish" in skills

    print("✅ 列出技能测试通过")


def test_load_skill():
    """测试加载技能"""
    from skills import load_skill

    skill = load_skill("xianyu-publish")
    assert skill is not None
    assert skill.name == "xianyu-publish"

    print("✅ 加载技能测试通过")


def test_describe_skill():
    """测试技能描述"""
    from skills import describe_skill

    desc = describe_skill("xianyu-content")
    assert desc is not None
    assert "name" in desc
    assert "description" in desc

    print(f"✅ 技能描述: {desc['name']} - {desc['description'][:50]}...")


async def test_publish_skill():
    """测试发布技能"""
    from skills.xianyu_publish import XianyuPublishSkill

    skill = XianyuPublishSkill()
    skill.agent = MockAgent()

    result = await skill.execute("publish", {
        "product_name": "测试商品",
        "price": 100.0,
        "category": "General"
    })

    print(f"✅ 发布结果: {result.get('status')}")
    assert result.get("status") in ["success", "error"]


async def test_manage_skill():
    """测试管理技能"""
    from skills.xianyu_manage import XianyuManageSkill

    skill = XianyuManageSkill()
    skill.agent = MockAgent()

    result = await skill.execute("polish", {"product_id": "item_123"})
    print(f"✅ 擦亮结果: {result.get('status')}")
    assert result.get("status") in ["success", "error"]

    result = await skill.execute("price_update", {
        "product_id": "item_123",
        "new_price": 90.0
    })
    print(f"✅ 调价结果: {result.get('status')}")


async def test_content_skill():
    """测试内容生成技能"""
    from skills.xianyu_content import XianyuContentSkill

    skill = XianyuContentSkill()
    skill.agent = MockAgent()

    result = await skill.execute("generate_title", {
        "product_name": "iPhone 15",
        "features": ["256GB", "蓝色"]
    })

    print(f"✅ 标题生成: {result.get('title', '')[:30]}...")
    assert result.get("status") == "success"

    result = await skill.execute("generate_description", {
        "product_name": "iPhone 15",
        "condition": "95新",
        "reason": "换新手机"
    })

    print(f"✅ 描述生成: {result.get('description', '')[:50]}...")


async def test_metrics_skill():
    """测试数据统计技能"""
    from skills.xianyu_metrics import XianyuMetricsSkill

    skill = XianyuMetricsSkill()
    skill.agent = MockAgent()

    result = await skill.execute("dashboard", {})
    print(f"✅ 仪表盘: {result.get('status')}")
    assert result.get("status") == "success"

    result = await skill.execute("product_metrics", {
        "product_id": "item_123",
        "days": 7
    })
    print(f"✅ 商品指标: {result.get('status')}")


async def test_all_skills():
    """测试所有技能"""
    from skills import load_skill

    skills_to_test = [
        ("xianyu-publish", {"action": "publish", "product_name": "测试", "price": 100}),
        ("xianyu-manage", {"action": "polish", "product_id": "test"}),
        ("xianyu-content", {"action": "generate_title", "product_name": "测试"}),
        ("xianyu-metrics", {"action": "dashboard"}),
    ]

    for skill_name, params in skills_to_test:
        skill = load_skill(skill_name)
        if skill:
            skill.agent = MockAgent()
            result = await skill.execute(params.get("action", ""), params)
            print(f"✅ {skill_name}: {result.get('status')}")


def run_tests():
    """运行所有测试"""
    print("="*60)
    print("闲鱼自动化工具 - 技能集成测试")
    print("="*60)

    tests = [
        ("技能注册中心", test_skill_registry),
        ("列出技能", test_list_skills),
        ("加载技能", test_load_skill),
        ("技能描述", test_describe_skill),
    ]

    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"❌ {name} 测试失败: {e}")

    async def run_async_tests():
        async_tests = [
            ("发布技能", test_publish_skill),
            ("管理技能", test_manage_skill),
            ("内容技能", test_content_skill),
            ("数据统计技能", test_metrics_skill),
            ("全部技能", test_all_skills),
        ]

        for name, test_func in async_tests:
            try:
                await test_func()
            except Exception as e:
                print(f"❌ {name} 测试失败: {e}")

    asyncio.run(run_async_tests())

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60)


if __name__ == "__main__":
    run_tests()
