import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardSummary, getRecentOperations, getSystemStatus, getTrendData, getTopProducts } from '../api/dashboard'
import { Store, ShoppingBag, MessageCircle, FileText, CheckCircle, AlertCircle, RefreshCw, Settings, Zap, Bot, BarChart3, Clock, Package, TrendingUp, Calendar } from 'lucide-react'
import toast from 'react-hot-toast'
import SetupGuide from '../components/SetupGuide'
import ApiStatusPanel from '../components/ApiStatusPanel'
import { useStoreCategory } from '../contexts/StoreCategoryContext'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'

const TABS = [
  { key: 'overview', label: '概览' },
  { key: 'analytics', label: '数据分析' },
];

const Dashboard = () => {
  const { category, meta } = useStoreCategory();
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState({ products: 0, orders: 0, messages: 0, replies: 0 });
  const [recentOps, setRecentOps] = useState([]);
  const [sysStatus, setSysStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const [metric, setMetric] = useState('views');
  const [days, setDays] = useState(30);
  const [trendData, setTrendData] = useState([]);
  const [topProducts, setTopProducts] = useState([]);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  useEffect(() => { fetchDashboardData() }, []);

  useEffect(() => {
    if (activeTab === 'analytics') fetchAnalyticsData();
  }, [activeTab, metric, days]);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const results = await Promise.allSettled([
        getDashboardSummary(), getRecentOperations(10), getSystemStatus()
      ]);
      const [summaryRes, opsRes, statusRes] = results.map(r => r.status === 'fulfilled' ? r.value : null);
      if (results.every(r => r.status === 'rejected')) throw new Error('所有接口均请求失败');

      if (summaryRes?.data) {
        const raw = summaryRes.data.data || summaryRes.data;
        setStats({
          products: raw.active_products ?? 0,
          orders: raw.today_operations ?? 0,
          messages: raw.total_wants ?? 0,
          replies: raw.total_sales ?? 0
        });
      }
      if (opsRes?.data) {
        const ops = Array.isArray(opsRes.data) ? opsRes.data : (opsRes.data.operations || []);
        setRecentOps(ops.map(op => ({
          action: op.operation_type || op.action || '未知操作',
          success: op.status === 'success' || op.status === 'completed',
          timestamp: op.timestamp || '',
          message: op.message || `商品 ${op.product_id || ''}`
        })));
      }
      if (statusRes?.data) setSysStatus(statusRes.data);
    } catch (error) {
      console.error('Dashboard fetch failed:', error);
      toast.error('获取仪表盘数据失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalyticsData = async () => {
    setAnalyticsLoading(true);
    try {
      const [trendRes, topRes] = await Promise.all([getTrendData(metric, days), getTopProducts(10)]);
      if (trendRes.data) {
        const td = trendRes.data.data || trendRes.data;
        setTrendData(Array.isArray(td) ? td : (td.trend || []));
      }
      if (topRes.data) {
        const tp = topRes.data.data || topRes.data;
        setTopProducts(Array.isArray(tp) ? tp : (tp.products || []));
      }
    } catch { toast.error('加载分析数据失败'); }
    finally { setAnalyticsLoading(false); }
  };

  if (loading) {
    return (
      <div className="xy-page p-6 xy-enter">
        <div className="flex justify-between mb-6">
          <div className="w-1/3">
            <div className="h-8 bg-xy-gray-200 rounded-lg w-1/2 mb-3 animate-pulse"></div>
            <div className="h-4 bg-xy-gray-200 rounded w-1/3 animate-pulse"></div>
          </div>
          <div className="flex gap-3">
            <div className="h-10 bg-xy-gray-200 rounded-xl w-32 animate-pulse"></div>
            <div className="h-10 bg-xy-gray-200 rounded-xl w-10 animate-pulse"></div>
          </div>
        </div>
        <div className="h-10 bg-xy-gray-200 rounded-xl w-48 mb-6 animate-pulse"></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6 mb-8">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="xy-card p-6 h-32 bg-xy-gray-100 animate-pulse border-none"></div>
          ))}
        </div>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="md:col-span-2 xy-card h-96 bg-xy-gray-100 animate-pulse border-none"></div>
          <div className="space-y-6">
            <div className="xy-card h-64 bg-xy-gray-100 animate-pulse border-none"></div>
            <div className="xy-card h-32 bg-xy-gray-100 animate-pulse border-none"></div>
          </div>
        </div>
      </div>
    );
  }

  const ckh = sysStatus?.cookie_health || {};
  const cookieHealth = {
    health_score: ckh.score ?? 100,
    status: ckh.healthy === false ? 'warning' : 'good',
  };

  return (
    <div className="xy-page xy-enter">
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-xy-text-primary">工作台</h1>
          <p className="mt-1 text-xy-text-secondary flex items-center gap-2">
            <span>{meta.icon} {meta.label}</span>
            <span className="text-xy-gray-300">|</span>
            闲鱼自动化运营概览
          </p>
        </div>
        <div className="flex gap-3">
          <div className="flex items-center gap-2 bg-xy-surface px-4 py-2 rounded-xl border border-xy-border shadow-sm">
            <div className={`w-2 h-2 rounded-full ${cookieHealth.status === 'good' ? 'bg-green-500' : 'bg-yellow-500'}`}></div>
            <span className="text-sm font-medium">Cookie: {cookieHealth.health_score ?? 100}分</span>
          </div>
          <button onClick={() => { fetchDashboardData(); if (activeTab === 'analytics') fetchAnalyticsData(); }} className="p-2 bg-xy-surface border border-xy-border rounded-xl shadow-sm hover:bg-xy-gray-50 transition-colors" aria-label="刷新数据">
            <RefreshCw className="w-5 h-5 text-xy-text-secondary" />
          </button>
        </div>
      </div>

      <SetupGuide />

      {/* Tabs */}
      <div className="flex bg-xy-gray-100 p-1 rounded-xl mb-6 w-fit">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-5 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === t.key ? 'bg-white shadow-sm text-xy-text-primary' : 'text-xy-text-secondary hover:text-xy-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6 mb-8">
            {[
              { label: '在售商品', value: stats.products, icon: ShoppingBag, color: 'bg-xy-brand-50', iconColor: 'text-xy-brand-500' },
              { label: '今日操作', value: stats.orders, icon: FileText, color: 'bg-blue-50', iconColor: 'text-blue-500' },
              { label: '总想要数', value: stats.messages, icon: MessageCircle, color: 'bg-red-50', iconColor: 'text-red-500' },
              { label: '总成交数', value: stats.replies, icon: CheckCircle, color: 'bg-green-50', iconColor: 'text-green-500' },
            ].map(card => (
              <div key={card.label} className="xy-card p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className={`p-3 ${card.color} rounded-xl`}>
                    <card.icon className={`h-6 w-6 ${card.iconColor}`} />
                  </div>
                </div>
                <p className="text-sm font-medium text-xy-text-secondary mb-1">{card.label}</p>
                <p className="text-2xl md:text-3xl font-bold text-xy-text-primary">{card.value}</p>
              </div>
            ))}
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <div className="md:col-span-2 xy-card overflow-hidden">
              <div className="px-6 py-4 border-b border-xy-border bg-xy-gray-50 flex justify-between items-center">
                <h2 className="text-base font-semibold text-xy-text-primary">近期自动化操作</h2>
                <button onClick={() => setActiveTab('analytics')} className="text-sm text-xy-brand-500 hover:text-xy-brand-600 font-medium">查看数据分析 &rarr;</button>
              </div>
              <div className="divide-y divide-xy-border">
                {recentOps.length === 0 ? (
                  <div className="p-12 flex flex-col items-center justify-center text-center">
                    <div className="w-16 h-16 bg-xy-gray-50 rounded-full flex items-center justify-center mb-4">
                      <Clock className="w-8 h-8 text-xy-gray-400" />
                    </div>
                    <p className="text-base font-medium text-xy-text-primary mb-1">暂无近期操作</p>
                    <p className="text-sm text-xy-text-secondary">系统自动执行的操作会显示在这里</p>
                  </div>
                ) : (
                  recentOps.map((op, idx) => (
                    <div key={idx} className="p-4 hover:bg-xy-gray-50 transition flex items-start gap-4">
                      <div className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${op.success ? 'bg-green-500' : 'bg-red-500'}`}></div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-xy-text-primary">{op.action}</span>
                          <span className="text-xs text-xy-text-secondary">{op.timestamp}</span>
                        </div>
                        <p className="text-sm text-xy-text-secondary truncate">{op.message}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="space-y-6">
              <div className="xy-card p-6">
                <h3 className="text-base font-semibold text-xy-text-primary mb-4">快捷操作</h3>
                <div className="space-y-3">
                  <Link to="/products/auto-publish" className="flex items-center justify-between p-3 rounded-xl border border-xy-border hover:border-xy-brand-500 hover:bg-xy-brand-50 transition-colors group">
                    <div className="flex items-center gap-3">
                      <div className="bg-orange-100 p-2 rounded-lg group-hover:bg-orange-200 transition-colors"><Store className="w-5 h-5 text-xy-brand-600" /></div>
                      <span className="font-medium text-xy-text-primary">自动上架</span>
                    </div>
                    <span className="text-xy-brand-500">&rarr;</span>
                  </Link>
                  <Link to="/messages" className="flex items-center justify-between p-3 rounded-xl border border-xy-border hover:border-blue-500 hover:bg-blue-50 transition-colors group">
                    <div className="flex items-center gap-3">
                      <div className="bg-blue-100 p-2 rounded-lg group-hover:bg-blue-200 transition-colors"><MessageCircle className="w-5 h-5 text-blue-600" /></div>
                      <span className="font-medium text-xy-text-primary">消息中心</span>
                    </div>
                    <span className="text-blue-500">&rarr;</span>
                  </Link>
                  <Link to="/config" className="flex items-center justify-between p-3 rounded-xl border border-xy-border hover:border-green-500 hover:bg-green-50 transition-colors group">
                    <div className="flex items-center gap-3">
                      <div className="bg-green-100 p-2 rounded-lg group-hover:bg-green-200 transition-colors"><Settings className="w-5 h-5 text-green-600" /></div>
                      <span className="font-medium text-xy-text-primary">系统配置</span>
                    </div>
                    <span className="text-green-500">&rarr;</span>
                  </Link>
                </div>
              </div>
              <ApiStatusPanel />
            </div>
          </div>
        </>
      )}

      {activeTab === 'analytics' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-bold text-xy-text-primary flex items-center gap-2"><BarChart3 className="w-5 h-5 text-xy-brand-500" /> 数据分析</h2>
            <div className="flex gap-2">
              <select className="xy-input py-1.5 px-3 text-sm bg-white" value={days} onChange={e => setDays(Number(e.target.value))}>
                <option value={7}>过去 7 天</option>
                <option value={30}>过去 30 天</option>
                <option value={90}>过去 90 天</option>
              </select>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 xy-card p-6">
              <div className="flex justify-between items-center mb-6">
                <h3 className="font-bold text-xy-text-primary">核心指标趋势</h3>
                <div className="flex bg-xy-gray-100 p-1 rounded-lg">
                  {[{ id: 'views', label: '浏览量' }, { id: 'wants', label: '想要数' }, { id: 'sales', label: '成交量' }].map(m => (
                    <button key={m.id} onClick={() => setMetric(m.id)} className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${metric === m.id ? 'bg-white shadow-sm text-xy-text-primary' : 'text-xy-text-secondary hover:text-xy-text-primary'}`}>
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="h-64 mt-4 relative">
                {analyticsLoading ? (
                  <div className="absolute inset-0 z-10 flex items-end gap-2 p-4 bg-white/80">
                    {[...Array(7)].map((_, i) => (
                      <div key={i} className="flex-1 bg-xy-gray-100 rounded-t-md animate-pulse" style={{ height: `${Math.max(20, Math.random() * 100)}%` }}></div>
                    ))}
                  </div>
                ) : trendData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={trendData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                      <XAxis dataKey="date" tickFormatter={v => v.slice(5)} tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                      <Tooltip labelFormatter={v => `日期: ${v}`} contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 13 }} />
                      <Bar dataKey="value" fill="#f97316" radius={[4, 4, 0, 0]} name={metric === 'views' ? '浏览量' : metric === 'wants' ? '想要数' : '成交量'} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-center">
                    <div className="w-12 h-12 bg-xy-gray-50 rounded-full flex items-center justify-center mb-3">
                      <Calendar className="w-6 h-6 text-xy-gray-400" />
                    </div>
                    <p className="text-sm font-medium text-xy-text-primary mb-1">暂无趋势数据</p>
                    <p className="text-xs text-xy-text-secondary">当前所选时间段内没有记录</p>
                  </div>
                )}
              </div>
            </div>

            <div className="xy-card p-0 overflow-hidden flex flex-col">
              <div className="px-6 py-4 border-b border-xy-border bg-xy-gray-50 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-green-500" />
                <h3 className="font-bold text-xy-text-primary">近期爆款商品</h3>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {analyticsLoading ? (
                  <div className="text-center py-8 text-xy-text-muted">加载中...</div>
                ) : topProducts.length > 0 ? (
                  topProducts.map((p, idx) => (
                    <div key={idx} className="flex gap-3 items-center">
                      <div className="w-6 h-6 rounded-full bg-xy-gray-100 flex items-center justify-center text-xs font-bold text-xy-text-secondary flex-shrink-0">{idx + 1}</div>
                      <div className="w-12 h-12 bg-xy-gray-200 rounded border border-xy-border overflow-hidden flex-shrink-0 flex items-center justify-center">
                        {p.pic_url ? <img src={p.pic_url} className="w-full h-full object-cover" alt="" /> : <Package className="w-5 h-5 text-xy-gray-400" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-xy-text-primary truncate">{p.title}</p>
                        <p className="text-xs text-xy-text-secondary mt-0.5">想要: {p.wants || 0} | 成交: {p.sales || 0} | 浏览: {p.views || 0}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <div className="w-12 h-12 bg-xy-gray-50 rounded-full flex items-center justify-center mb-3">
                      <Package className="w-6 h-6 text-xy-gray-400" />
                    </div>
                    <p className="text-sm font-medium text-xy-text-primary mb-1">暂无商品数据</p>
                    <p className="text-xs text-xy-text-secondary">暂时没有产生数据的爆款商品</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Dashboard
