import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardSummary, getRecentOperations, getSystemStatus } from '../api/dashboard'
import { Store, ShoppingBag, MessageCircle, FileText, CheckCircle, AlertCircle, RefreshCw, Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import SetupGuide from '../components/SetupGuide'

const Dashboard = () => {
  const [stats, setStats] = useState({
    products: 0,
    orders: 0,
    messages: 0,
    replies: 0
  })
  const [recentOps, setRecentOps] = useState([])
  const [sysStatus, setSysStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDashboardData()
  }, [])

  const fetchDashboardData = async () => {
    try {
      setLoading(true)
      const results = await Promise.allSettled([
        getDashboardSummary(),
        getRecentOperations(10),
        getSystemStatus()
      ]);
      const summaryRes = results[0].status === 'fulfilled' ? results[0].value : null;
      const opsRes = results[1].status === 'fulfilled' ? results[1].value : null;
      const statusRes = results[2].status === 'fulfilled' ? results[2].value : null;
      const failedCount = results.filter(r => r.status === 'rejected').length;
      if (failedCount === results.length) {
        throw new Error('所有仪表盘接口均请求失败');
      }

      if (summaryRes?.data) {
        const s = summaryRes.data?.data || summaryRes.data;
        const messageStats = statusRes?.data?.message_stats || {};
        const orderSummary = statusRes?.data?.order_summary || {};
        setStats({
          products: s.active_products ?? 0,
          orders: orderSummary.total_orders ?? 0,
          messages: messageStats.total_conversations ?? 0,
          replies: messageStats.today_replied ?? 0
        })
      }
      
      if (opsRes?.data) {
        const ops = Array.isArray(opsRes.data) ? opsRes.data : (opsRes.data.operations || []);
        setRecentOps(ops.map(op => ({
          action: op.operation_type || op.action || '未知操作',
          success: op.status === 'success' || op.status === 'completed',
          timestamp: op.timestamp || '',
          message: op.message || `商品 ${op.product_id || ''}`
        })))
      }
      
      if (statusRes?.data) {
        setSysStatus(statusRes.data)
      }

    } catch (error) {
      console.error('Failed to fetch dashboard data:', error)
      toast.error('获取仪表盘数据失败')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-64px)]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-xy-brand-500"></div>
      </div>
    )
  }

  const cookieHealth = {
    health_score: sysStatus?.cookie_health?.score ?? 0,
    status: sysStatus?.cookie_health?.status ?? 'bad',
  };

  return (
    <div className="xy-page xy-enter">
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-xy-text-primary">工作台</h1>
          <p className="mt-2 text-xy-text-secondary">闲鱼自动化运营概览</p>
        </div>
        <div className="flex gap-4">
          <div className="flex items-center gap-2 bg-xy-surface px-4 py-2 rounded-xl border border-xy-border shadow-sm">
            <div className={`w-2 h-2 rounded-full ${cookieHealth.status === 'good' ? 'bg-green-500' : 'bg-yellow-500'}`}></div>
            <span className="text-sm font-medium">Cookie: {cookieHealth.health_score ?? 100}分</span>
          </div>
          <button onClick={fetchDashboardData} className="p-2 bg-xy-surface border border-xy-border rounded-xl shadow-sm hover:bg-xy-gray-50 transition-colors" aria-label="刷新数据">
            <RefreshCw className="w-5 h-5 text-xy-text-secondary" />
          </button>
        </div>
      </div>

      <SetupGuide />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6 mb-8">
        <div className="xy-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="p-3 bg-xy-brand-50 rounded-xl">
              <ShoppingBag className="h-6 w-6 text-xy-brand-500" />
            </div>
          </div>
          <p className="text-sm font-medium text-xy-text-secondary mb-1">在售商品</p>
          <p className="text-2xl md:text-3xl font-bold text-xy-text-primary">{stats.products}</p>
        </div>

        <div className="xy-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="p-3 bg-blue-50 rounded-xl">
              <FileText className="h-6 w-6 text-blue-500" />
            </div>
          </div>
          <p className="text-sm font-medium text-xy-text-secondary mb-1">今日订单</p>
          <p className="text-2xl md:text-3xl font-bold text-xy-text-primary">{stats.orders}</p>
        </div>

        <div className="xy-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="p-3 bg-red-50 rounded-xl">
              <MessageCircle className="h-6 w-6 text-red-500" />
            </div>
          </div>
          <p className="text-sm font-medium text-xy-text-secondary mb-1">未读消息</p>
          <p className="text-2xl md:text-3xl font-bold text-xy-text-primary">{stats.messages}</p>
        </div>

        <div className="xy-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="p-3 bg-green-50 rounded-xl">
              <CheckCircle className="h-6 w-6 text-green-500" />
            </div>
          </div>
          <p className="text-sm font-medium text-xy-text-secondary mb-1">今日自动回复</p>
          <p className="text-2xl md:text-3xl font-bold text-xy-text-primary">{stats.replies}</p>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-8">
        <div className="md:col-span-2 xy-card overflow-hidden">
          <div className="px-6 py-4 border-b border-xy-border bg-xy-gray-50 flex justify-between items-center">
            <h2 className="text-base font-semibold text-xy-text-primary">近期自动化操作</h2>
            <Link to="/analytics" className="text-sm text-xy-brand-500 hover:text-xy-brand-600 font-medium">查看完整日志 &rarr;</Link>
          </div>
          
          <div className="divide-y divide-xy-border">
            {recentOps.length === 0 ? (
              <div className="p-8 text-center">
                <AlertCircle className="h-10 w-10 text-xy-gray-300 mx-auto mb-3" />
                <p className="text-xy-text-secondary">暂无近期操作记录</p>
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
                    <p className="text-sm text-xy-text-secondary truncate">
                      {op.message || JSON.stringify(op.details || {})}
                    </p>
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
                  <div className="bg-orange-100 p-2 rounded-lg group-hover:bg-orange-200 transition-colors">
                    <Store className="w-5 h-5 text-xy-brand-600" />
                  </div>
                  <span className="font-medium text-xy-text-primary">自动上架</span>
                </div>
                <span className="text-xy-brand-500">&rarr;</span>
              </Link>
              
              <Link to="/messages" className="flex items-center justify-between p-3 rounded-xl border border-xy-border hover:border-blue-500 hover:bg-blue-50 transition-colors group">
                <div className="flex items-center gap-3">
                  <div className="bg-blue-100 p-2 rounded-lg group-hover:bg-blue-200 transition-colors">
                    <MessageCircle className="w-5 h-5 text-blue-600" />
                  </div>
                  <span className="font-medium text-xy-text-primary">消息中心</span>
                </div>
                <span className="text-blue-500">&rarr;</span>
              </Link>

              <Link to="/config" className="flex items-center justify-between p-3 rounded-xl border border-xy-border hover:border-green-500 hover:bg-green-50 transition-colors group">
                <div className="flex items-center gap-3">
                  <div className="bg-green-100 p-2 rounded-lg group-hover:bg-green-200 transition-colors">
                    <Settings className="w-5 h-5 text-green-600" />
                  </div>
                  <span className="font-medium text-xy-text-primary">系统配置</span>
                </div>
                <span className="text-green-500">&rarr;</span>
              </Link>
            </div>
          </div>

          <div className="xy-card p-6 bg-gradient-to-br from-xy-gray-900 to-xy-gray-800 text-white">
            <h3 className="font-semibold mb-2">系统运行状态</h3>
            <div className="space-y-3 mt-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">服务状态</span>
                <span className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${sysStatus ? 'bg-green-400' : 'bg-red-400'}`}></div>
                  {sysStatus?.service_status === 'running' ? '运行中' : sysStatus?.service_status === 'degraded' ? '降级' : '异常'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
