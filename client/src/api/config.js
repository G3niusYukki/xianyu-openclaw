import { nodeApi } from './index';

// ---------------- 系统与店铺配置 ----------------

// 获取合并后的系统配置
export const getSystemConfig = () => nodeApi.get('/config');

// 保存系统配置
export const saveSystemConfig = (updates) => nodeApi.put('/config', updates);

// 获取配置表单 Schema (可选，用于动态渲染表单)
export const getConfigSections = () => nodeApi.get('/config/sections');