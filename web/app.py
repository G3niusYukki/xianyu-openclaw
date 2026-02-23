"""闲鱼自动化工具 - Web服务入口"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from datetime import datetime

from src.core.config import Config
from src.core.logger import get_logger
from src.core.startup_checks import run_all_checks, print_startup_report
from src.modules.listing.service import ListingService
from src.modules.operations.service import OperationsService
from src.modules.analytics.service import AnalyticsService
from src.modules.accounts.service import AccountsService

logger = get_logger(__name__)

if 'startup_done' not in st.session_state:
    results = run_all_checks(skip_browser=True)
    st.session_state.startup_ok = print_startup_report(results)
    st.session_state.startup_results = results
    st.session_state.startup_done = True

# 页面配置
st.set_page_config(
    page_title="闲鱼自动化工具",
    page_icon="🦞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化session state
if 'config' not in st.session_state:
    st.session_state.config = Config()
    st.session_state.logger = logger

if 'services' not in st.session_state:
    st.session_state.services = {
        'listing': ListingService(),
        'operations': OperationsService(),
        'analytics': AnalyticsService(),
        'accounts': AccountsService()
    }

# 侧边栏
with st.sidebar:
    st.title("🦞 闲鱼自动化工具")
    st.markdown("---")
    
    page = st.radio(
        "选择功能",
        ["📊 仪表盘", "🛒 商品发布", "⚙️ 运营管理", "👥 账号管理", "📈 数据分析"]
    )
    
    st.markdown("---")
    
    # 系统状态
    st.subheader("系统状态")
    status_placeholder = st.empty()
    
    with status_placeholder.container():
        st.info("✅ 系统运行中")
        st.caption(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    st.markdown("---")
    
    # 快捷操作
    st.subheader("快捷操作")
    if st.button("🔄 一键擦亮所有商品", use_container_width=True):
        st.session_state['quick_action'] = 'polish_all'
    
    if st.button("📊 生成日报", use_container_width=True):
        st.session_state['quick_action'] = 'daily_report'

# 主页面
if page == "📊 仪表盘":
    from web.pages.dashboard import show_dashboard
    show_dashboard()
    
elif page == "🛒 商品发布":
    from web.pages.publish import show_publish
    show_publish()
    
elif page == "⚙️ 运营管理":
    from web.pages.operations import show_operations
    show_operations()
    
elif page == "👥 账号管理":
    from web.pages.accounts import show_accounts
    show_accounts()
    
elif page == "📈 数据分析":
    from web.pages.analytics import show_analytics
    show_analytics()
