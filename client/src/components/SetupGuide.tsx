import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/index';
import { CheckCircle, Circle, ArrowRight, X, Zap, Cookie, Settings, Bot, Play, ChevronRight, RotateCcw, Info, XCircle } from 'lucide-react';

const DISMISS_KEY = 'xianyu_setup_guide_dismissed';

interface ChecksState {
  nodeBackend: boolean | null;
  pythonBackend: boolean | null;
  xgjConfigured: boolean | null;
  aiConfigured: boolean | null;
  cookieSet: boolean | null;
}

interface StepItem {
  key: string;
  label: string;
  desc: string;
  done: boolean;
  action: string | null;
  actionLabel: string | null;
  icon: React.ComponentType<{ className?: string }> | null;
  hint: string;
  validated?: boolean;
}

export default function SetupGuide() {
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === '1');
  const [checks, setChecks] = useState<ChecksState>({
    nodeBackend: null,
    pythonBackend: null,
    xgjConfigured: null,
    aiConfigured: null,
    cookieSet: null,
  });
  const [details, setDetails] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (dismissed) return;
    runChecks();
  }, [dismissed]);

  const runChecks = async () => {
    setLoading(true);
    const result: ChecksState = {
      nodeBackend: false,
      pythonBackend: false,
      xgjConfigured: false,
      aiConfigured: false,
      cookieSet: false,
    };
    const det: Record<string, string> = {};

    try {
      const res = await api.get('/config');
      result.nodeBackend = true;
      result.pythonBackend = true;
      const cfg = res.data?.config || {};
      const xgj = cfg.xianguanjia || {};
      result.xgjConfigured = !!(xgj.app_key && !String(xgj.app_key).includes('****') && xgj.app_secret && !String(xgj.app_secret).includes('****'));
      const ai = cfg.ai || {};
      result.aiConfigured = !!(ai.api_key && !String(ai.api_key).includes('****'));
    } catch { /* backend unavailable */ }

    try {
      const res = await api.get('/status');
      result.pythonBackend = true;
      const cookieHealth = res.data?.cookie_health;
      result.cookieSet = !!(cookieHealth && cookieHealth.score > 0);
      if (cookieHealth) det.cookie = cookieHealth.message;
    } catch { /* backend unavailable */ }

    try {
      const healthRes = await api.get('/health/check');
      const d = healthRes.data;
      if (d.xgj) {
        det.xgj = d.xgj.ok ? `连通 (${d.xgj.latency_ms || 0}ms)` : d.xgj.message;
        if (result.xgjConfigured && !d.xgj.ok) result.xgjConfigured = false;
      }
      if (d.ai) {
        det.ai = d.ai.ok ? `连通 (${d.ai.latency_ms || 0}ms)` : d.ai.message;
        if (result.aiConfigured && !d.ai.ok) result.aiConfigured = false;
      }
      if (d.cookie && !result.cookieSet) {
        det.cookie = d.cookie.message;
      }
    } catch { /* health check failed */ }

    setChecks(result);
    setDetails(det);
    setLoading(false);
  };

  const handleDismiss = () => {
    localStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  };

  if (dismissed) return null;

  const allDone = checks.nodeBackend && checks.pythonBackend && checks.xgjConfigured && checks.aiConfigured && checks.cookieSet;

  if (loading) {
    return (
      <div className="xy-card mb-8 p-6 animate-pulse">
        <div className="h-8 bg-xy-gray-100 rounded w-1/3 mb-6"></div>
        <div className="space-y-3">
          <div className="h-16 bg-xy-gray-50 rounded-xl"></div>
          <div className="h-16 bg-xy-gray-50 rounded-xl"></div>
          <div className="h-16 bg-xy-gray-50 rounded-xl"></div>
        </div>
      </div>
    );
  }
  if (allDone) return null;

  const steps: StepItem[] = [
    {
      key: 'cookieSet',
      label: '获取闲鱼 Cookie',
      desc: '系统需要 Cookie 来代替你操作闲鱼平台',
      done: checks.cookieSet,
      action: '/accounts',
      actionLabel: '一键获取',
      icon: Cookie,
      hint: '点击"一键获取"可从浏览器自动读取，也支持手动粘贴',
    },
    {
      key: 'xgjConfigured',
      label: '配置闲管家 API',
      desc: '连接闲管家开放平台，实现消息同步和订单管理',
      done: checks.xgjConfigured,
      action: '/config',
      actionLabel: '去配置',
      icon: Settings,
      hint: details.xgj || '前往闲管家开放平台注册应用，获取 AppKey 和 AppSecret',
      validated: !!details.xgj,
    },
    {
      key: 'aiConfigured',
      label: '配置 AI 服务',
      desc: '启用智能自动回复、意图识别和内容生成',
      done: checks.aiConfigured,
      action: '/config',
      actionLabel: '去配置',
      icon: Bot,
      hint: details.ai || '支持 DeepSeek、通义千问等 OpenAI 兼容 API，填入 API Key 即可',
      validated: !!details.ai,
    },
    {
      key: 'nodeBackend',
      label: 'Node.js 后端',
      desc: '配置管理和闲管家 API 代理',
      done: checks.nodeBackend,
      action: null,
      actionLabel: null,
      icon: null,
      hint: '运行 ./start.sh 自动启动',
    },
    {
      key: 'pythonBackend',
      label: 'Python 后端',
      desc: '自动化引擎和消息处理',
      done: checks.pythonBackend,
      action: null,
      actionLabel: null,
      icon: null,
      hint: '运行 ./start.sh 自动启动',
    },
  ];

  const completedCount = steps.filter(s => s.done).length;

  const WORKFLOW_STEPS = [
    { label: '获取 Cookie', icon: '1' },
    { label: '配置闲管家', icon: '2' },
    { label: '配置 AI', icon: '3' },
    { label: '开始运行', icon: '4' },
  ];

  return (
    <div className="xy-card mb-8 overflow-hidden border-2 border-xy-brand-200">
      <div className="px-6 py-4 bg-gradient-to-r from-xy-brand-50 to-orange-50 border-b border-xy-brand-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-xy-brand-500 text-white p-2 rounded-xl">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h2 className="font-bold text-xy-text-primary">快速上手指南</h2>
            <p className="text-sm text-xy-text-secondary">按顺序完成以下配置即可开始自动化运营 ({completedCount}/{steps.length})</p>
          </div>
        </div>
        <button onClick={handleDismiss} className="text-xy-text-muted hover:text-xy-text-primary p-1" aria-label="关闭引导">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="px-6 py-4 bg-xy-gray-50 border-b border-xy-border">
        <div className="flex items-center justify-center gap-0">
          {WORKFLOW_STEPS.map((ws, idx) => (
            <React.Fragment key={idx}>
              <div className="flex items-center gap-2">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold ${
                  idx < completedCount ? 'bg-green-500 text-white' : idx === completedCount ? 'bg-xy-brand-500 text-white' : 'bg-xy-gray-200 text-xy-gray-500'
                }`}>
                  {idx < completedCount ? '\u2713' : ws.icon}
                </div>
                <span className={`text-sm font-medium hidden sm:inline ${
                  idx <= completedCount ? 'text-xy-text-primary' : 'text-xy-text-muted'
                }`}>{ws.label}</span>
              </div>
              {idx < WORKFLOW_STEPS.length - 1 && (
                <ChevronRight className={`w-4 h-4 mx-2 sm:mx-4 shrink-0 ${idx < completedCount ? 'text-green-400' : 'text-xy-gray-300'}`} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="p-6">
        <div className="space-y-3">
          {steps.map((step) => (
            <div
              key={step.key}
              className={`flex items-center gap-4 p-4 rounded-xl border transition-colors ${
                step.done
                  ? 'bg-green-50 border-green-200'
                  : 'bg-white border-xy-border hover:border-xy-brand-300'
              }`}
            >
              {step.done ? (
                <CheckCircle className="w-6 h-6 text-green-500 flex-shrink-0" />
              ) : (
                <Circle className="w-6 h-6 text-xy-gray-300 flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className={`font-medium ${step.done ? 'text-green-700' : 'text-xy-text-primary'}`}>{step.label}</p>
                <p className="text-sm text-xy-text-secondary">{step.desc}</p>
                {!step.done && step.hint && (
                  <p className="text-xs text-xy-text-muted mt-1 flex items-start gap-1">
                    <Info className="w-3 h-3 mt-0.5 shrink-0" />
                    {step.hint}
                  </p>
                )}
              </div>
              {!step.done && step.action && (
                <Link
                  to={step.action}
                  className="flex items-center gap-1 text-sm font-medium text-xy-brand-500 hover:text-xy-brand-600 flex-shrink-0 bg-xy-brand-50 px-3 py-1.5 rounded-lg hover:bg-xy-brand-100 transition-colors"
                >
                  {step.actionLabel || '去配置'} <ArrowRight className="w-4 h-4" />
                </Link>
              )}
              {step.done && (
                <span className="text-sm text-green-600 font-medium flex-shrink-0">已完成</span>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 flex justify-between items-center">
          <button onClick={runChecks} className="text-sm text-xy-brand-500 hover:text-xy-brand-600 font-medium flex items-center gap-1 transition-colors">
            <RotateCcw className="w-3.5 h-3.5" /> 重新检测
          </button>
          <button onClick={handleDismiss} className="text-sm text-xy-text-muted hover:text-xy-text-primary transition-colors">
            稍后配置，跳过引导
          </button>
        </div>
      </div>
    </div>
  );
}
