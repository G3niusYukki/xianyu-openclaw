import { pyApi } from './index';

// ---------------- 自动上架 ----------------
// 获取可用模板
export const getTemplates = () => pyApi.get('/api/listing/templates');

// 上架内容生成及预览
export const previewListing = (data) => pyApi.post('/api/listing/preview', data);

// 确认发布商品
export const publishListing = (data) => pyApi.post('/api/listing/publish', data);
