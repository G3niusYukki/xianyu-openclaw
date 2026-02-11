"""
内容生成服务
Content Generation Service

提供AI驱动的商品标题和描述生成功能
"""

import os
from typing import List, Optional, Dict, Any

from openai import OpenAI, AsyncOpenAI

from src.core.config import get_config
from src.core.logger import get_logger


class ContentService:
    """
    内容生成服务

    集成大语言模型，生成高质量的商品标题和描述文案
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化内容生成服务

        Args:
            config: 配置字典
        """
        self.config = config or get_config().ai
        self.logger = get_logger()

        self.api_key = self.config.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = self.config.get("base_url") or os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
        self.model = self.config.get("model", "deepseek-chat")
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", 1000)
        self.fallback_enabled = self.config.get("fallback_enabled", True)
        self.fallback_model = self.config.get("fallback_model", "gpt-3.5-turbo")

        self.client: Optional[OpenAI] = None
        self.async_client: Optional[AsyncOpenAI] = None

        self._init_client()

    def _init_client(self) -> None:
        """初始化AI客户端"""
        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
                self.logger.success("AI client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize AI client: {e}")
                self.client = None
        else:
            self.logger.warning("AI API Key not found. Content generation will use templates.")

    def _call_ai(self, prompt: str, max_tokens: Optional[int] = None) -> Optional[str]:
        """
        调用AI生成内容

        Args:
            prompt: 提示词
            max_tokens: 最大token数

        Returns:
            生成的内容，失败返回None
        """
        if not self.client:
            return None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"AI call failed: {e}")
            return None

    def generate_title(self, product_name: str, features: List[str],
                       category: str = "General") -> str:
        """
        生成闲鱼商品标题

        Args:
            product_name: 商品名称
            features: 商品特点列表
            category: 商品分类

        Returns:
            生成的标题
        """
        if not self.client:
            return self._default_title(product_name, features)

        keywords = self._get_category_keywords(category)
        prompt = f"""
        请为闲鱼（二手交易平台）商品生成一个吸引人的标题。

        商品名称: {product_name}
        商品特点: {', '.join(features)}
        商品分类: {category}
        推荐关键词: {', '.join(keywords[:5])}

        要求:
        1. 15-25字以内
        2. 包含1-2个热搜关键词提高搜索曝光
        3. 突出商品卖点或性价比
        4. 真实感强，不要过于广告腔
        5. 可以使用符号增加吸引力，如【】、🔥、💰等
        """
        result = self._call_ai(prompt, max_tokens=60)

        if result and len(result) <= 30:
            return result

        return self._default_title(product_name, features)

    def _default_title(self, product_name: str, features: List[str]) -> str:
        """生成默认标题"""
        feature_str = ' '.join(features[:2]) if features else ''
        return f"【转卖】{product_name} {feature_str}".strip()[:25]

    def _get_category_keywords(self, category: str) -> List[str]:
        """获取分类热搜关键词"""
        keywords = {
            "数码手机": ["自用", "闲置", "正品", "国行", "原装", "95新", "便宜出"],
            "电脑办公": ["办公", "游戏", "高性能", "低价", "成色新"],
            "家电": ["家用", "闲置", "几乎全新", "保修期内"],
            "服饰鞋包": ["专柜", "正品", "全新", "闲置", "白菜价"],
            "美妆护肤": ["正品", "保真", "闲置", "临期特惠"],
            "家居": ["二手", "搬家急出", "几乎没用过"],
            "General": ["闲置", "便宜出", "自用", "转让"],
        }
        return keywords.get(category, keywords["General"])

    def generate_description(self, product_name: str, condition: str,
                            reason: str, tags: List[str],
                            extra_info: Optional[str] = None) -> str:
        """
        生成闲鱼商品描述文案

        Args:
            product_name: 商品名称
            condition: 成色描述
            reason: 转手原因
            tags: 标签列表
            extra_info: 额外信息

        Returns:
            生成的描述文案
        """
        if not self.client:
            return self._default_description(product_name, condition, reason, tags)

        prompt = f"""
        请写一段闲鱼商品的详细描述文案。

        商品名称: {product_name}
        商品成色: {condition}
        转手原因: {reason}
        标签: {', '.join(tags)}
        额外信息: {extra_info or '无'}

        要求:
        1. 语气亲切自然，营造真实个人卖家感
        2. 开头引入，说明商品来源或特点
        3. 中间详细描述成色、使用情况、瑕疵（如有）
        4. 结尾说明交易方式，引导私聊
        5. 100-200字为宜
        6. 不要使用过多emoji，适度使用
        """
        result = self._call_ai(prompt, max_tokens=300)

        if result and len(result) >= 50:
            return result

        return self._default_description(product_name, condition, reason, tags)

    def _default_description(self, product_name: str, condition: str,
                             reason: str, tags: List[str]) -> str:
        """生成默认描述"""
        return f"""出闲置 {product_name}，成色{condition}。

{reason}，所以转让。

商品详情：
- 成色：{condition}
- 交易说明：走闲鱼，诚心要的私聊"""

    def generate_listing_content(self, product_info: Dict[str, Any]) -> Dict[str, str]:
        """
        生成完整商品发布内容

        Args:
            product_info: 商品信息字典

        Returns:
            包含title和description的字典
        """
        product_name = product_info.get("name", "商品")
        features = product_info.get("features", [])
        category = product_info.get("category", "General")
        condition = product_info.get("condition", "95新")
        reason = product_info.get("reason", "用不上")
        tags = product_info.get("tags", [])
        extra_info = product_info.get("extra_info")

        title = self.generate_title(product_name, features, category)
        description = self.generate_description(
            product_name, condition, reason, tags, extra_info
        )

        return {
            "title": title,
            "description": description
        }

    def optimize_title(self, current_title: str, category: str = "General") -> str:
        """
        优化现有标题

        Args:
            current_title: 当前标题
            category: 商品分类

        Returns:
            优化后的标题
        """
        keywords = self._get_category_keywords(category)

        prompt = f"""
        请优化以下闲鱼商品标题，提高搜索曝光和吸引力。

        当前标题: {current_title}
        分类: {category}
        推荐关键词: {', '.join(keywords)}

        要求:
        1. 保持标题核心信息不变
        2. 适当添加热搜关键词
        3. 15-25字以内
        4. 不要过于广告化

        请直接返回优化后的标题，不需要额外说明。
        """

        result = self._call_ai(prompt, max_tokens=50)

        if result and len(result) >= 5 and len(result) <= 30:
            return result

        return current_title

    def generate_seo_keywords(self, product_name: str, category: str) -> List[str]:
        """
        生成SEO优化关键词

        Args:
            product_name: 商品名称
            category: 商品分类

        Returns:
            关键词列表
        """
        prompt = f"""
        为闲鱼商品生成SEO关键词。

        商品: {product_name}
        分类: {category}

        请生成5-8个相关热搜关键词，按热度排序。
        只需要返回关键词列表，用逗号分隔。
        """

        result = self._call_ai(prompt, max_tokens=100)

        if result:
            keywords = [k.strip() for k in result.split(',')]
            return [k for k in keywords if k][:8]

        return self._get_category_keywords(category)
