import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { pyApi } from '../api';
import toast from 'react-hot-toast';

const AccountContext = createContext(null);

export function AccountProvider({ children }) {
  const [accounts, setAccounts] = useState([]);
  const [currentAccountId, setCurrentAccountId] = useState(
    localStorage.getItem('currentAccountId') || null
  );
  const [loading, setLoading] = useState(true);

  const fetchAccounts = useCallback(async () => {
    try {
      setLoading(true);
      // 调用 Python 后端的 /api/status 来获取当前账号状态列表
      // 目前没有直接的获取全部账号的接口，或者通过配置接口获取
      // TODO: 需要后端提供获取账户列表的专门接口，或者通过 /api/status 获取。暂用 mock 或直接发请求
      const res = await pyApi.get('/api/status');
      
      // 假设后端返回 { accounts: [{id: 'acc_1', name: '主账号', enabled: true}] } 
      // 这块根据真实的后端数据结构调整
      const accountList = res.data?.accounts || [
        // { id: 'account_1', name: '默认店铺', enabled: true }
      ];
      
      setAccounts(accountList);

      if (accountList.length > 0 && (!currentAccountId || !accountList.find(a => a.id === currentAccountId))) {
        // 如果当前没选，或者选的不在列表里，默认选第一个
        switchAccount(accountList[0].id);
      }
    } catch (error) {
      console.error('Failed to load accounts:', error);
      // toast.error('无法加载店铺列表');
    } finally {
      setLoading(false);
    }
  }, [currentAccountId]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const switchAccount = (accountId) => {
    setCurrentAccountId(accountId);
    localStorage.setItem('currentAccountId', accountId);
    
    // 我们可能需要触发一个全局事件或者直接刷新页面来重新加载数据
    // 最简单的方式是触发一个 custom event
    window.dispatchEvent(new Event('accountSwitched'));
  };

  const currentAccount = accounts.find((a) => a.id === currentAccountId) || null;

  return (
    <AccountContext.Provider
      value={{
        accounts,
        currentAccount,
        currentAccountId,
        switchAccount,
        refreshAccounts: fetchAccounts,
        loading
      }}
    >
      {children}
    </AccountContext.Provider>
  );
}

export function useCurrentAccount() {
  const context = useContext(AccountContext);
  if (!context) {
    throw new Error('useCurrentAccount must be used within an AccountProvider');
  }
  return context;
}
