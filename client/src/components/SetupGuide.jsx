import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { nodeApi, pyApi } from '../api/index';
import { getSystemConfig } from '../api/config';
import { CheckCircle, Circle, ArrowRight, X, Zap } from 'lucide-react';

const DISMISS_KEY = 'xianyu_setup_guide_dismissed';

export default function SetupGuide() {
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === '1');
  const [checks, setChecks] = useState({
    nodeBackend: null,
    pythonBackend: null,
    xgjConfigured: null,
    aiConfigured: null,
    cookieSet: null,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (dismissed) return;
    runChecks();
  }, [dismissed]);

  const runChecks = async () => {
    setLoading(true);
    const result = {
      nodeBackend: false,
      pythonBackend: false,
      xgjConfigured: false,
      aiConfigured: false,
      cookieSet: false,
    };

    try {
      const res = await nodeApi.get('/health');
      result.nodeBackend = res.data?.status === 'ok';
    } catch { /* node backend unavailable */ }

    try {
      const res = await getSystemConfig();
      const cfg = res.data?.config || {};
      const xgj = cfg.xianguanjia || {};
      result.xgjConfigured = !!(xgj.app_key && xgj.app_secret);
      const ai = cfg.ai || {};
      result.aiConfigured = !!ai.api_key;
    } catch { /* config unavailable */ }

    try {
      const res = await pyApi.get('/api/status');
      result.pythonBackend = true;
      result.cookieSet = !!res.data?.cookie_exists;
    } catch { /* python backend unavailable */ }

    setChecks(result);
    setLoading(false);
  };

  const handleDismiss = () => {
    localStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  };

  if (dismissed) return null;

  const allDone = checks.pythonBackend && checks.xgjConfigured && checks.aiConfigured && checks.cookieSet;

  if (loading) return null;
  if (allDone) return null;

  const steps = [
    {
      key: 'nodeBackend',
      label: 'Node 代理（可选）',
      desc: '用于 webhook 校验和附加 API 代理',
      done: checks.nodeBackend,
      action: null,
    },
    {
      key: 'pythonBackend',
      label: 'Python 后端',
      desc: '自动化引擎和消息处理',
      done: checks.pythonBackend,
      action: null,
    },
    {
      key: 'xgjConfigured',
      label: '闲管家 API 配置',
      desc: '填入 AppKey 和 AppSecret',
      done: checks.xgjConfigured,
      action: '/config',
    },
    {
      key: 'aiConfigured',
      label: 'AI 服务配置',
      desc: '配置 AI API Key 用于自动回复',
      done: checks.aiConfigured,
      action: '/config',
    },
    {
      key: 'cookieSet',
      label: '闲鱼 Cookie',
      desc: '粘贴浏览器 Cookie 授权账号',
      done: checks.cookieSet,
      action: '/accounts',
    },
  ];

  const completedCount = steps.filter(s => s.done).length;

  return (
    <div className="xy-card mb-8 overflow-hidden border-2 border-xy-brand-200">
      <div className="px-6 py-4 bg-gradient-to-r from-xy-brand-50 to-orange-50 border-b border-xy-brand-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-xy-brand-500 text-white p-2 rounded-xl">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h2 className="font-bold text-xy-text-primary">首次使用配置引导</h2>
            <p className="text-sm text-xy-text-secondary">完成以下 {steps.length} 个步骤即可开始使用 ({completedCount}/{steps.length})</p>
          </div>
        </div>
        <button onClick={handleDismiss} className="text-xy-text-muted hover:text-xy-text-primary p-1" aria-label="关闭引导">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="p-6">
        <div className="space-y-4">
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
              </div>
              {!step.done && step.action && (
                <Link
                  to={step.action}
                  className="flex items-center gap-1 text-sm font-medium text-xy-brand-500 hover:text-xy-brand-600 flex-shrink-0"
                >
                  去配置 <ArrowRight className="w-4 h-4" />
                </Link>
              )}
              {step.done && (
                <span className="text-sm text-green-600 font-medium flex-shrink-0">已完成</span>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 flex justify-between items-center">
          <button onClick={runChecks} className="text-sm text-xy-brand-500 hover:text-xy-brand-600 font-medium">
            重新检测
          </button>
          <button onClick={handleDismiss} className="text-sm text-xy-text-muted hover:text-xy-text-primary">
            稍后配置，跳过引导
          </button>
        </div>
      </div>
    </div>
  );
}
