import React from 'react';
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Loader2, Wifi, Bot, Cookie, Server, Link2 } from 'lucide-react';
import useHealthCheck from '../hooks/useHealthCheck';

const STATUS_ICON: Record<string, React.ReactNode> = {
  ok:      <CheckCircle className="w-4 h-4 text-green-500" />,
  fail:    <XCircle className="w-4 h-4 text-red-500" />,
  warn:    <AlertTriangle className="w-4 h-4 text-amber-500" />,
  loading: <Loader2 className="w-4 h-4 text-xy-gray-400 animate-spin" />,
};

interface ServiceItem {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const SERVICES: ServiceItem[] = [
  { key: 'python', label: '后端服务', icon: Server },
  { key: 'cookie', label: '闲鱼 Cookie', icon: Cookie },
  { key: 'ai',     label: 'AI 服务',     icon: Bot },
  { key: 'xgj',    label: '闲管家 API',  icon: Link2 },
];

function statusOf(item: { ok?: boolean } | null | undefined): 'ok' | 'fail' | 'loading' {
  if (!item) return 'loading';
  return item.ok ? 'ok' : 'fail';
}

export default function ApiStatusPanel() {
  const { loading, lastChecked, refresh, ...services } = useHealthCheck();

  const allOk   = !loading && SERVICES.every(s => services[s.key as keyof typeof services]?.ok);
  const anyFail = !loading && SERVICES.some(s => !services[s.key as keyof typeof services]?.ok);

  return (
    <div className="xy-card overflow-hidden">
      <div className={`px-5 py-3 border-b border-xy-border flex items-center justify-between ${
        allOk ? 'bg-green-50' : anyFail ? 'bg-red-50' : 'bg-xy-gray-50'
      }`}>
        <div className="flex items-center gap-2">
          <Wifi className={`w-4 h-4 ${allOk ? 'text-green-600' : anyFail ? 'text-red-500' : 'text-xy-gray-400'}`} />
          <span className="text-sm font-semibold text-xy-text-primary">
            服务状态
          </span>
          {allOk && <span className="text-xs text-green-600 bg-green-100 px-2 py-0.5 rounded-full font-medium">全部正常</span>}
          {anyFail && <span className="text-xs text-red-600 bg-red-100 px-2 py-0.5 rounded-full font-medium">存在异常</span>}
        </div>
        <div className="flex items-center gap-3">
          {lastChecked && (
            <span className="text-xs text-xy-text-muted">
              {new Date(lastChecked).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={refresh}
            disabled={loading}
            className="p-1 rounded-md hover:bg-white/70 text-xy-text-muted hover:text-xy-text-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="刷新状态"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="divide-y divide-xy-border">
        {SERVICES.map(({ key, label, icon: Icon }) => {
          const svc = services[key as keyof typeof services];
          const st = loading ? 'loading' : statusOf(svc);
          return (
            <div key={key} className="px-5 py-2.5 flex items-center gap-3 hover:bg-xy-gray-50/50 transition-colors">
              <Icon className="w-4 h-4 text-xy-text-muted flex-shrink-0" />
              <span className="text-sm text-xy-text-primary flex-1">{label}</span>
              <div className="flex items-center gap-2">
                {svc?.latency_ms != null && (
                  <span className="text-xs text-xy-text-muted">{svc.latency_ms}ms</span>
                )}
                {st !== 'ok' && svc?.message && (
                  <span className={`text-xs ${st === 'fail' ? 'text-red-500' : 'text-xy-text-muted'} max-w-[160px] truncate`} title={svc.message}>
                    {svc.message}
                  </span>
                )}
                {STATUS_ICON[st]}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
