"""仪表盘页面"""

import streamlit as st
import asyncio
from datetime import datetime
import pandas as pd

from src.modules.analytics.service import AnalyticsService
from src.modules.accounts.service import AccountsService
from src.modules.accounts.monitor import Monitor

analytics_service = AnalyticsService()
accounts_service = AccountsService()
monitor = Monitor()

def show_dashboard():
    st.title("📊 运营仪表盘")
    
    # 检查快捷操作
    if st.session_state.get('quick_action') == 'polish_all':
        with st.spinner('正在执行批量擦亮...'):
            result = asyncio.run(execute_polish_all())
            if result:
                st.success('✅ 批量擦亮完成!')
        st.session_state['quick_action'] = None
    
    if st.session_state.get('quick_action') == 'daily_report':
        with st.spinner('正在生成日报...'):
            report = asyncio.run(analytics_service.get_daily_report())
            st.json(report)
        st.session_state['quick_action'] = None
    
    # 获取数据
    stats = asyncio.run(analytics_service.get_dashboard_stats())
    accounts = accounts_service.get_accounts()
    alerts = monitor.get_active_alerts()
    
    # 关键指标卡片
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="在售商品",
            value=f"{stats.get('active_products', 0)}个",
            delta=f"+{stats.get('new_listings_today', 0)}今日新增"
        )
    
    with col2:
        st.metric(
            label="总浏览量",
            value=f"{stats.get('total_views', 0):,}",
            delta=f"+{stats.get('views_today', 0)}今日"
        )
    
    with col3:
        st.metric(
            label="总想要数",
            value=f"{stats.get('total_wants', 0):,}",
            delta=f"+{stats.get('wants_today', 0)}今日"
        )
    
    with col4:
        st.metric(
            label="账号数量",
            value=f"{len(accounts)}个",
            delta=f"{sum(1 for a in accounts if a.get('enabled'))}个启用"
        )
    
    st.markdown("---")
    
    # 图表区域
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 浏览量趋势（近7天）")
        try:
            trends = asyncio.run(analytics_service.get_trend_data("views", days=7))
            if trends:
                df = pd.DataFrame(trends)
                st.line_chart(df.set_index('date')['views'])
        except Exception as e:
            st.warning(f"暂无趋势数据: {e}")
    
    with col2:
        st.subheader("👥 账号状态")
        if accounts:
            account_data = []
            for acc in accounts:
                health = accounts_service.get_account_health(acc.get('id', ''))
                account_data.append({
                    '账号': acc.get('name', '未知'),
                    '状态': '✅ 启用' if acc.get('enabled') else '❌ 禁用',
                    '健康度': f"{health.get('health_score', 0)}%"
                })
            st.dataframe(pd.DataFrame(account_data), use_container_width=True)
        else:
            st.info("暂无账号数据")
    
    st.markdown("---")
    
    # 最新告警
    st.subheader("🚨 最新告警")
    if alerts:
        for alert in alerts[:5]:
            level_emoji = {
                'info': 'ℹ️',
                'warning': '⚠️',
                'error': '❌',
                'critical': '🔴'
            }.get(alert.level, '📌')
            st.info(f"{level_emoji} **{alert.title}**\n\n{alert.message}")
    else:
        st.success("✅ 没有活跃告警")
    
    st.markdown("---")
    
    # 快速统计
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"今日发布: {stats.get('new_listings_today', 0)}个")
    with col2:
        st.info(f"今日擦亮: {stats.get('polished_today', 0)}次")
    with col3:
        st.info(f"总营收: ¥{stats.get('total_revenue', 0):,.2f}")

async def execute_polish_all():
    from src.modules.operations.service import OperationsService
    service = OperationsService()
    result = await service.batch_polish(max_items=50)
    return result.get('success', False)
