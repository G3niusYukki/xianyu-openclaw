import { pyApi } from './index';

// ---------------- 系统与店铺配置 ----------------

// 获取合并后的系统配置
export const getSystemConfig = () => pyApi.get('/api/config');

// 保存系统配置
export const saveSystemConfig = (updates) => pyApi.post('/api/config', updates);

// 获取配置表单 Schema (可选，用于动态渲染表单)
export const getConfigSections = () => pyApi.get('/api/config/sections');
