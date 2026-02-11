---
name: xianyu-content
description: Generate AI-powered titles and descriptions for Xianyu listings
usage: |
  User: "帮我生成iPhone 15的标题"
  User: "写一段闲置电脑的描述"
  User: "给这个商品生成一些关键词"
---

# Xianyu Content Skill

AI-powered content generation for Xianyu marketplace listings.

## Capabilities

- **Title Generation**: Generate catchy, searchable titles
- **Description Writing**: Create persuasive product descriptions
- **Keyword Optimization**: Suggest relevant tags and keywords
- **Content Optimization**: Improve existing titles and descriptions

## Usage Examples

### Generate Title
```
User: 帮我生成iPhone 15的标题
Action: generate_title, product_name="iPhone 15", features=["256GB", "蓝色"]
Result: "iPhone 15 256G 蓝色 国行 99新"
```

### Generate Description
```
User: 写一段闲置电脑的描述
Action: generate_description, product_name="MacBook Pro", condition="95新", reason="换新电脑"
Result: "出闲置 MacBook Pro，95新..."
```

## Best Practices

1. Provide as much product detail as possible
2. Include condition, brand, and key features
3. Specify if there are any defects or accessories
