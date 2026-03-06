import React, { useState } from 'react';
import { useCurrentAccount } from '../../contexts/AccountContext';
import { Store, Plus, Settings, Power, PowerOff, ShieldAlert } from 'lucide-react';
import toast from 'react-hot-toast';

export default function AccountList() {
  const { accounts, currentAccountId, switchAccount, refreshAccounts } = useCurrentAccount();
  const [isAdding, setIsAdding] = useState(false);

  const toggleAccount = (id, currentStatus) => {
    // TODO: 调用后端启用/禁用接口
    toast.success(`账户已${currentStatus ? '禁用' : '启用'} (Demo)`);
    refreshAccounts();
  };

  return (
    <div className="xy-page xy-enter max-w-5xl">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title">多店铺管理</h1>
          <p className="xy-subtitle mt-1">管理闲鱼账号授权、Cookie 状态与环境隔离</p>
        </div>
        <button onClick={() => setIsAdding(true)} className="xy-btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> 添加新店铺
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {accounts.map(acc => (
          <div 
            key={acc.id} 
            className={`xy-card p-5 relative overflow-hidden transition-all ${currentAccountId === acc.id ? 'ring-2 ring-xy-brand-500 ring-offset-2' : ''}`}
          >
            {currentAccountId === acc.id && (
              <div className="absolute top-0 right-0 bg-xy-brand-500 text-white text-[10px] font-bold px-3 py-1 rounded-bl-lg z-10">
                当前操作
              </div>
            )}
            
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`p-3 rounded-xl ${acc.enabled ? 'bg-orange-50' : 'bg-xy-gray-100'}`}>
                  <Store className={`w-6 h-6 ${acc.enabled ? 'text-xy-brand-500' : 'text-xy-text-muted'}`} />
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
                <span className="text-xy-text-secondary">ID</span>
                <span className="font-medium text-xy-text-primary">{acc.id}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-xy-text-secondary">Cookie 状态</span>
                <span className="flex items-center gap-1 text-green-600 font-medium">
                  正常
                </span>
              </div>
            </div>

            <div className="flex gap-2 pt-4 border-t border-xy-border">
              <button 
                onClick={() => switchAccount(acc.id)}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors ${currentAccountId === acc.id ? 'bg-xy-brand-50 text-xy-brand-600' : 'bg-xy-surface border border-xy-border hover:bg-xy-gray-50'}`}
              >
                {currentAccountId === acc.id ? '使用中' : '切换至此'}
              </button>
              
              <button 
                onClick={() => toast('进入单店配置 (Demo)')}
                className="p-2 border border-xy-border rounded-lg text-xy-text-secondary hover:text-xy-brand-500 hover:border-xy-brand-200 transition-colors"
                title="配置"
              >
                <Settings className="w-4 h-4" />
              </button>
              
              <button 
                onClick={() => toggleAccount(acc.id, acc.enabled)}
                className={`p-2 border rounded-lg transition-colors ${acc.enabled ? 'border-xy-border text-red-500 hover:bg-red-50' : 'border-xy-border text-green-600 hover:bg-green-50'}`}
                title={acc.enabled ? "停用" : "启用"}
              >
                {acc.enabled ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
              </button>
            </div>
          </div>
        ))}
      </div>

      {accounts.length === 0 && !isAdding && (
        <div className="xy-card p-16 text-center">
          <Store className="w-12 h-12 text-xy-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-xy-text-primary mb-2">暂无可用店铺</h3>
          <p className="text-xy-text-secondary mb-6">请先添加一个闲鱼账号以开始使用系统功能</p>
          <button onClick={() => setIsAdding(true)} className="xy-btn-primary">立即添加</button>
        </div>
      )}

      {isAdding && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden animate-in zoom-in-95">
            <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-xy-gray-50">
              <h3 className="font-bold text-lg">添加新店铺</h3>
              <button onClick={() => setIsAdding(false)} className="text-xy-text-muted hover:text-xy-text-primary">✕</button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="xy-label">店铺/账号标识 (英文或拼音)</label>
                <input type="text" className="xy-input px-3 py-2" placeholder="如: account_2" />
              </div>
              <div>
                <label className="xy-label">店铺显示名称</label>
                <input type="text" className="xy-input px-3 py-2" placeholder="如: 小王数码店" />
              </div>
              <div>
                <label className="xy-label">闲鱼 Cookie (必填)</label>
                <textarea className="xy-input px-3 py-2 h-24 resize-none" placeholder="粘贴从浏览器抓取的闲鱼 Cookie"></textarea>
                <p className="text-xs text-xy-text-muted mt-1 flex items-center gap-1"><ShieldAlert className="w-3 h-3"/> Cookie 将在本地加密存储，仅用于本系统的自动化操作</p>
              </div>
            </div>
            <div className="px-6 py-4 bg-xy-gray-50 border-t border-xy-border flex justify-end gap-3">
              <button onClick={() => setIsAdding(false)} className="xy-btn-secondary">取消</button>
              <button onClick={() => { toast.success('添加成功(Demo)'); setIsAdding(false); }} className="xy-btn-primary">保存并添加</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
