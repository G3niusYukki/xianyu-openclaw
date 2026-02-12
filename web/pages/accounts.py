"""账号管理页面"""

import streamlit as st
from src.modules.accounts.service import AccountsService
from src.modules.accounts.scheduler import Scheduler

accounts_service = AccountsService()
scheduler = Scheduler()

def show_accounts():
    st.title("👥 账号管理")
    
    # 功能标签页
    tab1, tab2, tab3 = st.tabs(["账号列表", "添加账号", "定时任务"])
    
    with tab1:
        show_account_list()
    
    with tab2:
        show_add_account()
    
    with tab3:
        show_scheduler()

def show_account_list():
    st.subheader("账号列表")
    
    accounts = accounts_service.get_accounts()
    
    if not accounts:
        st.info("暂无账号，请先添加账号")
        return
    
    # 账号卡片
    for acc in accounts:
        health = accounts_service.get_account_health(acc.get('id', ''))
        health_score = health.get('health_score', 0)
        
        # 状态图标
        status_icon = "✅" if acc.get('enabled') else "❌"
        health_emoji = "🟢" if health_score >= 80 else "🟡" if health_score >= 50 else "🔴"
        
        with st.expander(f"{status_icon} {acc.get('name', '未知')} - {health_emoji} 健康度 {health_score}%"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**账号ID**: {acc.get('id', 'N/A')}")
                st.write(f"**优先级**: {acc.get('priority', 0)}")
            
            with col2:
                st.write(f"**总发布**: {health.get('total_published', 0)}次")
                st.write(f"**总错误**: {health.get('total_errors', 0)}次")
            
            with col3:
                st.write(f"**Cookie状态**: {'✅ 有效' if health.get('cookie_valid') else '❌ 无效'}")
            
            st.write("---")
            
            # 操作按钮
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if acc.get('enabled'):
                    if st.button(f"禁用 {acc.get('name')}", key=f"disable_{acc.get('id')}"):
                        accounts_service.disable_account(acc.get('id'))
                        st.rerun()
                else:
                    if st.button(f"启用 {acc.get('name')}", key=f"enable_{acc.get('id')}"):
                        accounts_service.enable_account(acc.get('id'))
                        st.rerun()
            
            with col2:
                if st.button("设置为当前账号", key=f"set_{acc.get('id')}"):
                    accounts_service.set_current_account(acc.get('id'))
                    st.success(f"✅ 已设置为当前账号")
            
            with col3:
                if st.button("刷新Cookie", key=f"refresh_{acc.get('id')}"):
                    st.info("📋 请在浏览器中重新获取Cookie后填入")
                    new_cookie = st.text_area("新Cookie", key=f"new_cookie_{acc.get('id')}", height=100)
                    if st.button("确认更新", key=f"update_{acc.get('id')}"):
                        if new_cookie:
                            accounts_service.refresh_cookie(acc.get('id'), new_cookie)
                            st.success("✅ Cookie已更新")
                            st.rerun()

def show_add_account():
    st.subheader("添加新账号")
    
    with st.form("add_account_form"):
        account_id = st.text_input("账号ID*", placeholder="例如: account_3")
        name = st.text_input("账号名称*", placeholder="例如: 备用账号")
        cookie = st.text_area("Cookie*", placeholder="从浏览器开发者工具中复制Cookie", height=150)
        priority = st.number_input("优先级", min_value=1, max_value=10, value=3, help="数值越小优先级越高")
        
        st.info("💡 如何获取Cookie：\n1. 在浏览器中登录闲鱼\n2. 按F12打开开发者工具\n3. 切换到Network标签\n4. 刷新页面，找到任意请求\n5. 在Request Headers中复制Cookie")
        
        submitted = st.form_submit_button("➕ 添加账号", type="primary")
        
        if submitted:
            if not account_id or not name or not cookie:
                st.error("❌ 请填写所有必填项")
                return
            
            accounts_service.add_account(
                account_id=account_id,
                name=name,
                cookie=cookie,
                priority=priority
            )
            st.success("✅ 账号添加成功！")
            st.rerun()

def show_scheduler():
    st.subheader("定时任务")
    
    st.info("💡 定时任务可以自动化执行日常操作")
    
    # 查看现有任务
    status = scheduler.get_scheduler_status()
    st.write(f"当前总任务数: {status.get('total_tasks', 0)}")
    
    # 创建新任务
    st.write("---")
    st.write("#### 创建新任务")
    
    with st.form("create_task_form"):
        task_name = st.text_input("任务名称", placeholder="例如: 每日擦亮")
        task_type = st.selectbox(
            "任务类型",
            ["polish", "metrics", "health_check", "custom"]
        )
        
        if task_type == "polish":
            st.info("⏰ 定时擦亮商品")
            max_items = st.number_input("擦亮数量", min_value=10, max_value=200, value=50)
        elif task_type == "metrics":
            st.info("📊 定时采集数据")
            metrics_types = st.multiselect(
                "采集类型",
                ["views", "wants", "sales"],
                default=["views", "wants"]
            )
        else:
            st.info("⚙️ 自定义任务")
        
        # Cron表达式生成器
        st.write("#### 执行时间")
        col1, col2, col3 = st.columns(3)
        with col1:
            hour = st.selectbox("小时", list(range(24)), index=9)
        with col2:
            minute = st.selectbox("分钟", list(range(60)), index=0)
        with col3:
            weekday = st.selectbox(
                "重复频率",
                ["每天", "仅工作日", "仅周末", "仅周一"]
            )
        
        # 生成Cron表达式
        if weekday == "每天":
            cron_expr = f"{minute} {hour} * * *"
        elif weekday == "仅工作日":
            cron_expr = f"{minute} {hour} * * 1-5"
        elif weekday == "仅周末":
            cron_expr = f"{minute} {hour} * * 6,0"
        else:
            cron_expr = f"{minute} {hour} * * 1"
        
        st.write(f"Cron表达式: `{cron_expr}`")
        st.caption("Cron格式: 分 时 日 月 周")
        
        if st.form_submit_button("➕ 创建任务"):
            if not task_name:
                st.warning("⚠️ 请输入任务名称")
            else:
                if task_type == "polish":
                    scheduler.create_polish_task(
                        cron_expression=cron_expr,
                        max_items=max_items,
                        name=task_name
                    )
                elif task_type == "metrics":
                    scheduler.create_metrics_task(
                        cron_expression=cron_expr,
                        metrics_types=metrics_types,
                        name=task_name
                    )
                else:
                    scheduler.create_task(
                        task_type="custom",
                        name=task_name,
                        cron_expression=cron_expr,
                        params={}
                    )
                st.success("✅ 任务创建成功！")
                st.rerun()
    
    # 任务列表
    st.write("---")
    st.write("#### 任务列表")
    tasks = scheduler.list_tasks()
    
    if tasks:
        for task in tasks:
            with st.expander(f"{'✅' if task.enabled else '❌'} {task.name}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**类型**: {task.task_type}")
                    st.write(f"**Cron**: `{task.cron_expression}`")
                with col2:
                    st.write(f"**状态**: {'启用' if task.enabled else '禁用'}")
                    st.write(f"**上次执行**: {task.last_run or '未执行'}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if task.enabled:
                        if st.button("禁用", key=f"disable_task_{task.task_id}"):
                            scheduler.update_task(task.task_id, enabled=False)
                            st.rerun()
                    else:
                        if st.button("启用", key=f"enable_task_{task.task_id}"):
                            scheduler.update_task(task.task_id, enabled=True)
                            st.rerun()
                with col2:
                    if st.button("立即执行", key=f"run_task_{task.task_id}"):
                        result = asyncio.run(scheduler.run_task_now(task.task_id))
                        st.info(f"执行结果: {result}")
                    if st.button("删除", key=f"delete_task_{task.task_id}"):
                        scheduler.delete_task(task.task_id)
                        st.rerun()
    else:
        st.info("暂无定时任务")

import asyncio
