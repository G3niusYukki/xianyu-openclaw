# 🚀 可视化面板和简易化部署方案

## 概述

本项目新增了可视化Web面板和一键部署功能，让操作人员可以更便捷地使用闲鱼自动化工具。

---

## 📋 主要特性

### 1. 可视化Web界面

基于 **Streamlit + React** 构建的现代Web界面:

- ✅ 直观的仪表盘，实时展示运营数据
- ✅ 简单的商品发布流程，支持单个和批量发布
- ✅ 便捷的运营管理功能（擦亮、调价、下架）
- ✅ 统一的账号管理和定时任务设置
- ✅ 完善的数据分析和报表生成

### 2. 一键安装部署

提供跨平台的一键安装脚本:

- **Windows**: `install.bat` + `start.bat`
- **macOS/Linux**: `install.sh` + `start.sh`

安装脚本会自动:
- 检测系统环境（Python、Node.js）
- 创建Python虚拟环境
- 安装所有依赖包
- 初始化配置文件
- 构建前端项目

### 3. 桌面应用支持

支持打包为独立桌面应用:

- **PyInstaller**: Python后端打包
- **Electron**: React前端打包
- 一键生成可执行文件

---

## 📦 项目结构

```
xianyu-openclaw/
├── web/                          # Web服务
│   ├── app.py                    # Streamlit应用入口
│   ├── api.py                    # FastAPI接口
│   ├── pages/                    # Streamlit页面
│   │   ├── dashboard.py          # 仪表盘
│   │   ├── publish.py            # 商品发布
│   │   ├── operations.py         # 运营管理
│   │   ├── accounts.py           # 账号管理
│   │   └── analytics.py          # 数据分析
│   └── frontend/                # React前端
│       ├── src/
│       │   ├── components/       # React组件
│       │   ├── pages/           # 页面组件
│       │   ├── services/         # API服务
│       │   └── types/           # 类型定义
│       ├── package.json         # 前端依赖
│       ├── vite.config.ts       # Vite配置
│       └── electron.js          # Electron配置
├── install.sh                   # macOS/Linux安装脚本
├── install.bat                  # Windows安装脚本
├── start.sh                     # macOS/Linux启动脚本
├── start.bat                    # Windows启动脚本
├── pyinstaller.spec             # PyInstaller打包配置
├── USER_GUIDE.md                # 用户使用指南
└── DEPLOYMENT.md                # 本文档
```

---

## 🚀 快速开始

### 前置要求

- **Python**: 3.10+
- **Node.js**: 18+

### 一键安装

#### Windows

```cmd
# 1. 双击运行安装脚本
install.bat

# 2. 等待安装完成后，双击启动
start.bat

# 3. 浏览器访问
http://localhost:8501
```

#### macOS/Linux

```bash
# 1. 运行安装脚本
bash install.sh

# 2. 启动应用
bash start.sh

# 3. 浏览器访问
http://localhost:8501
```

### 手动安装（开发模式）

```bash
# 1. 安装Python依赖
pip install -r requirements.txt

# 2. 安装前端依赖
cd web/frontend
npm install
npm run build
cd ../..

# 3. 启动后端
streamlit run web/app.py
```

---

## 🎨 功能说明

### 仪表盘

- 关键指标卡片（在售商品、浏览量、想要数、营收）
- 浏览量趋势图表（近7天）
- 账号状态列表
- 最新告警信息
- 快捷操作按钮

### 商品发布

**单个发布**:
- 分步式发布流程（3步）
- AI智能生成标题和描述
- 图片上传和预览
- 支持邮寄/面交设置

**批量发布**:
- Excel/CSV模板导入
- 批量图片处理
- 智能发布间隔控制

### 运营管理

- 批量擦亮（可设置数量和间隔）
- 价格调整（单个/批量/打折）
- 商品下架/上架
- 操作结果统计

### 账号管理

- 多账号添加和管理
- Cookie验证和刷新
- 健康度监控
- 定时任务创建和管理

### 数据分析

- 运营报表（日报/周报/月报）
- 趋势分析图表
- 商品排行榜
- 数据导出（CSV/Excel/JSON）

---

## 📦 桌面应用打包

### 使用Electron打包（推荐）

```bash
cd web/frontend

# 开发模式
npm run electron-dev

# 构建并打包
npm run electron-build
```

打包后的文件位置:
- Windows: `dist-electron/*.exe`
- macOS: `dist-electron/*.dmg`

### 使用PyInstaller打包

```bash
# 打包Python应用
pyinstaller pyinstaller.spec

# 打包后的文件在 dist/xianyu-automation/
```

---

## 🔧 配置说明

### 环境变量 (.env)

```bash
# AI服务
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx

# 闲鱼Cookie
XIANYU_COOKIE_1=your_cookie_here

# 服务端口
OPENCLAW_PORT=9222
```

### 配置文件 (config/config.yaml)

```yaml
app:
  name: "xianyu-openclaw"
  log_level: "INFO"

ai:
  provider: "deepseek"
  model: "deepseek-chat"

media:
  max_width: 1500
  max_height: 1500
```

详细配置说明请参考 [USER_GUIDE.md](USER_GUIDE.md)

---

## 📊 技术架构

```
┌─────────────────────────────────────────┐
│          用户浏览器 (React前端)          │
│         http://localhost:8501           │
└──────────────┬──────────────────────────┘
               │
               ↓
┌─────────────────────────────────────────┐
│       Streamlit Web服务 (app.py)        │
│   ┌───────────────────────────────┐   │
│   │  页面: dashboard, publish, ...  │   │
│   └──────────────┬────────────────┘   │
└──────────────────┼─────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────┐
│         FastAPI接口服务 (api.py)        │
│  ┌───────────────────────────────┐    │
│  │  /api/dashboard, /api/...    │    │
│  └──────────────┬────────────────┘    │
└──────────────────┼─────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────┐
│         核心业务服务层                   │
│  ListingService, OperationsService, ...  │
└─────────────────────────────────────────┘
```

---

## 🐛 常见问题

### Q1: 安装失败

- 检查Python和Node.js版本
- 确保有网络连接
- 查看错误日志

### Q2: 无法启动

- 确认端口8501未被占用
- 检查虚拟环境是否激活
- 查看logs目录日志

### Q3: Cookie过期

- 在账号管理页面刷新Cookie
- 更新.env文件

详细问题请参考 [USER_GUIDE.md](USER_GUIDE.md#常见问题)

---

## 📝 更新日志

### v2.0.0 (2024-02-12)

#### 新增功能

- ✨ 可视化Web界面（Streamlit + React）
- ✨ 一键安装脚本（Windows/macOS/Linux）
- ✨ 桌面应用打包支持
- ✨ 完整的用户使用指南

#### 功能改进

- 📈 实时仪表盘和数据可视化
- 🛒 简化的商品发布流程
- ⚙️ 便捷的运营管理功能
- 👥 统一的账号管理界面
- 📊 丰富的数据分析报表

---

## 📞 技术支持

- **用户指南**: [USER_GUIDE.md](USER_GUIDE.md)
- **GitHub**: https://github.com/yourusername/xianyu-openclaw
- **Issue**: https://github.com/yourusername/xianyu-openclaw/issues

---

**祝使用愉快！** 🦞
