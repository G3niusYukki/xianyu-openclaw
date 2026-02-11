---
name: xianyu-manage
description: Manage existing listings on Xianyu (Polish/Refresh, Delist, Price Drop).
usage: |
  User: "帮我擦亮所有商品"
  User: "把 iPhone 13 下架"
  User: "所有商品降价 5%"
---

# Xianyu Manage Skill

This skill handles the maintenance of existing listings.

## Capabilities

- `polish_listings(limit=None)`: Refresh listings to get more views.
- `delist_product(product_name)`: Remove a product from shelves.
- `update_price(product_name, new_price)`: Change the price of a listing.

## Workflow (Polish)

1.  Navigate to "My Sellings" page.
2.  Iterate through items.
3.  Find valid "Polish" buttons (dates back to >24h usually).
4.  Click Polish with random delays.
