import { pyApi } from './index';

// ---------------- 仪表盘与配置统计 ----------------

// 获取全系统状态概览 (包含多账号)
export const getSystemStatus = () => pyApi.get('/api/status');

// 获取当前账号的运营漏斗概览
export const getDashboardSummary = () => pyApi.get('/api/summary');

// 获取趋势数据
export const getTrendData = (metric, days = 30) => 
  pyApi.get(`/api/trend?metric=${metric}&days=${days}`);

// 获取热门商品
export const getTopProducts = (limit = 12) => 
  pyApi.get(`/api/top-products?limit=${limit}`);

// 获取最近操作记录
export const getRecentOperations = (limit = 20) => 
  pyApi.get(`/api/recent-operations?limit=${limit}`);

// 手动操作触发 (如重启模块、一键修复)
export const serviceControl = (action) => 
  pyApi.post('/api/service/control', { action });

// 控制单独模块的启停 (target)
export const moduleControl = (action, target) => 
  pyApi.post('/api/module/control', { action, target });
