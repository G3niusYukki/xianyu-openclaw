import axios from 'axios';

export const nodeApi = axios.create({
  baseURL: import.meta.env.VITE_NODE_API_URL || '/api',
  timeout: 15000,
});

export const pyApi = axios.create({
  baseURL: import.meta.env.VITE_PY_API_URL || '/py',
  timeout: 15000,
});

const FRIENDLY_ERRORS = {
  'Network Error': '网络连接失败，请检查网络',
  'ECONNREFUSED': '服务未启动或无法连接',
  'timeout': '请求超时，请稍后重试',
};

const friendlyMessage = (error) => {
  const raw = error.response?.data?.error || error.response?.data?.msg || error.message || '';
  for (const [key, msg] of Object.entries(FRIENDLY_ERRORS)) {
    if (raw.includes(key)) return msg;
  }
  if (error.response?.status === 500) return '服务器内部错误';
  if (error.response?.status === 502) return '服务暂时不可用';
  if (error.response?.status === 404) return '请求的资源不存在';
  return raw;
};

const responseErrorInterceptor = (error) => {
  const userMsg = friendlyMessage(error);
  console.error('[API Error]', error.config?.url, error.message, error.response?.data);
  error.message = userMsg;
  error.statusCode = error.response?.status;
  return Promise.reject(error);
};

nodeApi.interceptors.response.use((response) => response, responseErrorInterceptor);
pyApi.interceptors.response.use((response) => response, responseErrorInterceptor);
