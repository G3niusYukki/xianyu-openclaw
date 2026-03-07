import { api } from './index';
import type { AxiosResponse } from 'axios';
import type { ApiResponse } from './index';

export interface DashboardSummary {
  total_operations: number;
  today_operations: number;
  active_products: number;
  sold_products: number;
  total_views: number;
  total_wants: number;
  total_sales: number;
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface TopProduct {
  product_id: string;
  title: string;
  status: string;
  views: number;
  wants: number;
  sales: number;
}

export const getSystemStatus = (): Promise<AxiosResponse> => api.get('/status');

export const getDashboardSummary = (): Promise<AxiosResponse<ApiResponse<DashboardSummary>>> =>
  api.get('/summary');

export const getTrendData = (metric: string, days = 30): Promise<AxiosResponse<ApiResponse<TrendPoint[]>>> =>
  api.get(`/trend?metric=${metric}&days=${days}`);

export const getTopProducts = (limit = 12): Promise<AxiosResponse<ApiResponse<TopProduct[]>>> =>
  api.get(`/top-products?limit=${limit}`);

export const getRecentOperations = (limit = 20): Promise<AxiosResponse> =>
  api.get(`/recent-operations?limit=${limit}`);

export const serviceControl = (action: string): Promise<AxiosResponse> =>
  api.post('/service/control', { action });

export const moduleControl = (action: string, target: string): Promise<AxiosResponse> =>
  api.post('/module/control', { action, target });
