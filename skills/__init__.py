"""
闲鱼技能包
Xianyu Skills Package

提供闲鱼自动化运营的所有技能
"""

from .registry import (
    SkillsRegistry,
    get_skill,
    list_skills,
    load_skill,
    describe_skill,
)

from .xianyu_publish import XianyuPublishSkill
from .xianyu_manage import XianyuManageSkill
from .xianyu_content import XianyuContentSkill
from .xianyu_metrics import XianyuMetricsSkill
from .xianyu_accounts import XianyuAccountsSkill

__all__ = [
    "SkillsRegistry",
    "get_skill",
    "list_skills",
    "load_skill",
    "describe_skill",
    "XianyuPublishSkill",
    "XianyuManageSkill",
    "XianyuContentSkill",
    "XianyuMetricsSkill",
    "XianyuAccountsSkill",
]
