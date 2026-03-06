import React, { useState, useEffect, useMemo } from 'react';
import { getProducts, unpublishProduct, publishProduct } from '../../api/xianguanjia';
import toast from 'react-hot-toast';
import { Package, Search, Plus, RefreshCw, PowerOff, Play, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function ProductList() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchProducts();
  }, [page]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const res = await getProducts(page, 20);
      if (res.data?.ok) {
        setProducts(res.data.data?.list || []);
      } else {
        toast.error(res.data?.error || '无法获取商品列表');
      }
    } catch {
      toast.error('加载失败');
    } finally {
      setLoading(false);
    }
  };

  const filteredProducts = useMemo(() => {
    if (!searchQuery.trim()) return products;
    const q = searchQuery.toLowerCase();
    return products.filter(p =>
      (p.title && p.title.toLowerCase().includes(q)) ||
      (p.product_id && String(p.product_id).toLowerCase().includes(q))
    );
  }, [products, searchQuery]);

  const toggleStatus = async (product) => {
    const isOnline = product.status === 1 || product.status === '1' || product.status === 'on_sale';
    const actionStr = isOnline ? '下架' : '重新上架';
    
    try {
      toast.loading(`正在${actionStr}...`, { id: 'status_toggle' });
      const res = isOnline
        ? await unpublishProduct(product.product_id)
        : await publishProduct(product.product_id);
      
      if (res.data?.ok) {
        toast.success(`${actionStr}成功`, { id: 'status_toggle' });
        fetchProducts();
      } else {
        toast.error(res.data?.error || `${actionStr}失败`, { id: 'status_toggle' });
      }
    } catch {
      toast.error(`${actionStr}出错`, { id: 'status_toggle' });
    }
  };

  const formatPrice = (price) => {
    const num = Number(price);
    if (!num || isNaN(num)) return '¥0.00';
    return `¥${(num / 100).toFixed(2)}`;
  };

  return (
    <div className="xy-page xy-enter">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title">商品管理</h1>
          <p className="xy-subtitle mt-1">管理闲鱼在售商品，或使用 AI 辅助发布新商品</p>
        </div>
        <div className="flex gap-3">
          <button onClick={fetchProducts} className="xy-btn-secondary px-3" aria-label="刷新商品列表">
            <RefreshCw className="w-4 h-4" />
          </button>
          <Link to="/products/auto-publish" className="xy-btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" /> 自动上架
          </Link>
        </div>
      </div>

      <div className="xy-card overflow-hidden">
        <div className="border-b border-xy-border px-4 py-3 bg-xy-gray-50 flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-xy-text-muted" />
            <input 
              type="text" 
              placeholder="搜索商品标题或 ID" 
              className="xy-input pl-9 pr-3 py-1.5 text-sm"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              aria-label="搜索商品"
            />
          </div>
        </div>

        {loading ? (
          <div className="p-12 text-center">
            <RefreshCw className="w-8 h-8 animate-spin text-xy-brand-500 mx-auto" />
            <p className="mt-4 text-xy-text-secondary">正在同步闲管家数据...</p>
          </div>
        ) : filteredProducts.length === 0 ? (
          <div className="p-16 text-center">
            <div className="w-16 h-16 bg-xy-gray-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <Package className="w-8 h-8 text-xy-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-xy-text-primary mb-1">
              {searchQuery ? '未找到匹配商品' : '还没有商品'}
            </h3>
            <p className="text-xy-text-secondary mb-6">
              {searchQuery ? '请尝试其他搜索关键词' : '点击右上角按钮开始你的第一次 AI 智能上架吧'}
            </p>
            {!searchQuery && <Link to="/products/auto-publish" className="xy-btn-primary">去发布商品</Link>}
          </div>
        ) : (
          <div className="divide-y divide-xy-border">
            {filteredProducts.map(p => {
              const isOnline = p.status === 1 || p.status === '1' || p.status === 'on_sale';
              return (
                <div key={p.product_id} className="p-5 hover:bg-xy-gray-50 transition-colors flex flex-col md:flex-row gap-5">
                  <div className="w-24 h-24 bg-xy-gray-100 rounded-lg overflow-hidden border border-xy-border flex-shrink-0 relative">
                    {p.pic_url || (Array.isArray(p.images) && p.images[0]) ? (
                      <img src={p.pic_url || p.images[0]} alt={p.title || '商品图片'} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-xy-gray-300">
                        <Package className="w-8 h-8" />
                      </div>
                    )}
                    {!isOnline && (
                      <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                        <span className="text-white text-xs font-bold px-2 py-1 bg-black/50 rounded">已下架</span>
                      </div>
                    )}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="text-base font-medium text-xy-text-primary mb-2 line-clamp-2 leading-snug">
                          {p.title}
                        </h3>
                        <div className="flex flex-wrap items-center gap-4 text-sm text-xy-text-secondary mb-2">
                          <span className="text-lg font-bold text-xy-brand-500">{formatPrice(p.price)}</span>
                          <span className="bg-xy-gray-100 px-2 py-0.5 rounded text-xs">库存: {p.stock ?? 1}</span>
                          {p.view_count != null && <span>浏览 {p.view_count}</span>}
                          {p.want_count != null && <span>想要 {p.want_count}</span>}
                        </div>
                        <p className="text-xs text-xy-text-muted">ID: {p.product_id}</p>
                      </div>
                      
                      <div className="flex flex-col items-end gap-2 flex-shrink-0">
                        {isOnline ? (
                          <button 
                            onClick={() => toggleStatus(p)}
                            className="xy-btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 text-red-600 hover:bg-red-50 hover:border-red-200"
                          >
                            <PowerOff className="w-3.5 h-3.5" /> 下架
                          </button>
                        ) : (
                          <button 
                            onClick={() => toggleStatus(p)}
                            className="xy-btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 text-green-600 hover:bg-green-50 hover:border-green-200"
                          >
                            <Play className="w-3.5 h-3.5" /> 上架
                          </button>
                        )}
                        <a href={`https://h5.m.goofish.com/app/idleFish-F2e/fish-mini-item/pages/detail?id=${p.product_id}`} target="_blank" rel="noreferrer" className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1 mt-1">
                          查看闲鱼详情 <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
