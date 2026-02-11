"""
闲鱼内容生成技能
Xianyu Content Skill

生成闲鱼商品标题和描述文案
"""

from openclaw.agent.skill import AgentSkill
from typing import Dict, Any, List, Optional


class XianyuContentSkill(AgentSkill):
    """
    内容生成技能

    集成大语言模型生成高质量的闲鱼商品标题和描述
    """

    name = "xianyu-content"
    description = "Generate catchy titles, persuasive descriptions, and SEO keywords for Xianyu listings"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        执行内容生成操作

        Args:
            action: 操作类型
            **kwargs: 操作参数
        """
        action_map = {
            "generate_title": self._generate_title,
            "generate_description": self._generate_description,
            "generate_full": self._generate_full,
            "optimize_title": self._optimize_title,
            "optimize_description": self._optimize_description,
            "generate_keywords": self._generate_keywords,
            "generate_seo": self._generate_seo,
        }

        if action in action_map:
            return await action_map[action](kwargs)
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

    async def _generate_title(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成标题

        Args:
            product_name: 商品名称
            features: 商品特点列表
            category: 商品分类
            style: 标题风格 (catchy, simple, professional)
        """
        product_name = params.get("product_name", "商品")
        features = params.get("features", [])
        category = params.get("category", "General")
        style = params.get("style", "catchy")

        self.log(f"Generating title for: {product_name}")

        try:
            from src.modules.content.service import ContentService

            service = ContentService()
            title = service.generate_title(product_name, features, category)

            return {
                "status": "success",
                "action": "generate_title",
                "product_name": product_name,
                "title": title,
                "length": len(title),
                "category": category,
                "style": style
            }

        except ImportError:
            return self._mock_generate("title", product_name)
        except Exception as e:
            self.log(f"Title generation error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _generate_description(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成描述文案

        Args:
            product_name: 商品名称
            condition: 成色
            reason: 转手原因
            tags: 标签列表
            extra_info: 额外信息
        """
        product_name = params.get("product_name", "商品")
        condition = params.get("condition", "95新")
        reason = params.get("reason", "用不上")
        tags = params.get("tags", [])
        extra_info = params.get("extra_info")

        self.log(f"Generating description for: {product_name}")

        try:
            from src.modules.content.service import ContentService

            service = ContentService()
            description = service.generate_description(
                product_name, condition, reason, tags, extra_info
            )

            return {
                "status": "success",
                "action": "generate_description",
                "product_name": product_name,
                "description": description,
                "length": len(description),
                "condition": condition
            }

        except ImportError:
            return self._mock_generate("description", product_name)
        except Exception as e:
            self.log(f"Description generation error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _generate_full(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成完整商品内容

        Args:
            product_name: 商品名称
            features: 商品特点
            category: 分类
            condition: 成色
            reason: 转手原因
            tags: 标签
        """
        product_name = params.get("product_name", "商品")
        features = params.get("features", [])
        category = params.get("category", "General")
        condition = params.get("condition", "95新")
        reason = params.get("reason", "用不上")
        tags = params.get("tags", [])

        self.log(f"Generating full content for: {product_name}")

        try:
            from src.modules.content.service import ContentService

            service = ContentService()

            title = service.generate_title(product_name, features, category)
            description = service.generate_description(
                product_name, condition, reason, tags
            )
            keywords = service.generate_seo_keywords(product_name, category)

            return {
                "status": "success",
                "action": "generate_full",
                "product_name": product_name,
                "title": title,
                "description": description,
                "keywords": keywords,
                "category": category
            }

        except ImportError:
            return {
                "status": "success",
                "action": "generate_full",
                "product_name": product_name,
                "title": f"【转卖】{product_name}",
                "description": f"出闲置 {product_name}，成色{condition}。",
                "keywords": ["闲置", "便宜出"],
                "mock": True
            }
        except Exception as e:
            self.log(f"Full content generation error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _optimize_title(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化现有标题

        Args:
            current_title: 当前标题
            category: 商品分类
        """
        current_title = params.get("current_title", "")
        category = params.get("category", "General")

        if not current_title:
            return {"status": "error", "message": "Current title required"}

        self.log(f"Optimizing title: {current_title[:30]}...")

        try:
            from src.modules.content.service import ContentService

            service = ContentService()
            optimized = service.optimize_title(current_title, category)

            return {
                "status": "success",
                "action": "optimize_title",
                "original": current_title,
                "optimized": optimized
            }

        except ImportError:
            return {
                "status": "success",
                "action": "optimize_title",
                "original": current_title,
                "optimized": current_title,
                "mock": True
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _optimize_description(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化现有描述

        Args:
            current_description: 当前描述
        """
        current_description = params.get("current_description", "")

        if not current_description:
            return {"status": "error", "message": "Current description required"}

        return {
            "status": "success",
            "action": "optimize_description",
            "original": current_description,
            "optimized": current_description,
            "mock": True
        }

    async def _generate_keywords(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成标签关键词

        Args:
            product_name: 商品名称
            category: 商品分类
        """
        product_name = params.get("product_name", "商品")
        category = params.get("category", "General")

        self.log(f"Generating keywords for: {product_name}")

        try:
            from src.modules.content.service import ContentService

            service = ContentService()
            keywords = service.generate_seo_keywords(product_name, category)

            return {
                "status": "success",
                "action": "generate_keywords",
                "product_name": product_name,
                "keywords": keywords,
                "count": len(keywords)
            }

        except ImportError:
            return {
                "status": "success",
                "action": "generate_keywords",
                "product_name": product_name,
                "keywords": ["闲置", "便宜出", "自用"],
                "mock": True
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _generate_seo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成完整SEO内容

        Args:
            product_name: 商品名称
            features: 特点
            category: 分类
        """
        product_name = params.get("product_name", "商品")
        features = params.get("features", [])
        category = params.get("category", "General")

        return {
            "status": "success",
            "action": "generate_seo",
            "product_name": product_name,
            "title": f"{product_name} {' '.join(features)}",
            "description": f"专业出售{product_name}，{', '.join(features)}。",
            "keywords": [product_name] + features,
            "mock": True
        }

    def _mock_generate(self, content_type: str, product_name: str) -> Dict[str, Any]:
        """生成模拟内容"""
        if content_type == "title":
            return {
                "status": "success",
                "action": "generate_title",
                "product_name": product_name,
                "title": f"【转卖】{product_name}",
                "length": len(product_name) + 6,
                "mock": True
            }
        else:
            return {
                "status": "success",
                "action": "generate_description",
                "product_name": product_name,
                "description": f"出闲置 {product_name}，成色95新。",
                "length": 20,
                "mock": True
            }
