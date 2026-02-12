"""数据分析页面"""

import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime, timedelta

from src.modules.analytics.service import AnalyticsService
from src.modules.analytics.report_generator import ReportGenerator
from src.modules.analytics.visualization import DataVisualizer

analytics_service = AnalyticsService()
report_generator = ReportGenerator()
visualizer = DataVisualizer()

def show_analytics():
    st.title("📈 数据分析")
    
    # 功能选择
    tab1, tab2, tab3, tab4 = st.tabs(["运营报表", "趋势分析", "商品分析", "数据导出"])
    
    with tab1:
        show_reports()
    
    with tab2:
        show_trends()
    
    with tab3:
        show_product_analysis()
    
    with tab4:
        show_data_export()

def show_reports():
    st.subheader("运营报表")
    
    report_type = st.radio(
        "报表类型",
        ["日报", "周报", "月报"],
        horizontal=True
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if report_type == "月报":
            year = st.number_input("年份", min_value=2023, max_value=2030, value=datetime.now().year)
            month = st.selectbox("月份", list(range(1, 13)), index=datetime.now().month - 1)
        else:
            st.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d')}")
    
    with col2:
        if st.button("📊 生成报表", type="primary"):
            with st.spinner('正在生成报表...'):
                if report_type == "日报":
                    report = asyncio.run(analytics_service.get_daily_report())
                elif report_type == "周报":
                    report = asyncio.run(report_generator.generate_weekly_report())
                else:
                    report = asyncio.run(report_generator.generate_monthly_report(year=year, month=month))
                
                display_report(report, report_type)

def display_report(report, report_type):
    st.subheader(f"{report_type}概览")
    
    if report_type == "日报":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("新增商品", f"{report.get('new_listings', 0)}个")
        with col2:
            st.metric("浏览量", f"{report.get('total_views', 0):,}")
        with col3:
            st.metric("想要数", f"{report.get('total_wants', 0):,}")
        with col4:
            st.metric("成交额", f"¥{report.get('total_revenue', 0):,.2f}")
        
        st.write("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("擦亮次数", f"{report.get('polished_count', 0)}次")
        with col2:
            st.metric("价格调整", f"{report.get('price_updates', 0)}次")
    
    elif report_type == "周报":
        summary = report.get('summary', {})
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("周新增", f"{summary.get('new_listings', 0)}个")
        with col2:
            st.metric("周浏览", f"{summary.get('total_views', 0):,}")
        with col3:
            st.metric("周成交", f"¥{summary.get('total_revenue', 0):,.2f}")
        with col4:
            st.metric("环比增长", f"{summary.get('growth_rate', 0):.1f}%")
    
    elif report_type == "月报":
        summary = report.get('summary', {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("月新增", f"{summary.get('new_listings', 0)}个")
        with col2:
            st.metric("月营收", f"¥{summary.get('total_revenue', 0):,.2f}")
        with col3:
            st.metric("月浏览", f"{summary.get('total_views', 0):,}")
    
    with st.expander("查看详细数据"):
        st.json(report)

def show_trends():
    st.subheader("趋势分析")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        metric_type = st.selectbox(
            "指标类型",
            ["views", "wants", "sales", "revenue"]
        )
    with col2:
        days = st.number_input("时间范围（天）", min_value=7, max_value=90, value=30)
    with col3:
        st.write("数据说明")
        st.caption("- views: 浏览量")
        st.caption("- wants: 想要数")
        st.caption("- sales: 成交数")
        st.caption("- revenue: 营收")
    
    if st.button("📈 查看趋势", type="primary"):
        with st.spinner('正在获取趋势数据...'):
            trends = asyncio.run(analytics_service.get_trend_data(metric_type, days=days))
        
        if trends:
            df = pd.DataFrame(trends)
            
            metric_name = {
                'views': '浏览量',
                'wants': '想要数',
                'sales': '成交数',
                'revenue': '营收'
            }.get(metric_type, metric_type)
            
            st.write(f"#### {metric_name}趋势（近{days}天）")
            
            # 图表
            st.line_chart(df.set_index('date')[metric_type])
            
            # 数据表格
            st.write("数据详情:")
            st.dataframe(df, use_container_width=True)
            
            # 统计信息
            st.write("---")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("总计", f"{df[metric_type].sum():,.0f}")
            with col2:
                st.metric("平均", f"{df[metric_type].mean():,.2f}")
            with col3:
                st.metric("最大", f"{df[metric_type].max():,.0f}")
            with col4:
                st.metric("最小", f"{df[metric_type].min():,.0f}")
        else:
            st.warning("暂无趋势数据")

def show_product_analysis():
    st.subheader("商品分析")
    
    st.info("💡 分析单个商品的表现数据")
    
    product_id = st.text_input("商品ID", placeholder="例如: item_123456")
    days = st.number_input("分析周期（天）", min_value=7, max_value=90, value=30)
    
    if product_id and st.button("🔍 分析商品", type="primary"):
        with st.spinner('正在分析...'):
            try:
                report = asyncio.run(report_generator.generate_product_report(product_id, days=days))
                
                st.write("---")
                st.write("#### 商品概况")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("总浏览", f"{report.get('total_views', 0):,}")
                with col2:
                    st.metric("总想要", f"{report.get('total_wants', 0)}")
                with col3:
                    st.metric("转化率", f"{report.get('conversion_rate', 0):.2f}%")
                
                st.write("---")
                st.write("#### 详细数据")
                if 'daily_data' in report:
                    df = pd.DataFrame(report['daily_data'])
                    st.dataframe(df, use_container_width=True)
                
                with st.expander("查看完整报告"):
                    st.json(report)
            
            except Exception as e:
                st.error(f"分析失败: {str(e)}")

def show_data_export():
    st.subheader("数据导出")
    
    st.info("💡 将运营数据导出为Excel或CSV文件")
    
    export_type = st.selectbox(
        "导出类型",
        ["商品数据", "操作日志", "账号统计", "趋势数据"]
    )
    
    format_type = st.selectbox(
        "文件格式",
        ["CSV", "Excel", "JSON"]
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if export_type in ["趋势数据", "账号统计"]:
            days = st.number_input("时间范围（天）", min_value=1, max_value=365, value=30)
    
    with col2:
        pass
    
    if st.button("📥 导出数据", type="primary"):
        with st.spinner('正在准备数据...'):
            try:
                filepath = asyncio.run(analytics_service.export_data(
                    data_type="products" if export_type == "商品数据" else 
                            "logs" if export_type == "操作日志" else 
                            "accounts" if export_type == "账号统计" else "trends",
                    format=format_type.lower()
                ))
                
                st.success(f"✅ 数据已导出!")
                st.info(f"文件位置: `{filepath}`")
                
                # 下载按钮（需要实现文件下载功能）
                with open(filepath, 'rb') as f:
                    st.download_button(
                        label="下载文件",
                        data=f,
                        file_name=filepath.split('/')[-1],
                        mime="application/octet-stream"
                    )
            
            except Exception as e:
                st.error(f"导出失败: {str(e)}")
