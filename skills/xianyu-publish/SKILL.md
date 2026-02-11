---
name: xianyu-publish
description: Publish a product to Xianyu (Idle Fish) marketplace.
usage: |
  User: "帮我把这个iPhone 15 Pro发布到闲鱼"
  User: "卖个二手自行车"
---

# Xianyu Publish Skill

This skill allows the agent to publish a product listing to Xianyu. It handles the entire process from information gathering to final submission.

## Workflow

1.  **Information Gathering**:
    - Analyze the user's request to extract: `Product Name`, `Price` (optional), `Condition` (optional), `Images` (optional).
    - If critical information is missing, ASK the user.
        - *Critical Info*: Product Name, Condition (New/Used), Intent (Sell/Trade).
    
2.  **Content Generation (Auto)**:
    - Use LLM to generate a **Title** (max 30 chars, catchy).
    - Use LLM to generate a **Description** (detailed, persuasive).

3.  **Execution**:
    - Navigate to Xianyu Publish Page.
    - Upload images (if provided).
    - Fill in Title, Description, Price, Category.
    - Submit.

## Capabilities

- `generate_title(product_name, features)` -> str
- `generate_description(product_name, condition, features)` -> str
- `publish_listing(title, description, price, images)` -> dict

## Example Interaction

User: Sell my iPhone 13.
Agent: Sure! What's the condition? Any specific accessories or defects?
User: It's 90% new, battery 85%, comes with a case. Price around 3000.
Agent: Got it. Generating listing...
   - Title: "iPhone 13 128G 9成新 电池85% 送手机壳顺丰包邮"
   - Description: "..."
   - Listing...
   ✅ Published Successfully! Link: ...
