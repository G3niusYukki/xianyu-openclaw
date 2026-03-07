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
  'Network Error': {
    msg: '网络连接失败',
    action: '请检查网络连接，确认后端服务已启动（运行 ./start.sh）',
  },
  'ECONNREFUSED': {
    msg: '服务未启动',
    action: '请运行 ./start.sh 启动所有服务',
  },
  'timeout': {
    msg: '请求超时',
    action: '请稍后重试，如果持续超时，请检查后端日志',
  },
};

const STATUS_ERRORS = {
  401: {
    msg: 'Cookie 已过期或无效',
    action: '请前往「店铺管理」页面重新获取 Cookie',
  },
  403: {
    msg: '权限不足',
    action: '请检查「系统配置」中的闲管家 AppKey 和 AppSecret 是否正确',
  },
  404: {
    msg: '请求的资源不存在',
    action: '请检查 API 地址是否正确',
  },
  500: {
    msg: '服务器内部错误',
    action: '请查看后端日志排查问题（日志路径: logs/ 目录）',
  },
  502: {
    msg: '服务暂时不可用',
    action: '后端服务可能正在重启，请稍等几秒后刷新页面',
  },
  503: {
    msg: '服务维护中',
    action: '后端服务正在维护，请稍后重试',
  },
};

const friendlyMessage = (error) => {
  const raw = error.response?.data?.error || error.response?.data?.msg || error.message || '';

  for (const [key, info] of Object.entries(FRIENDLY_ERRORS)) {
    if (raw.includes(key)) return info;
  }

  const status = error.response?.status;
  if (status && STATUS_ERRORS[status]) {
    return STATUS_ERRORS[status];
  }

  return { msg: raw || '未知错误', action: '' };
};

const responseErrorInterceptor = (error) => {
  const userMsg = friendlyMessage(error);
  console.error('[API Error]', error.config?.url, error.message, error.response?.data);
  error.message = userMsg.msg;
  error.action = userMsg.action;
  error.statusCode = error.response?.status;
  return Promise.reject(error);
};

nodeApi.interceptors.response.use((response) => response, responseErrorInterceptor);
pyApi.interceptors.response.use((response) => response, responseErrorInterceptor);
