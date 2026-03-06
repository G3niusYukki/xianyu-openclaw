import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useCurrentAccount } from '../contexts/AccountContext'
import { getDashboardSummary, getRecentOperations, getSystemStatus } from '../api/dashboard'
import { Store, ShoppingBag, MessageCircle, FileText, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'

const Dashboard = () => {
  const { user } = useAuth()
  const { currentAccount, currentAccountId, accounts } = useCurrentAccount()
  
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
    // 监听账号切换事件
    const handleAccountSwitched = () => fetchDashboardData();
    window.addEventListener('accountSwitched', handleAccountSwitched);
    
    fetchDashboardData()

    return () => window.removeEventListener('accountSwitched', handleAccountSwitched);
  }, [currentAccountId])

  const fetchDashboardData = async () => {
    try {
      setLoading(true)
      const [summaryRes, opsRes, statusRes] = await Promise.all([
        getDashboardSummary(),
        getRecentOperations(10),
        getSystemStatus()
      ]).catch(e => {
        console.error("Some dashboard API failed", e);
        return [{}, {}, {}];
      });

      if (summaryRes?.data) {
        setStats({
          products: summaryRes.data.published_count || summaryRes.data.active_products || 0,
          orders: summaryRes.data.orders_created || 0,
          messages: summaryRes.data.unread_messages || 0,
          replies: summaryRes.data.auto_replies || 0
        })
      }
      
      if (opsRes?.data?.operations) {
        setRecentOps(opsRes.data.operations)
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

  const getAccountStatusColor = (status) => {
    if (status === 'good') return 'text-xy-success';
    if (status === 'warning') return 'text-xy-warning';
    return 'text-xy-error';
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-64px)]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-xy-brand-500"></div>
      </div>
    )
  }

  const myAccountStatus = sysStatus?.modules?.account_health?.details?.[currentAccountId] || { health_score: 100, status: 'good' };

  return (
    <div className="xy-page xy-enter">
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-xy-text-primary">
            欢迎回来，{user.username}
          </h1>
          <p className="mt-2 text-xy-text-secondary">
            当前操作店铺：<span className="font-medium text-xy-brand-600">{currentAccount?.name || '未选择'}</span>
          </p>
        </div>
        <div className="flex gap-4">
          <div className="flex items-center gap-2 bg-xy-surface px-4 py-2 rounded-xl border border-xy-border shadow-sm">
            <div className={`w-2 h-2 rounded-full ${myAccountStatus.status === 'good' ? 'bg-green-500' : 'bg-yellow-500'}`}></div>
            <span className="text-sm font-medium">Cookie: {myAccountStatus.health_score}分</span>
          </div>
          <button onClick={fetchDashboardData} className="p-2 bg-xy-surface border border-xy-border rounded-xl shadow-sm hover:bg-xy-gray-50 transition-colors">
            <RefreshCw className="w-5 h-5 text-xy-text-secondary" />
          </button>
        </div>
      </div>

      {/* 核心数据指标 */}
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
          <p className="text-sm font-medium text-xy-text-secondary mb-1">自动回复</p>
          <p className="text-2xl md:text-3xl font-bold text-xy-text-primary">{stats.replies}</p>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-8">
        {/* 左侧：最近操作记录 */}
        <div className="md:col-span-2 xy-card overflow-hidden">
          <div className="px-6 py-4 border-b border-xy-border bg-xy-gray-50 flex justify-between items-center">
            <h2 className="text-base font-semibold text-xy-text-primary">近期自动化操作</h2>
            <Link to="/logs" className="text-sm text-xy-brand-500 hover:text-xy-brand-600 font-medium">查看完整日志 &rarr;</Link>
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

        {/* 右侧：快捷入口和状态 */}
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

              <Link to="/accounts" className="flex items-center justify-between p-3 rounded-xl border border-xy-border hover:border-green-500 hover:bg-green-50 transition-colors group">
                <div className="flex items-center gap-3">
                  <div className="bg-green-100 p-2 rounded-lg group-hover:bg-green-200 transition-colors">
                    <Settings className="w-5 h-5 text-green-600" />
                  </div>
                  <span className="font-medium text-xy-text-primary">店铺配置</span>
                </div>
                <span className="text-green-500">&rarr;</span>
              </Link>
            </div>
          </div>

          <div className="xy-card p-6 bg-gradient-to-br from-xy-gray-900 to-xy-gray-800 text-white">
            <h3 className="font-semibold mb-2">系统运行状态</h3>
            <div className="space-y-3 mt-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">模块网关</span>
                <span className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${sysStatus?.modules?.account_health ? 'bg-green-400' : 'bg-red-400'}`}></div>
                  {sysStatus?.modules?.account_health ? '运行中' : '异常'}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">总店铺数</span>
                <span className="font-medium">{accounts.length} 个</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
