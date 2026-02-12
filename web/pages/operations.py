"""运营管理页面"""

import streamlit as st
import asyncio
import pandas as pd

from src.modules.operations.service import OperationsService

operations_service = OperationsService()

def show_operations():
    st.title("⚙️ 运营管理")
    
    # 功能选择
    operation = st.radio(
        "选择操作",
        ["批量擦亮", "价格调整", "商品下架", "重新上架"],
        horizontal=True
    )
    
    if operation == "批量擦亮":
        show_polish()
    elif operation == "价格调整":
        show_price_update()
    elif operation == "商品下架":
        show_delist()
    elif operation == "重新上架":
        show_relist()

def show_polish():
    st.subheader("批量擦亮")
    
    st.info("💡 擦亮可以提高商品在搜索结果中的排名，建议每天执行一次")
    
    col1, col2 = st.columns(2)
    with col1:
        max_items = st.slider(
            "擦亮商品数量",
            min_value=10,
            max_value=200,
            value=50,
            step=10
        )
    with col2:
        delay_range = st.slider(
            "操作间隔（秒）",
            min_value=1,
            max_value=10,
            value=(3, 6)
        )
    
    if st.button("🔄 开始批量擦亮", type="primary", use_container_width=True):
        with st.spinner('正在批量擦亮...'):
            result = asyncio.run(operations_service.batch_polish(max_items=max_items))
        
        st.subheader("擦亮结果")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("成功", f"{result.get('success', 0)}个")
        with col2:
            st.metric("失败", f"{result.get('failed', 0)}个")
        with col3:
            st.metric("总计", f"{result.get('total', 0)}个")
        
        if result.get('failed', 0) > 0:
            with st.expander("查看失败详情"):
                st.write(result.get('errors', []))

def show_price_update():
    st.subheader("价格调整")
    
    st.info("💡 支持单个或批量调整商品价格")
    
    update_mode = st.radio(
        "调整方式",
        ["单个调整", "批量调整", "打折调整"]
    )
    
    if update_mode == "单个调整":
        product_id = st.text_input("商品ID", placeholder="例如: item_123456")
        new_price = st.number_input("新价格 (元)", min_value=0.0, step=0.01)
        original_price = st.number_input("原价 (元，可选)", min_value=0.0, step=0.01, value=0.0)
        
        if st.button("💰 更新价格"):
            if product_id and new_price > 0:
                with st.spinner('正在更新价格...'):
                    result = asyncio.run(operations_service.update_price(
                        product_id=product_id,
                        new_price=new_price,
                        original_price=original_price if original_price > 0 else None
                    ))
                
                if result.get('success'):
                    st.success(f"✅ 价格更新成功！")
                else:
                    st.error(f"❌ 价格更新失败")
            else:
                st.warning("⚠️ 请填写商品ID和新价格")
    
    elif update_mode == "批量调整":
        st.write("#### 上传价格调整表")
        st.info("💡 支持Excel/CSV格式，列：商品ID, 新价格, 原价（可选）")
        
        upload_file = st.file_uploader(
            "上传文件",
            type=['xlsx', 'xls', 'csv']
        )
        
        if upload_file:
            df = pd.read_excel(upload_file) if upload_file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(upload_file)
            st.dataframe(df)
            
            if st.button("🚀 开始批量调整"):
                with st.spinner('正在批量调整价格...'):
                    updates = []
                    for _, row in df.iterrows():
                        updates.append({
                            "product_id": row.get('商品ID', row.get('product_id', '')),
                            "new_price": float(row.get('新价格', row.get('new_price', 0))),
                            "original_price": float(row.get('原价', row.get('original_price', 0))) if row.get('原价', row.get('original_price', 0)) > 0 else None
                        })
                    
                    results = asyncio.run(operations_service.batch_update_price(updates))
                    success_count = sum(1 for r in results if r.get('success'))
                    
                    st.success(f"✅ 批量调整完成！成功 {success_count}/{len(updates)}")
    
    elif update_mode == "打折调整":
        discount_rate = st.slider(
            "折扣率",
            min_value=50,
            max_value=99,
            value=90
        )
        st.write(f"所有商品将以 {discount_rate}% 的价格出售")
        
        if st.button("🏷️ 应用折扣"):
            st.info("⚠️ 此功能将调整所有商品价格，请谨慎操作！")
            if st.button("确认执行", type="primary"):
                st.success("✅ 折扣应用完成（示例）")

def show_delist():
    st.subheader("商品下架")
    
    st.warning("⚠️ 下架后的商品需要重新上架才能出售")
    
    product_id = st.text_input("商品ID", placeholder="例如: item_123456")
    reason = st.selectbox(
        "下架原因",
        ["已售出", "不卖了", "价格调整", "其他"]
    )
    other_reason = st.text_input("其他原因（可选）") if reason == "其他" else ""
    
    final_reason = other_reason if reason == "其他" else reason
    
    if st.button("📦 确认下架", type="primary"):
        if product_id:
            with st.spinner('正在下架...'):
                result = asyncio.run(operations_service.delist(
                    product_id=product_id,
                    reason=final_reason
                ))
            
            if result.get('success'):
                st.success(f"✅ 商品已下架")
            else:
                st.error(f"❌ 下架失败")
        else:
            st.warning("⚠️ 请填写商品ID")

def show_relist():
    st.subheader("重新上架")
    
    product_id = st.text_input("商品ID", placeholder="例如: item_123456")
    
    if st.button("🔄 确认上架", type="primary"):
        if product_id:
            with st.spinner('正在上架...'):
                result = asyncio.run(operations_service.relist(product_id))
            
            if result.get('success'):
                st.success(f"✅ 商品已重新上架")
            else:
                st.error(f"❌ 上架失败")
        else:
            st.warning("⚠️ 请填写商品ID")
