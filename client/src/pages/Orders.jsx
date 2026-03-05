import React from 'react'
import { PackageSearch, RefreshCcw } from 'lucide-react'

const Orders = () => {
  return (
    <div className="xy-page xy-enter space-y-5">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="xy-title">订单中心</h1>
          <p className="xy-subtitle mt-1">状态优先展示：待付款、待发货、待收货、已完成。</p>
        </div>
        <button className="xy-btn-secondary px-4 py-2 inline-flex items-center gap-2 text-sm">
          <RefreshCcw className="w-4 h-4" /> 刷新
        </button>
      </header>

      <section className="xy-card p-6">
        <div className="grid md:grid-cols-4 gap-3 mb-5">
          {['待付款', '待发货', '待收货', '已完成'].map((status) => (
            <div key={status} className="xy-card-soft p-3 text-sm font-medium text-slate-700">{status}</div>
          ))}
        </div>

        <div className="rounded-2xl border border-dashed border-slate-300 py-14 grid place-items-center text-center">
          <div>
            <PackageSearch className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <p className="text-slate-700 font-medium">暂无订单数据</p>
            <p className="text-sm text-slate-500 mt-1">接入真实订单 API 后将展示分页列表与异常处理入口。</p>
          </div>
        </div>
      </section>
    </div>
  )
}

export default Orders
