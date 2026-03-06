import { pyApi } from './index';

export const getProducts = (pageNo = 1, pageSize = 20, search = '') =>
  pyApi.get('/api/xgj/products', { params: { page_no: pageNo, page_size: pageSize, search } });

export const getOrders = ({ page_no = 1, page_size = 20, order_status, search = '' } = {}) =>
  pyApi.get('/api/xgj/orders', { params: { page_no, page_size, order_status, search } });

export const unpublishProduct = (productId) =>
  pyApi.post('/api/xgj/product/unpublish', { product_id: productId });

export const publishProduct = (productId) =>
  pyApi.post('/api/xgj/product/publish', { product_id: productId });

export const modifyOrderPrice = (orderId, totalFee) =>
  pyApi.post('/api/xgj/order/modify-price', { order_id: orderId, total_fee: totalFee });

export const deliverOrder = (orderId) =>
  pyApi.post('/api/xgj/order/deliver', { order_id: orderId });
