import React, { useState, useRef, useEffect } from 'react';
import { useCurrentAccount } from '../../contexts/AccountContext';
import { ChevronDown, Store, Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function AccountSelector() {
  const { accounts, currentAccount, switchAccount, loading } = useCurrentAccount();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (loading && accounts.length === 0) {
    return <div className="h-9 w-32 bg-gray-200 animate-pulse rounded-md"></div>;
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 bg-xy-surface border border-xy-border rounded-lg hover:bg-xy-gray-50 transition-colors"
      >
        <Store className="w-4 h-4 text-xy-text-secondary" />
        <span className="text-sm font-medium text-xy-text-primary truncate max-w-[120px]">
          {currentAccount ? currentAccount.name : '未选择店铺'}
        </span>
        <ChevronDown className="w-4 h-4 text-xy-text-secondary" />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-64 bg-white border border-xy-border rounded-xl shadow-lg z-50 py-1">
          {accounts.length > 0 ? (
            accounts.map((acc) => (
              <button
                key={acc.id}
                onClick={() => {
                  switchAccount(acc.id);
                  setIsOpen(false);
                }}
                className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between hover:bg-xy-gray-50 transition-colors ${
                  currentAccount?.id === acc.id ? 'bg-orange-50 text-xy-brand-500' : 'text-xy-text-primary'
                }`}
              >
                <div className="flex items-center gap-2">
                  <Store className="w-4 h-4" />
                  <span className="truncate">{acc.name}</span>
                </div>
                {/* 可以根据后端状态显示在线/离线 */}
                <div className={`w-2 h-2 rounded-full ${acc.enabled ? 'bg-green-500' : 'bg-gray-300'}`} title={acc.enabled ? '已启用' : '已禁用'}></div>
              </button>
            ))
          ) : (
            <div className="px-4 py-3 text-sm text-xy-text-secondary text-center">暂无可用店铺</div>
          )}
          
          <div className="h-px bg-xy-border my-1"></div>
          
          <button
            onClick={() => {
              setIsOpen(false);
              navigate('/accounts');
            }}
            className="w-full text-left px-4 py-2.5 text-sm text-xy-text-secondary hover:text-xy-brand-500 hover:bg-xy-gray-50 flex items-center gap-2 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>管理店铺</span>
          </button>
        </div>
      )}
    </div>
  );
}
