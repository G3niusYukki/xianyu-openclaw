"""
OpenClaw集成示例
OpenClaw Integration Example

演示如何在OpenClaw框架中使用闲鱼技能
"""

from openclaw.agent.skill import AgentSkill


class XianyuPublishSkill(AgentSkill):
    """
    商品发布技能

    在OpenClaw中使用的发布技能实现
    """

    name = "xianyu-publish"
    description = "发布商品到闲鱼，包含自动文案生成和图片处理"

    async def execute(self, product_name: str, price: float, **kwargs) -> dict:
        """
        发布商品

        Usage in OpenClaw:
            User: "帮我发布iPhone 15，价格5000"
            Agent calls: xianyu_publish(product_name="iPhone 15", price=5000)
        """
        self.log(f"Publishing product: {product_name}")

        try:
            from src.modules.listing.models import Listing
            from src.modules.listing.service import ListingService
            from src.modules.content.service import ContentService

            content_service = ContentService()

            title = await self.generate_title(product_name, kwargs.get("features", []))
            description = await self.generate_description(
                product_name,
                kwargs.get("condition", "95新"),
                kwargs.get("reason", "用不上")
            )

            listing = Listing(
                title=title,
                description=description,
                price=price,
                images=kwargs.get("images", []),
                tags=kwargs.get("tags", [])
            )

            service = ListingService()
            result = await service.create_listing(listing)

            return {
                "status": "success" if result.success else "failed",
                "product_id": result.product_id,
                "link": result.product_url,
                "title": title
            }

        except Exception as e:
            self.log(f"Publish error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def generate_title(self, product_name: str, features: list) -> str:
        """生成标题"""
        try:
            prompt = f"为闲鱼商品生成简短标题：{product_name}，特点：{', '.join(features)}"
            response = await self.agent.llm.chat(prompt)
            return response.strip()[:25]
        except:
            return f"【转卖】{product_name}"

    async def generate_description(self, product_name: str, condition: str,
                                   reason: str) -> str:
        """生成描述"""
        try:
            prompt = f"写一段闲鱼商品描述：{product_name}，成色{condition}，原因：{reason}"
            response = await self.agent.llm.chat(prompt)
            return response.strip()
        except:
            return f"出闲置 {product_name}，成色{condition}，{reason}。"


class XianyuManageSkill(AgentSkill):
    """
    店铺管理技能

    在OpenClaw中使用的店铺管理技能
    """

    name = "xianyu-manage"
    description = "管理闲鱼商品：擦亮、调价、下架等"

    async def execute(self, action: str, **kwargs) -> dict:
        """
        执行管理操作

        Usage in OpenClaw:
            User: "帮我擦亮所有商品"
            Agent calls: xianyu_manage(action="polish")

            User: "把iPhone 15降到4000"
            Agent calls: xianyu_manage(action="price_update", product_name="iPhone 15", new_price=4000)
        """
        try:
            from src.modules.operations.service import OperationsService

            service = OperationsService()

            if action == "polish":
                result = await service.polish_listing(kwargs.get("product_id", ""))
                return {"status": "success", "action": "polish"}

            elif action == "batch_polish":
                result = await service.batch_polish(kwargs.get("max_items", 50))
                return {"status": "success", "polished": result.get("success", 0)}

            elif action == "price_update":
                result = await service.update_price(
                    kwargs.get("product_id", ""),
                    kwargs.get("new_price", 0)
                )
                return {"status": "success", "action": "price_update"}

            elif action == "delist":
                result = await service.delist(
                    kwargs.get("product_id", ""),
                    kwargs.get("reason", "下架")
                )
                return {"status": "success", "action": "delist"}

            else:
                return {"status": "error", "message": f"Unknown action: {action}"}

        except Exception as e:
            self.log(f"Manage error: {e}", level="error")
            return {"status": "error", "message": str(e)}


class XianyuContentSkill(AgentSkill):
    """
    内容生成技能

    在OpenClaw中使用的内容生成技能
    """

    name = "xianyu-content"
    description = "生成闲鱼商品标题、描述和关键词"

    async def execute(self, action: str, **kwargs) -> dict:
        """
        执行内容生成

        Usage in OpenClaw:
            User: "帮我写一个iPhone的标题"
            Agent calls: xianyu_content(action="title", product_name="iPhone 15")
        """
        try:
            from src.modules.content.service import ContentService

            service = ContentService()

            if action == "title":
                title = service.generate_title(
                    kwargs.get("product_name", "商品"),
                    kwargs.get("features", []),
                    kwargs.get("category", "General")
                )
                return {"status": "success", "title": title}

            elif action == "description":
                desc = service.generate_description(
                    kwargs.get("product_name", "商品"),
                    kwargs.get("condition", "95新"),
                    kwargs.get("reason", "用不上"),
                    kwargs.get("tags", [])
                )
                return {"status": "success", "description": desc}

            elif action == "keywords":
                keywords = service.generate_seo_keywords(
                    kwargs.get("product_name", "商品"),
                    kwargs.get("category", "General")
                )
                return {"status": "success", "keywords": keywords}

            elif action == "full":
                title = service.generate_title(
                    kwargs.get("product_name", "商品"),
                    kwargs.get("features", []),
                    kwargs.get("category", "General")
                )
                desc = service.generate_description(
                    kwargs.get("product_name", "商品"),
                    kwargs.get("condition", "95新"),
                    kwargs.get("reason", "用不上"),
                    kwargs.get("tags", [])
                )
                keywords = service.generate_seo_keywords(
                    kwargs.get("product_name", "商品"),
                    kwargs.get("category", "General")
                )
                return {
                    "status": "success",
                    "title": title,
                    "description": desc,
                    "keywords": keywords
                }

            else:
                return {"status": "error", "message": f"Unknown action: {action}"}

        except Exception as e:
            self.log(f"Content error: {e}", level="error")
            return {"status": "error", "message": str(e)}


class XianyuMetricsSkill(AgentSkill):
    """
    数据统计技能

    在OpenClaw中使用的数据查询技能
    """

    name = "xianyu-metrics"
    description = "查询闲鱼店铺数据和运营报表"

    async def execute(self, action: str, **kwargs) -> dict:
        """
        执行数据查询

        Usage in OpenClaw:
            User: "今天的运营数据怎么样"
            Agent calls: xianyu_metrics(action="dashboard")
        """
        try:
            from src.modules.analytics.service import AnalyticsService

            service = AnalyticsService()

            if action == "dashboard":
                stats = await service.get_dashboard_stats()
                return {"status": "success", "data": stats}

            elif action == "product":
                history = await service.get_product_metrics(
                    kwargs.get("product_id", ""),
                    kwargs.get("days", 7)
                )
                return {"status": "success", "data": history}

            elif action == "logs":
                logs = await service.get_operation_logs(kwargs.get("limit", 100))
                return {"status": "success", "logs": logs}

            else:
                return {"status": "error", "message": f"Unknown action: {action}"}

        except Exception as e:
            self.log(f"Metrics error: {e}", level="error")
            return {"status": "error", "message": str(e)}


# 在OpenClaw中使用示例
EXAMPLE_USAGE = """
# OpenClaw Agent配置示例 (AGENTS.md)

## 闲鱼助手技能

你拥有以下闲鱼运营技能：

### xianyu-publish
发布商品到闲鱼
参数: product_name, price, images, tags, features, condition, reason

### xianyu-manage  
管理店铺商品
参数: action (polish/batch_polish/price_update/delist), product_id, new_price

### xianyu-content
生成商品文案
参数: action (title/description/keywords/full), product_name, features, tags

### xianyu-metrics
查询运营数据
参数: action (dashboard/product/logs), product_id, days

## 使用示例

用户: "帮我发布这个iPhone 15，价格5000"
执行: xianyu_publish(product_name="iPhone 15", price=5000)

用户: "擦亮所有商品"
执行: xianyu_manage(action="batch_polish")

用户: "写一个macbook的标题"
执行: xianyu_content(action="title", product_name="MacBook Pro")

用户: "今天的运营数据"
执行: xianyu_metrics(action="dashboard")
"""
