# 闲鱼自动化工具 - 用户使用指南

## 📖 目录

- [快速开始](#快速开始)
- [安装指南](#安装指南)
- [配置说明](#配置说明)
- [功能使用](#功能使用)
- [常见问题](#常见问题)

---

## 🚀 快速开始

### 系统要求

- **操作系统**: Windows 10/11, macOS 10.15+
- **Python**: 3.10 或更高版本
- **Node.js**: 18.0 或更高版本

### 一键安装

#### Windows用户

1. 双击运行 `install.bat`
2. 等待安装完成
3. 双击 `start.bat` 启动应用

#### macOS/Linux用户

1. 在终端执行: `bash install.sh`
2. 等待安装完成
3. 执行: `bash start.sh` 启动应用

### 访问应用

安装启动后，在浏览器中打开:

```
http://localhost:8501
```

---

## 📦 安装指南

### 前置准备

1. **安装Python**
   - 访问 https://www.python.org/downloads/
   - 下载并安装 Python 3.10+
   - 安装时勾选 "Add Python to PATH"

2. **安装Node.js**
   - 访问 https://nodejs.org/
   - 下载并安装 LTS 版本

### 手动安装（不推荐）

```bash
# 1. 克隆项目
git clone https://github.com/yourusername/xianyu-openclaw.git
cd xianyu-openclaw

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows

# 3. 安装Python依赖
pip install -r requirements.txt

# 4. 安装前端依赖
cd web/frontend
npm install
npm run build
cd ../..

# 5. 配置环境变量
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# 6. 启动应用
streamlit run web/app.py
```

---

## ⚙️ 配置说明

### 1. 环境变量配置 (.env)

```bash
# AI服务配置
DEEPSEEK_API_KEY=sk-xxx  # 替换为你的DeepSeek API密钥
OPENAI_API_KEY=sk-xxx    # 替换为你的OpenAI API密钥

# 闲鱼账号Cookie（从浏览器获取）
XIANYU_COOKIE_1=your_cookie_here
XIANYU_COOKIE_2=your_second_cookie_here

# OpenClaw配置（如需要）
OPENCLAW_HOST=localhost
OPENCLAW_PORT=9222
```

### 2. 如何获取闲鱼Cookie

1. 在浏览器中登录闲鱼
2. 按 `F12` 打开开发者工具
3. 切换到 `Network` 标签
4. 刷新页面，找到任意请求
5. 在 `Request Headers` 中复制 `Cookie` 的值
6. 将Cookie填入 `.env` 文件中的 `XIANYU_COOKIE_1`

### 3. 配置文件说明 (config/config.yaml)

```yaml
# 应用配置
app:
  name: "xianyu-openclaw"
  log_level: "INFO"

# AI服务配置
ai:
  provider: "deepseek"  # 可选: deepseek, openai
  model: "deepseek-chat"

# 媒体处理配置
media:
  max_width: 1500
  max_height: 1500
  output_quality: 85
  watermark:
    enabled: false
    text: "闲鱼助手"
```

---

## 🎯 功能使用

### 1. 仪表盘

仪表盘提供运营数据的实时概览:

- **在售商品数**: 当前上架的商品总数
- **总浏览量**: 所有商品的累计浏览次数
- **总想要数**: 所有商品的累计想要人数
- **总营收**: 累计成交金额
- **浏览量趋势**: 近7天浏览量变化曲线
- **账号状态**: 各账号的健康度和启用状态

**快捷操作**:
- 🔄 一键擦亮所有商品
- 📊 生成日报

### 2. 商品发布

#### 单个发布

1. 点击侧边栏 "商品发布"
2. 选择 "单个发布" 模式
3. 填写商品信息:
   - 商品名称（必填）
   - 商品分类（必填）
   - 售价（必填）
   - 原价（可选）
   - 成色（必填）
   - 出售原因
   - 商品特性
4. 上传商品图片（最多9张）
5. 选择AI智能生成选项:
   - AI生成标题（推荐开启）
   - AI生成描述（推荐开启）
6. 点击 "立即发布"

#### 批量发布

1. 选择 "批量发布" 模式
2. 下载商品信息模板
3. 按模板格式填写商品信息
4. 上传填写好的Excel/CSV文件
5. 设置发布间隔
6. 点击 "开始批量发布"

### 3. 运营管理

#### 批量擦亮

1. 设置擦亮数量（默认50个）
2. 设置操作间隔（建议3-6秒）
3. 点击 "开始批量擦亮"
4. 查看擦亮结果统计

#### 价格调整

**单个调整**:
1. 选择要调整的商品
2. 输入新价格
3. 点击 "更新价格"

**批量调整**:
1. 下载价格调整模板
2. 填写商品ID和新价格
3. 上传文件并执行

#### 商品管理

- 查看所有商品列表
- 下架商品
- 重新上架已下架商品

### 4. 账号管理

#### 添加账号

1. 点击 "添加账号"
2. 填写账号信息:
   - 账号名称
   - 优先级（数字越小优先级越高）
   - Cookie（必填）
3. 点击 "添加"

#### 管理账号

- 启用/禁用账号
- 设置为当前账号
- 刷新Cookie
- 删除账号

#### 定时任务

1. 点击 "定时任务" 标签
2. 点击 "创建任务"
3. 设置任务参数:
   - 任务名称
   - 任务类型（擦亮/数据采集/健康检查）
   - 执行时间（使用Cron表达式）
4. 保存任务

**常用Cron表达式**:
- `0 9 * * *` - 每天上午9点
- `0 */4 * * *` - 每4小时
- `0 9 * * 1` - 每周一上午9点

### 5. 数据分析

#### 运营报表

1. 选择报表类型（日报/周报/月报）
2. 选择时间范围
3. 点击 "生成报表"
4. 查看统计数据和图表

#### 趋势分析

1. 选择指标类型（浏览量/想要数/成交数/营收）
2. 设置时间范围（7-90天）
3. 点击 "查看趋势"
4. 查看趋势曲线和统计数据

#### 数据导出

1. 选择导出类型
2. 选择文件格式（CSV/Excel/JSON）
3. 点击 "导出数据"
4. 下载生成的文件

---

## ❓ 常见问题

### Q1: 无法启动应用

**问题**: 双击start.sh/bat后无法打开

**解决方案**:
1. 确认已正确安装Python和Node.js
2. 检查虚拟环境是否正确创建
3. 查看终端/命令行中的错误信息
4. 手动执行: `streamlit run web/app.py`

### Q2: Cookie过期

**问题**: 操作时提示Cookie无效

**解决方案**:
1. 按照上述步骤重新获取Cookie
2. 在 "账号管理" 页面点击 "刷新Cookie"
3. 更新.env文件中的Cookie值
4. 重启应用

### Q3: 图片上传失败

**问题**: 发布商品时图片无法上传

**解决方案**:
1. 检查图片格式（仅支持JPG/PNG/WEBP）
2. 检查图片大小（建议小于5MB）
3. 检查data/processed_images目录权限
4. 查看logs目录中的错误日志

### Q4: AI生成失败

**问题**: 标题或描述生成失败

**解决方案**:
1. 检查.env文件中的API密钥是否正确
2. 确认API账户有足够的额度
3. 检查网络连接
4. 可以选择关闭AI生成，手动输入

### Q5: 批量操作卡住

**问题**: 批量擦亮或发布时程序卡住

**解决方案**:
1. 检查操作间隔设置（不要小于3秒）
2. 检查浏览器是否正常运行
3. 刷新页面重试
4. 查看logs目录中的日志文件

### Q6: 如何查看错误日志

**解决方案**:
1. 打开 `logs` 目录
2. 查看最新的日志文件（按日期命名）
3. 日志文件中会记录详细的错误信息

### Q7: 应用占用端口

**问题**: 启动提示端口8501已被占用

**解决方案**:
```bash
# 指定其他端口启动
streamlit run web/app.py --server.port=8502
```

---

## 📞 技术支持

如果遇到其他问题，请:

1. 查看 `logs` 目录中的日志文件
2. 检查 `config/config.yaml` 配置是否正确
3. 确认 `.env` 环境变量是否配置正确
4. 访问项目GitHub: https://github.com/yourusername/xianyu-openclaw
5. 提交Issue: https://github.com/yourusername/xianyu-openclaw/issues

---

## 📝 版本信息

- **当前版本**: 1.0.0
- **发布日期**: 2024-02-12
- **更新日志**: 请参考项目README.md

---

**祝使用愉快！** 🦞
