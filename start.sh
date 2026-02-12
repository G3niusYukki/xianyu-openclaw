#!/bin/bash

# 闲鱼自动化工具 - macOS启动脚本

# 激活虚拟环境
source venv/bin/activate

# 启动Streamlit应用
streamlit run web/app.py --server.port=8501 --server.headless=false
