import React, { useState, useEffect, useRef } from 'react';
import { pyApi } from '../../api/index';
import { nodeApi } from '../../api/index';
import { Store, Plus, Settings, Power, PowerOff, ShieldAlert, RefreshCw, Zap, Loader2, CheckCircle, XCircle, Monitor, ClipboardPaste } from 'lucide-react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

const GRAB_STAGE_CONFIG = {
  idle: { color: 'text-xy-gray-500', label: '就绪' },
  reading_db: { color: 'text-blue-600', label: '读取浏览器 Cookie' },
  validating: { color: 'text-blue-600', label: '验证有效性' },
  login_required: { color: 'text-orange-600', label: '需要登录' },
  waiting_login: { color: 'text-orange-600', label: '等待登录' },
  saving: { color: 'text-blue-600', label: '保存中' },
  success: { color: 'text-green-600', label: '获取成功' },
  failed: { color: 'text-red-600', label: '获取失败' },
  cancelled: { color: 'text-xy-gray-500', label: '已取消' },
};

export default function AccountList() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cookieMode, setCookieMode] = useState(null);
  const [newCookie, setNewCookie] = useState('');
  const [saving, setSaving] = useState(false);
  const [grabbing, setGrabbing] = useState(false);
  const [grabProgress, setGrabProgress] = useState(null);
  const eventSourceRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchAccounts();
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const res = await nodeApi.get('/config');
      const cfg = res.data?.config || {};
      const xgj = cfg.xianguanjia || {};
      const configured = !!(xgj.app_key && xgj.app_secret && !String(xgj.app_key).includes('****'));
      setAccounts([{
        id: 'default',
        name: '默认店铺',
        enabled: true,
        configured,
      }]);
    } catch {
      setAccounts([{ id: 'default', name: '默认店铺', enabled: true, configured: false }]);
    } finally {
      setLoading(false);
    }
  };

  const toggleAutomation = async (currentStatus) => {
    try {
      const action = currentStatus ? 'stop' : 'start';
      await pyApi.post('/api/module/control', { action, target: 'presales' });
      toast.success(`已${currentStatus ? '停用' : '启用'}自动化服务`);
      fetchAccounts();
    } catch {
      toast.error('操作失败');
    }
  };

  const handleSaveCookie = async () => {
    if (!newCookie.trim()) {
      toast.error('请填写闲鱼 Cookie');
      return;
    }
    setSaving(true);
    try {
      await pyApi.post('/api/update-cookie', { cookie: newCookie });
      toast.success('Cookie 已保存');
      setCookieMode(null);
      setNewCookie('');
      fetchAccounts();
    } catch {
      toast.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const startAutoGrab = async () => {
    setGrabbing(true);
    setGrabProgress({ stage: 'reading_db', message: '正在启动...', hint: '', progress: 0 });

    try {
      await pyApi.post('/api/cookie/auto-grab');
    } catch (err) {
      if (err?.response?.status === 409) {
        toast.error('已有获取任务在运行');
      } else {
        toast.error('启动失败：' + (err.message || '未知错误'));
        setGrabbing(false);
        setGrabProgress(null);
        return;
      }
    }

    const pyBase = pyApi.defaults.baseURL || 'http://localhost:8091';
    const es = new EventSource(`${pyBase}/api/cookie/auto-grab/status`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setGrabProgress(data);
        if (data.stage === 'success') {
          toast.success('Cookie 获取成功！');
          setGrabbing(false);
          es.close();
          fetchAccounts();
        } else if (data.stage === 'failed' || data.stage === 'cancelled') {
          setGrabbing(false);
          es.close();
          if (data.stage === 'failed') toast.error(data.message || '获取失败');
        }
      } catch {}
    };

    es.onerror = () => {
      setGrabbing(false);
      es.close();
    };
  };

  const cancelAutoGrab = async () => {
    try {
      await pyApi.post('/api/cookie/auto-grab/cancel');
    } catch {}
    if (eventSourceRef.current) eventSourceRef.current.close();
    setGrabbing(false);
    setGrabProgress(null);
  };

  if (loading) {
    return (
      <div className="xy-page xy-enter flex items-center justify-center min-h-[50vh]">
        <RefreshCw className="w-8 h-8 animate-spin text-xy-brand-500" />
      </div>
    );
  }

  return (
    <div className="xy-page xy-enter max-w-5xl">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title">店铺管理</h1>
          <p className="xy-subtitle mt-1">管理闲鱼账号授权、Cookie 状态与自动化服务</p>
        </div>
        <button onClick={() => setCookieMode('choose')} className="xy-btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> 更新 Cookie
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {accounts.map(acc => (
          <div key={acc.id} className="xy-card p-5 relative overflow-hidden ring-2 ring-xy-brand-500 ring-offset-2">
            <div className="absolute top-0 right-0 bg-xy-brand-500 text-white text-[10px] font-bold px-3 py-1 rounded-bl-lg z-10">
              当前店铺
            </div>
            
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-orange-50">
                  <Store className="w-6 h-6 text-xy-brand-500" />
                </div>
                <div>
                  <h3 className="font-bold text-xy-text-primary">{acc.name}</h3>
                  <div className="flex items-center gap-1.5 mt-1">
                    <div className={`w-2 h-2 rounded-full ${acc.enabled ? 'bg-green-500' : 'bg-xy-gray-300'}`}></div>
                    <span className="text-xs text-xy-text-secondary">{acc.enabled ? '运行中' : '已停用'}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-2 mb-6">
              <div className="flex justify-between text-sm">
                <span className="text-xy-text-secondary">闲管家配置</span>
                <span className={`font-medium ${acc.configured ? 'text-green-600' : 'text-red-500'}`}>
                  {acc.configured ? '已配置' : '未配置'}
                </span>
              </div>
            </div>

            <div className="flex gap-2 pt-4 border-t border-xy-border">
              <button 
                onClick={() => navigate('/config')}
                className="flex-1 py-2 text-sm font-medium rounded-lg bg-xy-surface border border-xy-border hover:bg-xy-gray-50 flex items-center justify-center gap-1.5"
              >
                <Settings className="w-4 h-4" /> 配置
              </button>
              
              <button 
                onClick={() => toggleAutomation(acc.enabled)}
                className={`p-2 border rounded-lg transition-colors ${acc.enabled ? 'border-xy-border text-red-500 hover:bg-red-50' : 'border-xy-border text-green-600 hover:bg-green-50'}`}
                title={acc.enabled ? "停用自动化" : "启用自动化"}
                aria-label={acc.enabled ? "停用自动化" : "启用自动化"}
              >
                {acc.enabled ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
              </button>
            </div>
          </div>
        ))}
      </div>

      {cookieMode === 'choose' && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-xy-gray-50">
              <h3 className="font-bold text-lg">获取闲鱼 Cookie</h3>
              <button onClick={() => setCookieMode(null)} className="text-xy-text-muted hover:text-xy-text-primary text-xl" aria-label="关闭">&times;</button>
            </div>
            <div className="p-6">
              <p className="text-sm text-xy-text-secondary mb-5">
                Cookie 是闲鱼的登录凭证，系统需要它来代替你操作闲鱼平台。请选择获取方式：
              </p>
              <div className="space-y-3">
                <button
                  onClick={() => { setCookieMode('auto'); startAutoGrab(); }}
                  className="w-full p-4 rounded-xl border-2 border-xy-brand-500 bg-orange-50 hover:bg-orange-100 transition-colors text-left group"
                >
                  <div className="flex items-center gap-3 mb-1">
                    <Zap className="w-5 h-5 text-xy-brand-500" />
                    <span className="font-bold text-xy-text-primary">自动获取（推荐）</span>
                  </div>
                  <p className="text-sm text-xy-text-secondary ml-8">
                    自动从浏览器读取 Cookie，如果你已在 Chrome 中登录过闲鱼，无需任何操作
                  </p>
                </button>

                <button
                  onClick={() => setCookieMode('manual')}
                  className="w-full p-4 rounded-xl border border-xy-border hover:bg-xy-gray-50 transition-colors text-left"
                >
                  <div className="flex items-center gap-3 mb-1">
                    <ClipboardPaste className="w-5 h-5 text-xy-text-secondary" />
                    <span className="font-bold text-xy-text-primary">手动粘贴</span>
                  </div>
                  <p className="text-sm text-xy-text-secondary ml-8">
                    从浏览器开发者工具 (F12) 复制 Cookie 后粘贴
                  </p>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {cookieMode === 'auto' && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-xy-gray-50">
              <h3 className="font-bold text-lg">自动获取 Cookie</h3>
              <button onClick={() => { cancelAutoGrab(); setCookieMode(null); }} className="text-xy-text-muted hover:text-xy-text-primary text-xl" aria-label="关闭">&times;</button>
            </div>
            <div className="p-6 space-y-5">
              {grabProgress && (
                <>
                  <div className="flex items-center gap-3">
                    {grabProgress.stage === 'success' ? (
                      <CheckCircle className="w-8 h-8 text-green-500 shrink-0" />
                    ) : grabProgress.stage === 'failed' || grabProgress.stage === 'cancelled' ? (
                      <XCircle className="w-8 h-8 text-red-500 shrink-0" />
                    ) : (
                      <Loader2 className="w-8 h-8 text-xy-brand-500 animate-spin shrink-0" />
                    )}
                    <div>
                      <p className={`font-semibold ${GRAB_STAGE_CONFIG[grabProgress.stage]?.color || 'text-xy-text-primary'}`}>
                        {grabProgress.message || GRAB_STAGE_CONFIG[grabProgress.stage]?.label || grabProgress.stage}
                      </p>
                      {grabProgress.hint && (
                        <p className="text-sm text-xy-text-secondary mt-0.5">{grabProgress.hint}</p>
                      )}
                    </div>
                  </div>

                  {grabProgress.progress > 0 && grabProgress.stage !== 'success' && grabProgress.stage !== 'failed' && (
                    <div className="w-full bg-xy-gray-100 rounded-full h-2">
                      <div
                        className="bg-xy-brand-500 h-2 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(grabProgress.progress, 100)}%` }}
                      ></div>
                    </div>
                  )}

                  {grabProgress.stage === 'waiting_login' && (
                    <div className="p-4 bg-orange-50 rounded-xl border border-orange-200">
                      <div className="flex items-start gap-2">
                        <Monitor className="w-5 h-5 text-orange-600 mt-0.5 shrink-0" />
                        <div className="text-sm">
                          <p className="font-medium text-orange-800">操作步骤：</p>
                          <ol className="list-decimal list-inside mt-1 space-y-1 text-orange-700">
                            <li>查看已打开的 Chrome 浏览器窗口</li>
                            <li>打开手机闲鱼 APP</li>
                            <li>扫描浏览器中的二维码登录</li>
                            <li>登录成功后系统会自动获取 Cookie</li>
                          </ol>
                        </div>
                      </div>
                    </div>
                  )}

                  {grabProgress.stage === 'reading_db' && (
                    <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                      <p className="text-sm text-blue-700">
                        <strong>提示：</strong>如果系统弹出"钥匙串访问"弹窗，请点击"允许"以读取浏览器 Cookie。
                      </p>
                    </div>
                  )}

                  {grabProgress.stage === 'success' && (
                    <div className="p-3 bg-green-50 rounded-lg border border-green-200">
                      <p className="text-sm text-green-700">
                        Cookie 有效期约 7-30 天。过期后可再次点击"自动获取"更新。
                      </p>
                    </div>
                  )}

                  {grabProgress.stage === 'failed' && (
                    <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                      <p className="text-sm text-red-700">
                        {grabProgress.error || '获取失败，请尝试手动粘贴 Cookie。'}
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="px-6 py-4 bg-xy-gray-50 border-t border-xy-border flex justify-end gap-3">
              {grabbing ? (
                <button onClick={cancelAutoGrab} className="xy-btn-secondary">取消</button>
              ) : (
                <>
                  <button onClick={() => { setCookieMode(null); setGrabProgress(null); }} className="xy-btn-secondary">关闭</button>
                  {grabProgress?.stage === 'failed' && (
                    <button onClick={() => setCookieMode('manual')} className="xy-btn-primary">手动粘贴</button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {cookieMode === 'manual' && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-xy-gray-50">
              <h3 className="font-bold text-lg">手动粘贴 Cookie</h3>
              <button onClick={() => setCookieMode(null)} className="text-xy-text-muted hover:text-xy-text-primary text-xl" aria-label="关闭">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                <p className="text-sm text-blue-700 font-medium mb-2">获取步骤：</p>
                <ol className="list-decimal list-inside text-sm text-blue-600 space-y-1">
                  <li>在 Chrome 中打开 <a href="https://www.goofish.com" target="_blank" rel="noopener noreferrer" className="underline">goofish.com</a> 并登录</li>
                  <li>按 F12 打开开发者工具</li>
                  <li>切换到 Network 标签，刷新页面</li>
                  <li>点击任意请求，找到 Request Headers 中的 Cookie</li>
                  <li>复制完整 Cookie 值粘贴到下方</li>
                </ol>
              </div>
              <div>
                <label className="xy-label">闲鱼 Cookie</label>
                <textarea 
                  className="xy-input px-3 py-2 h-32 resize-none" 
                  placeholder="粘贴从浏览器抓取的闲鱼 Cookie"
                  value={newCookie}
                  onChange={e => setNewCookie(e.target.value)}
                />
                <p className="text-xs text-xy-text-muted mt-1 flex items-center gap-1">
                  <ShieldAlert className="w-3 h-3"/> Cookie 将在本地加密存储，仅用于自动化操作
                </p>
              </div>
            </div>
            <div className="px-6 py-4 bg-xy-gray-50 border-t border-xy-border flex justify-end gap-3">
              <button onClick={() => setCookieMode(null)} className="xy-btn-secondary">取消</button>
              <button 
                onClick={handleSaveCookie} 
                disabled={saving}
                className="xy-btn-primary disabled:opacity-50"
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
