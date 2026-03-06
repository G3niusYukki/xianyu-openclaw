import React, { useState, useEffect } from 'react';
import { pyApi } from '../../api/index';
import { getAccounts } from '../../api/accounts';
import { Store, Plus, Settings, Power, PowerOff, ShieldAlert, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

export default function AccountList() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [newCookie, setNewCookie] = useState('');
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchAccounts();
  }, []);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const res = await getAccounts();
      setAccounts(res.data?.accounts || []);
    } catch {
      setAccounts([]);
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
      setIsAdding(false);
      setNewCookie('');
      fetchAccounts();
    } catch {
      toast.error('保存失败');
    } finally {
      setSaving(false);
    }
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
        <button onClick={() => setIsAdding(true)} className="xy-btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> 更新 Cookie
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {accounts.map(acc => (
          <div
            key={acc.id}
            className={`xy-card p-5 relative overflow-hidden ${acc.current ? 'ring-2 ring-xy-brand-500 ring-offset-2' : ''}`}
          >
            {acc.current && (
              <div className="absolute top-0 right-0 bg-xy-brand-500 text-white text-[10px] font-bold px-3 py-1 rounded-bl-lg z-10">
                当前店铺
              </div>
            )}
            
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-orange-50">
                  <Store className="w-6 h-6 text-xy-brand-500" />
                </div>
                <div>
                  <h3 className="font-bold text-xy-text-primary">{acc.name}</h3>
                  <div className="flex items-center gap-1.5 mt-1">
                    <div className={`w-2 h-2 rounded-full ${acc.enabled ? 'bg-green-500' : 'bg-xy-gray-300'}`}></div>
                    <span className="text-xs text-xy-text-secondary">{acc.automation_enabled ? '自动化运行中' : '自动化未启动'}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-2 mb-6">
              <div className="flex justify-between text-sm">
                <span className="text-xy-text-secondary">闲管家配置</span>
                <span className={`font-medium ${acc.xgj_configured ? 'text-green-600' : 'text-red-500'}`}>
                  {acc.xgj_configured ? '已配置' : '未配置'}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-xy-text-secondary">Cookie 健康</span>
                <span className={`font-medium ${acc.health === 'good' ? 'text-green-600' : acc.health === 'warning' ? 'text-yellow-600' : 'text-red-500'}`}>
                  {acc.health_score ?? 0} 分
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
                onClick={() => toggleAutomation(acc.automation_enabled)}
                className={`p-2 border rounded-lg transition-colors ${acc.automation_enabled ? 'border-xy-border text-red-500 hover:bg-red-50' : 'border-xy-border text-green-600 hover:bg-green-50'}`}
                title={acc.automation_enabled ? "停用自动化" : "启用自动化"}
                aria-label={acc.automation_enabled ? "停用自动化" : "启用自动化"}
              >
                {acc.automation_enabled ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
              </button>
            </div>
          </div>
        ))}
      </div>

      {isAdding && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-xy-gray-50">
              <h3 className="font-bold text-lg">更新 Cookie</h3>
              <button onClick={() => setIsAdding(false)} className="text-xy-text-muted hover:text-xy-text-primary text-xl" aria-label="关闭">&times;</button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="xy-label">闲鱼 Cookie (必填)</label>
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
              <button onClick={() => setIsAdding(false)} className="xy-btn-secondary">取消</button>
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
