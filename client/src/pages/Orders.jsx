import React, { useState, useEffect } from 'react';
import { getOrders } from '../api/xianguanjia';
import toast from 'react-hot-toast';
import { Receipt, Search, Filter, AlertCircle, RefreshCw, Tag, BellRing } from 'lucide-react';
import { useCurrentAccount } from '../contexts/AccountContext';

export default function Orders() {
  const { currentAccountId } = useCurrentAccount();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('ALL'); // ALL, WAIT_BUYER_PAY, WAIT_SELLER_SEND

  useEffect(() => {
    fetchOrders();
  }, [tab, currentAccountId]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const statusMap = {
        'ALL': undefined,
        'WAIT_BUYER_PAY': 1,
        'WAIT_SELLER_SEND': 2
      };
      
      const payload = {
        page_no: 1,
        page_size: 20
      };
      if (statusMap[tab]) {
        payload.order_status = statusMap[tab];
      }
      
      const res = await getOrders(payload);
      if (res.data?.ok) {
        setOrders(res.data.data?.list || []);
      } else {
        toast.error(res.data?.error || '无法获取订单');
      }
    } catch (e) {
      toast.error('加载订单失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRemind = (orderId) => {
    // 调用 Python 后端的催单接口
    toast.success(`已加入催单队列: ${orderId}`);
  };

  const handleAdjustPrice = (orderId) => {
    toast.success(`进入改价流程: ${orderId}`);
  };

  return (
    <div className="xy-page xy-enter">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title">订单中心</h1>
          <p className="xy-subtitle mt-1">管理店铺订单与改价、催单操作</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchOrders} className="xy-btn-secondary px-3">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="xy-card overflow-hidden">
        {/* Tabs & Filters */}
        <div className="border-b border-xy-border px-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex gap-6 overflow-x-auto whitespace-nowrap">
            {[
              { id: 'ALL', label: '全部订单' },
              { id: 'WAIT_BUYER_PAY', label: '待付款' },
              { id: 'WAIT_SELLER_SEND', label: '待发货' }
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`py-4 text-sm font-medium border-b-2 transition-colors ${
                  tab === t.id 
                    ? 'border-xy-brand-500 text-xy-brand-600' 
                    : 'border-transparent text-xy-text-secondary hover:text-xy-text-primary'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          
          <div className="py-3 flex items-center gap-2 min-w-[240px]">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-xy-text-muted" />
              <input 
                type="text" 
                placeholder="搜索订单号/买家" 
                className="xy-input pl-9 pr-3 py-1.5 text-sm"
              />
            </div>
            <button className="xy-btn-secondary p-2">
              <Filter className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Order List */}
        {loading ? (
          <div className="p-12 text-center">
            <RefreshCw className="w-8 h-8 animate-spin text-xy-brand-500 mx-auto" />
            <p className="mt-4 text-xy-text-secondary">加载中...</p>
          </div>
        ) : orders.length === 0 ? (
          <div className="p-16 text-center">
            <div className="w-16 h-16 bg-xy-gray-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <Receipt className="w-8 h-8 text-xy-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-xy-text-primary mb-1">暂无订单</h3>
            <p className="text-xy-text-secondary">当前状态下没有查询到订单</p>
          </div>
        ) : (
          <div className="divide-y divide-xy-border">
            {orders.map(order => (
              <div key={order.order_id} className="p-5 hover:bg-xy-gray-50 transition-colors">
                <div className="flex flex-wrap items-center justify-between gap-4 mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium">订单号: {order.order_id}</span>
                    <span className="text-xs text-xy-text-muted">{order.create_time}</span>
                  </div>
                  <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                    order.status === 1 ? 'bg-orange-100 text-orange-700' :
                    order.status === 2 ? 'bg-blue-100 text-blue-700' :
                    'bg-xy-gray-100 text-xy-text-secondary'
                  }`}>
                    {order.status === 1 ? '待付款' : order.status === 2 ? '待发货' : '其他'}
                  </span>
                </div>
                
                <div className="flex gap-4">
                  <div className="w-20 h-20 bg-xy-gray-100 rounded-lg overflow-hidden border border-xy-border flex-shrink-0">
                    <img src={order.pic_url || 'https://via.placeholder.com/80'} alt="" className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-base font-medium text-xy-text-primary truncate mb-1">{order.title || '未知商品'}</h3>
                    <p className="text-sm text-xy-text-secondary mb-2">买家: {order.buyer_name}</p>
                    <div className="text-lg font-bold text-xy-brand-500">¥{(order.total_fee / 100).toFixed(2)}</div>
                  </div>
                  
                  <div className="flex flex-col gap-2 justify-end">
                    {order.status === 1 && (
                      <>
                        <button onClick={() => handleRemind(order.order_id)} className="xy-btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 hover:text-blue-600 hover:border-blue-200">
                          <BellRing className="w-3.5 h-3.5" /> 一键催单
                        </button>
                        <button onClick={() => handleAdjustPrice(order.order_id)} className="xy-btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 hover:text-orange-600 hover:border-orange-200">
                          <Tag className="w-3.5 h-3.5" /> 阶梯降价
                        </button>
                      </>
                    )}
                    {order.status === 2 && (
                      <button className="xy-btn-primary text-xs px-4 py-1.5">立即发货</button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
