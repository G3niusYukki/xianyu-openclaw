"""
闲鱼技能注册中心
Xianyu Skills Registry

提供技能注册、发现和加载功能
"""

import importlib
from typing import Dict, List, Type, Optional, Any
from openclaw.agent.skill import AgentSkill


class SkillsRegistry:
    """
    技能注册中心

    管理所有闲鱼相关技能的注册和发现
    """

    _skills: Dict[str, Type[AgentSkill]] = {}
    _skill_paths = {
        "xianyu-publish": ("skills.xianyu_publish", "skill", "XianyuPublishSkill"),
        "xianyu-manage": ("skills.xianyu_manage", "skill", "XianyuManageSkill"),
        "xianyu-content": ("skills.xianyu_content", "skill", "XianyuContentSkill"),
        "xianyu-metrics": ("skills.xianyu_metrics", "skill", "XianyuMetricsSkill"),
        "xianyu-accounts": ("skills.xianyu_accounts", "skill", "XianyuAccountsSkill"),
    }

    @classmethod
    def register(cls, skill_class: Type[AgentSkill]) -> Type[AgentSkill]:
        """
        注册技能
        """
        name = getattr(skill_class, "name", skill_class.__name__)
        cls._skills[name] = skill_class
        return skill_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[AgentSkill]]:
        """
        获取技能类
        """
        if name in cls._skills:
            return cls._skills[name]

        if name in cls._skill_paths:
            return cls._load_skill(name)

        return None

    @classmethod
    def _load_skill(cls, name: str) -> Optional[Type[AgentSkill]]:
        """
        动态加载技能
        """
        if name not in cls._skill_paths:
            return None

        module_path, module_name, class_name = cls._skill_paths[name]

        try:
            module = importlib.import_module(module_path)
            skill_class = getattr(module, class_name)
            cls._skills[name] = skill_class
            return skill_class
        except (ImportError, AttributeError) as e:
            print(f"Failed to load skill {name}: {e}")
            return None

    @classmethod
    def list(cls) -> List[str]:
        """
        列出所有已注册技能
        """
        return list(cls._skills.keys())

    @classmethod
    def all(cls) -> Dict[str, Type[AgentSkill]]:
        """
        获取所有已注册技能
        """
        return cls._skills.copy()

    @classmethod
    def load_all(cls) -> Dict[str, Type[AgentSkill]]:
        """
        加载所有可用技能
        """
        for name in cls._skill_paths:
            cls.get(name)
        return cls._skills.copy()


def get_skill(name: str) -> Optional[Type[AgentSkill]]:
    """
    获取技能类
    """
    return SkillsRegistry.get(name)


def list_skills() -> List[str]:
    """
    列出所有可用技能
    """
    registry = SkillsRegistry.load_all()
    return list(registry.keys())


def load_skill(name: str) -> Optional[AgentSkill]:
    """
    加载技能实例
    """
    skill_class = get_skill(name)
    if skill_class:
        return skill_class()
    return None


def describe_skill(name: str) -> Optional[Dict[str, Any]]:
    """
    获取技能描述信息
    """
    skill_class = get_skill(name)
    if skill_class:
        return {
            "name": getattr(skill_class, "name", name),
            "description": getattr(skill_class, "description", ""),
            "module": skill_class.__module__,
        }
    return None
