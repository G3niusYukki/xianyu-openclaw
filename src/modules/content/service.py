from openai import OpenAI
from loguru import logger
import os

class ContentService:
    def __init__(self, config):
        self.config = config
        self.api_key = config.get('ai', {}).get('api_key')
        self.base_url = config.get('ai', {}).get('base_url', 'https://api.openai.com/v1')
        self.model = config.get('ai', {}).get('model', 'gpt-3.5-turbo')
        
        if self.api_key:
             self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
             self.client = None
             logger.warning("AI API Key not found. Content generation will be disabled/mocked.")

    def generate_title(self, product_name: str, features: list[str]) -> str:
        """
        Generate a catchy title for Xianyu.
        """
        if not self.client:
            return f"【转卖】{product_name} {' '.join(features)}"

        prompt = f"""
        请为闲鱼（二手交易平台）上的商品生成一个吸引人的标题。
        商品名称: {product_name}
        特点: {', '.join(features)}
        要求: 
        1. 包含热搜关键词
        2. 突出性价比或急出
        3. 20字以内
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=60
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate title: {e}")
            return f"{product_name} {' '.join(features)}"

    def generate_description(self, product_name: str, condition: str, reason: str, tags: list[str]) -> str:
        """
        Generate a detailed and persuasive description.
        """
        if not self.client:
            return f"出闲置 {product_name}，成色{condition}，{reason}。感兴趣的私聊。"

        prompt = f"""
        请写一段闲鱼商品的详细描述文案。
        商品: {product_name}
        成色: {condition}
        转手原因: {reason}
        标签: {', '.join(tags)}
        
        要求:
        1. 语气亲切，真实感强
        2. 描述清晰，包含瑕疵情况（如有）
        3. 结尾引导私聊或通过信用分背书
        4. 100-200字
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate description: {e}")
            return f"出闲置 {product_name}..."
