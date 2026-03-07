import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { api } from '../api/index';

export interface CategoryMeta {
  label: string;
  icon: string;
  desc: string;
}

export const CATEGORY_META: Record<string, CategoryMeta> = {
  express:      { label: '快递代发',     icon: '📦', desc: '转转、闲鱼代发快递包裹' },
  exchange:     { label: '兑换码/卡密', icon: '🔑', desc: '游戏兑换码、充值卡密等虚拟商品' },
  recharge:     { label: '充值代充',     icon: '💳', desc: '游戏代充、会员充值' },
  movie_ticket: { label: '电影票',       icon: '🎬', desc: '电影票代购' },
  account:      { label: '账号交易',     icon: '👤', desc: '游戏/平台账号交易' },
  game:         { label: '游戏道具',     icon: '🎮', desc: '游戏装备、皮肤、道具' },
};

const EXPRESS_FEATURES = new Set([
  'route-stats', 'export-routes', 'import-routes',
  'markup-rules', 'import-markup', 'pricing',
  'delivery', 'auto-ship',
]);

const VIRTUAL_FEATURES = new Set([
  'virtual-goods-metrics', 'virtual-goods-inspect',
  'exchange-templates', 'auto-delivery-code',
]);

const UNIVERSAL_FEATURES = new Set([
  'dashboard', 'cookie', 'ai', 'xgj', 'oss',
  'auto-reply', 'messages', 'notifications',
  'order-reminder', 'accounts', 'config',
  'analytics', 'products', 'orders',
  'auto-publish', 'listing',
]);

export interface StoreCategoryContextValue {
  category: string;
  meta: CategoryMeta;
  allCategories: Record<string, CategoryMeta>;
  switchCategory: (cat: string) => Promise<void>;
  isFeatureVisible: (featureKey: string) => boolean;
  loading: boolean;
}

const StoreCategoryContext = createContext<StoreCategoryContextValue | null>(null);

export function StoreCategoryProvider({ children }: { children: ReactNode }) {
  const [category, setCategory] = useState('express');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/config')
      .then(res => {
        const saved = res.data?.config?.store?.category;
        if (saved && CATEGORY_META[saved]) setCategory(saved);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const switchCategory = useCallback(async (newCat: string) => {
    if (!CATEGORY_META[newCat]) return;
    setCategory(newCat);
    try {
      await api.put('/config', { store: { category: newCat } });
    } catch {
      // persist failure is non-critical
    }
  }, []);

  const isFeatureVisible = useCallback((featureKey: string) => {
    if (UNIVERSAL_FEATURES.has(featureKey)) return true;
    if (category === 'express') return EXPRESS_FEATURES.has(featureKey);
    return VIRTUAL_FEATURES.has(featureKey);
  }, [category]);

  const meta = CATEGORY_META[category] || CATEGORY_META.express;

  return (
    <StoreCategoryContext.Provider value={{ category, meta, allCategories: CATEGORY_META, switchCategory, isFeatureVisible, loading }}>
      {children}
    </StoreCategoryContext.Provider>
  );
}

export function useStoreCategory(): StoreCategoryContextValue {
  const ctx = useContext(StoreCategoryContext);
  if (!ctx) throw new Error('useStoreCategory must be used within StoreCategoryProvider');
  return ctx;
}
