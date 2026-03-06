import axios from 'axios';

// Node.js 后端 API (主要负责认证、用户、设置、审查、闲管家代理)
export const nodeApi = axios.create({
  baseURL: import.meta.env.VITE_NODE_API_URL || '/api',
  timeout: 15000,
});

// Python 仪表盘后端 API (主要负责运营数据、自动化控制、商品上架等)
export const pyApi = axios.create({
  baseURL: import.meta.env.VITE_PY_API_URL || '/py',
  timeout: 15000,
});

// 请求拦截器：注入 Token 与多店铺当前账号上下文
const requestInterceptor = (config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  
  const accountId = localStorage.getItem('currentAccountId');
  if (accountId) {
    config.headers['X-Account-Id'] = accountId;
  }
  return config;
};

nodeApi.interceptors.request.use(requestInterceptor);
pyApi.interceptors.request.use(requestInterceptor);

// 响应拦截器：统一处理错误
const responseErrorInterceptor = (error) => {
  const customMessage = error.response?.data?.error || error.response?.data?.msg || error.message;
  // 可以在这里派发全局的未登录事件 (401) 或者交由各组件处理
  return Promise.reject(new Error(customMessage));
};

nodeApi.interceptors.response.use((response) => response, responseErrorInterceptor);
pyApi.interceptors.response.use((response) => response, responseErrorInterceptor);
