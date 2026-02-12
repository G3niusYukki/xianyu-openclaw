"""商品发布页面"""

import streamlit as st
from datetime import datetime
import asyncio

from src.modules.listing.service import ListingService
from src.modules.listing.models import Listing
from src.modules.content.service import ContentService
from src.modules.media.service import MediaService

listing_service = ListingService()
content_service = ContentService()
media_service = MediaService()

def show_publish():
    st.title("🛒 商品发布")
    
    # 发布模式选择
    publish_mode = st.radio(
        "发布模式",
        ["单个发布", "批量发布"],
        horizontal=True
    )
    
    if publish_mode == "单个发布":
        show_single_publish()
    else:
        show_batch_publish()

def show_single_publish():
    st.subheader("单个商品发布")
    
    with st.form("publish_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("基本信息")
            name = st.text_input("商品名称*", placeholder="例如：iPhone 15 Pro 256GB")
            category = st.selectbox(
                "商品分类",
                ["数码手机", "电脑办公", "家居日用", "服饰鞋包", "美妆护肤", "运动户外", "其他"]
            )
            price = st.number_input("售价 (元)*", min_value=0.0, step=0.01, value=0.0)
            original_price = st.number_input("原价 (元)", min_value=0.0, step=0.01, value=0.0)
        
        with col2:
            st.subheader("商品详情")
            condition = st.selectbox(
                "成色",
                ["全新", "99新", "95新", "9成新", "8成新", "使用痕迹明显"]
            )
            reason = st.text_area(
                "出售原因",
                placeholder="例如：换新手机，闲置处理",
                height=80
            )
            
            features = st.text_input(
                "商品特性（用逗号分隔）",
                placeholder="例如：256GB, 原色钛金属, 国行, 无拆修"
            )
            features_list = [f.strip() for f in features.split(',') if f.strip()]
        
        st.subheader("图片上传")
        images = st.file_uploader(
            "上传商品图片",
            accept_multiple_files=True,
            type=['jpg', 'jpeg', 'png', 'webp'],
            help="最多上传9张图片，建议尺寸1000x1000"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("AI智能生成")
            use_ai_title = st.checkbox("AI生成标题", value=True)
            use_ai_desc = st.checkbox("AI生成描述", value=True)
        
        with col2:
            st.subheader("其他选项")
            enable_delivery = st.checkbox("支持邮寄", value=True)
            enable_face = st.checkbox("支持面交", value=False)
        
        submitted = st.form_submit_button("🚀 立即发布", type="primary", use_container_width=True)
        
        if submitted:
            if not name or price <= 0:
                st.error("❌ 请填写商品名称和售价")
                return
            
            if not images:
                st.error("❌ 请至少上传一张图片")
                return
            
            with st.spinner('正在处理并发布...'):
                try:
                    # 生成内容
                    if use_ai_title:
                        title = content_service.generate_title(
                            product_name=name,
                            features=features_list,
                            category=category
                        )
                    else:
                        title = name
                    
                    if use_ai_desc:
                        description = content_service.generate_description(
                            product_name=name,
                            condition=condition,
                            reason=reason,
                            tags=features_list
                        )
                    else:
                        description = reason or f"{condition}，{reason}"
                    
                    # 处理图片
                    processed_images = []
                    if images:
                        import tempfile
                        import os
                        temp_dir = tempfile.mkdtemp()
                        for img_file in images:
                            img_path = os.path.join(temp_dir, img_file.name)
                            with open(img_path, 'wb') as f:
                                f.write(img_file.getbuffer())
                            processed_images.append(img_path)
                    
                    # 创建商品
                    listing = Listing(
                        title=title,
                        description=description,
                        price=price,
                        original_price=original_price if original_price > 0 else None,
                        category=category,
                        images=processed_images,
                        tags=features_list,
                        delivery_available=enable_delivery,
                        face_trade_available=enable_face
                    )
                    
                    # 发布
                    result = asyncio.run(listing_service.create_listing(listing))
                    
                    if result.success:
                        st.success(f"✅ 发布成功！")
                        st.info(f"商品链接: {result.product_url}")
                    else:
                        st.error(f"❌ 发布失败: {result.error_message}")
                    
                except Exception as e:
                    st.error(f"❌ 发布出错: {str(e)}")

def show_batch_publish():
    st.subheader("批量商品发布")
    
    st.info("💡 批量发布功能，支持从Excel/CSV导入商品信息，自动批量发布")
    
    upload_file = st.file_uploader(
        "上传商品信息文件",
        type=['xlsx', 'xls', 'csv'],
        help="支持Excel和CSV格式"
    )
    
    if upload_file:
        st.write("文件预览:")
        df = pd.read_excel(upload_file) if upload_file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(upload_file)
        st.dataframe(df.head(10))
        
        st.write("文件信息:")
        st.write(f"- 总商品数: {len(df)}")
        st.write(f"- 列名: {', '.join(df.columns)}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            delay_min = st.number_input("最小间隔（秒）", min_value=1, value=5)
        with col2:
            delay_max = st.number_input("最大间隔（秒）", min_value=1, value=10)
        with col3:
            start_index = st.number_input("起始行", min_value=0, value=0, max_value=len(df)-1)
        
        if st.button("🚀 开始批量发布", type="primary"):
            st.warning("⚠️ 批量发布功能需要完整的Excel数据文件，请确保格式正确")
            st.info("示例格式：商品名称 | 分类 | 价格 | 成色 | 出售原因 | 图片路径1 | 图片路径2 | ...")

import pandas as pd
