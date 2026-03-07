import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';

export interface ApiResponse<T = any> {
  ok?: boolean;
  success?: boolean;
  data?: T;
  error?: string;
  error_code?: string;
  error_message?: string;
  config?: Record<string, any>;
}

export const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 15000,
});

/** @deprecated Use `api` instead */
export const nodeApi = api;
/** @deprecated Use `api` instead */
export const pyApi = api;

interface FriendlyError {
  msg: string;
  action: string;
}

const FRIENDLY_ERRORS: Record<string, FriendlyError> = {
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

const STATUS_ERRORS: Record<number, FriendlyError> = {
  401: { msg: 'Cookie 已过期或无效', action: '请前往「店铺管理」页面重新获取 Cookie' },
  403: { msg: '权限不足', action: '请检查「系统配置」中的闲管家 AppKey 和 AppSecret 是否正确' },
  404: { msg: '请求的资源不存在', action: '请检查 API 地址是否正确' },
  500: { msg: '服务器内部错误', action: '请查看后端日志排查问题（日志路径: logs/ 目录）' },
  502: { msg: '服务暂时不可用', action: '后端服务可能正在重启，请稍等几秒后刷新页面' },
  503: { msg: '服务维护中', action: '后端服务正在维护，请稍后重试' },
};

const friendlyMessage = (error: AxiosError): FriendlyError => {
  const raw = (error.response?.data as any)?.error
    || (error.response?.data as any)?.msg
    || error.message
    || '';

  for (const [key, info] of Object.entries(FRIENDLY_ERRORS)) {
    if (raw.includes(key)) return info;
  }

  const status = error.response?.status;
  if (status && STATUS_ERRORS[status]) return STATUS_ERRORS[status];

  return { msg: raw || '未知错误', action: '' };
};

const responseErrorInterceptor = (error: AxiosError) => {
  const userMsg = friendlyMessage(error);
  console.error('[API Error]', error.config?.url, error.message, error.response?.data);
  (error as any).message = userMsg.msg;
  (error as any).action = userMsg.action;
  (error as any).statusCode = error.response?.status;
  return Promise.reject(error);
};

api.interceptors.response.use((response: AxiosResponse) => response, responseErrorInterceptor);
