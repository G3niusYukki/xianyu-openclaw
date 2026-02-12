@echo off
REM 闲鱼自动化工具 - Windows启动脚本

chcp 65001 >nul

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 启动Streamlit应用
streamlit run web\app.py --server.port=8501 --server.headless=false
