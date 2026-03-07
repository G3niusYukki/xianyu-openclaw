import { nodeApi } from './index';

export const proxyXgjApi = (apiPath, payload) => 
  nodeApi.post('/xgj/proxy', { apiPath, payload });

export const getProducts = (pageNo = 1, pageSize = 20) => 
  proxyXgjApi('/api/open/product/list', { page_no: pageNo, page_size: pageSize });

export const getOrders = (payload) => 
  proxyXgjApi('/api/open/order/list', payload);

export const unpublishProduct = (productId) => 
  proxyXgjApi('/api/open/product/unpublish', { product_id: productId });

export const publishProduct = (productId) => 
  proxyXgjApi('/api/open/product/publish', { product_id: productId });
