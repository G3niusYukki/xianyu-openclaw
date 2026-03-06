import { nodeApi } from './index';

// ---------------- 闲管家 API ----------------
// 通过 Node 代理发送 API 请求
export const proxyXgjApi = (path, payload) => 
  nodeApi.post('/xgj/proxy', { path, payload });

// 便捷封装常用方法:
// 1. 获取商品列表
export const getProducts = (pageNo = 1, pageSize = 20) => 
  proxyXgjApi('/api/open/product/list', { page_no: pageNo, page_size: pageSize });

// 2. 获取订单列表 (根据业务需要)
export const getOrders = (payload) => 
  proxyXgjApi('/api/open/order/list', payload);

// 3. 上下架商品等
export const unpublishProduct = (productId) => 
  proxyXgjApi('/api/open/product/unpublish', { product_id: productId });

export const publishProduct = (productId) => 
  proxyXgjApi('/api/open/product/publish', { product_id: productId });
