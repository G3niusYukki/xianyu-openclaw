import React, { useState, useEffect } from 'react';
import { getTrendData, getTopProducts } from '../../api/dashboard';
import { TrendingUp, BarChart2, Calendar, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Analytics() {
  const [metric, setMetric] = useState('views');
  const [days, setDays] = useState(30);
  const [trendData, setTrendData] = useState([]);
  const [topProducts, setTopProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [metric, days]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [trendRes, topRes] = await Promise.all([
        getTrendData(metric, days),
        getTopProducts(10)
      ]);
      
      if (trendRes.data) {
        const trend = Array.isArray(trendRes.data) ? trendRes.data : (trendRes.data.trend || []);
        setTrendData(trend);
      }
      if (topRes.data) {
        const products = Array.isArray(topRes.data) ? topRes.data : (topRes.data.products || []);
        setTopProducts(products);
      }
    } catch (e) {
      toast.error('加载分析数据失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="xy-page xy-enter">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title flex items-center gap-2"><BarChart2 className="w-6 h-6 text-xy-brand-500" /> 数据分析</h1>
          <p className="xy-subtitle mt-1">查看店铺转化漏斗、流量趋势与爆款商品</p>
        </div>
        <div className="flex gap-2">
          <select 
            className="xy-input py-1.5 px-3 text-sm bg-white"
            value={days}
            onChange={e => setDays(Number(e.target.value))}
          >
            <option value={7}>过去 7 天</option>
            <option value={30}>过去 30 天</option>
            <option value={90}>过去 90 天</option>
          </select>
          <button onClick={fetchData} className="xy-btn-secondary px-3">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        {/* 左侧：趋势图 (这里用 CSS 模拟一个简单的柱状图) */}
        <div className="md:col-span-2 xy-card p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="font-bold text-xy-text-primary">核心指标趋势</h3>
            <div className="flex bg-xy-gray-100 p-1 rounded-lg">
              {[
                { id: 'views', label: '浏览量' },
                { id: 'wants', label: '想要数' },
                { id: 'sales', label: '成交量' }
              ].map(m => (
                <button
                  key={m.id}
                  onClick={() => setMetric(m.id)}
                  className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                    metric === m.id ? 'bg-white shadow-sm text-xy-text-primary' : 'text-xy-text-secondary hover:text-xy-text-primary'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          
          <div className="h-64 flex items-end justify-between gap-1 mt-4 border-b border-xy-border pb-2 relative">
            {loading ? (
              <div className="absolute inset-0 flex items-center justify-center bg-white/50">
                <RefreshCw className="w-6 h-6 animate-spin text-xy-brand-500" />
              </div>
            ) : trendData.length > 0 ? (
              trendData.map((day, i) => (
                <div key={i} className="w-full flex flex-col items-center group relative">
                  <div 
                    className="w-full bg-xy-brand-200 group-hover:bg-xy-brand-400 transition-colors rounded-t-sm"
                    style={{ height: `${Math.max(5, (day.value / Math.max(...trendData.map(d=>d.value))) * 100)}%` }}
                  ></div>
                  {/* Tooltip */}
                  <div className="opacity-0 group-hover:opacity-100 absolute bottom-full mb-2 bg-xy-gray-900 text-white text-xs py-1 px-2 rounded whitespace-nowrap z-10 pointer-events-none transition-opacity">
                    {day.date}: {day.value}
                  </div>
                </div>
              ))
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center text-xy-text-muted">
                <Calendar className="w-8 h-8 mb-2" />
                <p>暂无趋势数据</p>
              </div>
            )}
          </div>
        </div>

        {/* 右侧：热门商品 */}
        <div className="xy-card p-0 overflow-hidden flex flex-col">
          <div className="px-6 py-4 border-b border-xy-border bg-xy-gray-50 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-xy-success" />
            <h3 className="font-bold text-xy-text-primary">近期爆款商品</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {loading ? (
              <div className="text-center py-8 text-xy-text-muted">加载中...</div>
            ) : topProducts.length > 0 ? (
              topProducts.map((p, idx) => (
                <div key={idx} className="flex gap-3 items-center">
                  <div className="w-6 h-6 rounded-full bg-xy-gray-100 flex items-center justify-center text-xs font-bold text-xy-text-secondary flex-shrink-0">
                    {idx + 1}
                  </div>
                  <div className="w-12 h-12 bg-xy-gray-200 rounded border border-xy-border overflow-hidden flex-shrink-0">
                    {p.pic_url && <img src={p.pic_url} className="w-full h-full object-cover" alt="" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-xy-text-primary truncate">{p.title}</p>
                    <p className="text-xs text-xy-text-secondary mt-0.5">想要: {p.wants || 0} | 成交: {p.sales || 0} | 浏览: {p.views || 0}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-10 text-xy-text-muted">暂无商品数据</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
