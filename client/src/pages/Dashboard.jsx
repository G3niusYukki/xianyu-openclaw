import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardSummary, getRecentOperations, getSystemStatus } from '../api/dashboard'
import { Store, ShoppingBag, MessageCircle, FileText, CheckCircle, AlertCircle, RefreshCw, Settings, Zap, Bot, BarChart3, Clock, Package } from 'lucide-react'
import toast from 'react-hot-toast'
import SetupGuide from '../components/SetupGuide'
import ApiStatusPanel from '../components/ApiStatusPanel'

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
        const s = summaryRes.data;
        setStats({
          products: s.active_products ?? 0,
          orders: s.today_orders ?? s.today_operations ?? 0,
          messages: s.unread_messages ?? s.total_wants ?? 0,
          replies: s.today_replies ?? s.total_sales ?? 0
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

  const cookieHealth = sysStatus?.modules?.account_health?.details?.default || { health_score: 100, status: 'good' };

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

      <div className="xy-card mb-8 overflow-hidden">
        <div className="px-6 py-4 border-b border-xy-border bg-gradient-to-r from-xy-gray-900 to-xy-gray-800">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-400" /> 核心功能
          </h2>
          <p className="text-sm text-gray-400 mt-1">闲鱼虚拟商品卖家自动化工作台</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-xy-border">
          <div className="p-5 text-center hover:bg-xy-gray-50 transition-colors">
            <Bot className="w-7 h-7 text-blue-500 mx-auto mb-2" />
            <p className="text-sm font-semibold text-xy-text-primary">AI 智能回复</p>
            <p className="text-xs text-xy-text-secondary mt-1">自动识别买家意图，智能生成回复</p>
          </div>
          <div className="p-5 text-center hover:bg-xy-gray-50 transition-colors">
            <Package className="w-7 h-7 text-orange-500 mx-auto mb-2" />
            <p className="text-sm font-semibold text-xy-text-primary">自动上架</p>
            <p className="text-xs text-xy-text-secondary mt-1">批量生成商品描述并一键上架</p>
          </div>
          <div className="p-5 text-center hover:bg-xy-gray-50 transition-colors">
            <Clock className="w-7 h-7 text-green-500 mx-auto mb-2" />
            <p className="text-sm font-semibold text-xy-text-primary">自动发货</p>
            <p className="text-xs text-xy-text-secondary mt-1">虚拟商品订单自动确认并发货</p>
          </div>
          <div className="p-5 text-center hover:bg-xy-gray-50 transition-colors">
            <BarChart3 className="w-7 h-7 text-purple-500 mx-auto mb-2" />
            <p className="text-sm font-semibold text-xy-text-primary">数据分析</p>
            <p className="text-xs text-xy-text-secondary mt-1">商品销量、消息量等运营数据统计</p>
          </div>
          <button onClick={fetchDashboardData} className="p-2 bg-xy-surface border border-xy-border rounded-xl shadow-sm hover:bg-xy-gray-50 transition-colors" aria-label="刷新数据">
            <RefreshCw className="w-5 h-5 text-xy-text-secondary" />
          </button>
        </div>
      </div>

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

          <ApiStatusPanel />
        </div>
      </div>
    </div>
  )
}

export default Dashboard
