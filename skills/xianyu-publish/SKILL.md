---
name: xianyu_publish
description: 发布商品到闲鱼，支持 AI 文案生成、图片上传、批量发布
---

# 闲鱼商品发布

当用户想要在闲鱼上发布（上架）商品时，使用此技能。

## 能力范围

- 发布单个商品到闲鱼
- 支持设置标题、描述、价格、分类、图片、标签
- 图片需要提供服务器上的文件路径

## 使用方法

使用 `bash` 工具执行以下命令：

### 发布商品

```bash
cd /home/node/.openclaw/workspace && python -m src.cli publish \
  --title "商品标题" \
  --price 价格数字 \
  --description "商品描述文本" \
  --category "分类名称" \
  --images 图片路径1 图片路径2 \
  --tags 标签1 标签2
```

参数说明：
- `--title`（必填）：商品标题，建议 10-25 字
- `--price`（必填）：售价，数字
- `--description`：商品详细描述
- `--original-price`：原价
- `--category`：分类（数码手机、电脑办公、家电、服饰鞋包等）
- `--images`：图片文件路径列表，空格分隔
- `--tags`：标签列表，如 95新 国行 配件齐全

### 示例

用户说："帮我发布一个 iPhone 15 Pro，价格 5999，95新"

```bash
cd /home/node/.openclaw/workspace && python -m src.cli publish \
  --title "【自用出】iPhone 15 Pro 256G 原色钛金属 95新" \
  --price 5999 \
  --description "自用出闲置 iPhone 15 Pro 256GB，原色钛金属配色，95新成色，配件齐全（包括原装充电线），无磕碰无划痕。换机出。" \
  --category "数码手机" \
  --tags 95新 国行 配件齐全 iPhone
```

## 注意事项

- 生成标题时要吸引人，突出卖点，控制在 25 字以内
- 描述要真实详细，包含成色、原因、配件等信息
- 命令输出为 JSON 格式，包含 success、product_id、product_url 字段
