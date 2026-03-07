import { api } from './index';
import type { AxiosResponse } from 'axios';

export const proxyXgjApi = (apiPath: string, payload?: Record<string, any>): Promise<AxiosResponse> =>
  api.post('/xgj/proxy', { apiPath, payload });

export const getProducts = (pageNo = 1, pageSize = 20): Promise<AxiosResponse> =>
  proxyXgjApi('/api/open/product/list', { page_no: pageNo, page_size: pageSize });

export const getOrders = (payload: Record<string, any>): Promise<AxiosResponse> =>
  proxyXgjApi('/api/open/order/list', payload);

export const unpublishProduct = (productId: string): Promise<AxiosResponse> =>
  proxyXgjApi('/api/open/product/unpublish', { product_id: productId });

export const publishProduct = (productId: string): Promise<AxiosResponse> =>
  proxyXgjApi('/api/open/product/publish', { product_id: productId });
