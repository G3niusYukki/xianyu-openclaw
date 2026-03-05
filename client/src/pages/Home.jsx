import React from 'react'
import { Link } from 'react-router-dom'
import { Compass, MessageCircle, PackagePlus, Receipt, Sparkles } from 'lucide-react'

const Home = () => {
  return (
    <div className="xy-page space-y-6 xy-enter">
      <section className="xy-card p-6 md:p-8 bg-gradient-to-br from-orange-50 via-white to-blue-50">
        <p className="text-sm font-medium text-orange-600 mb-2">闲鱼风格化前端升级</p>
        <h1 className="xy-title mb-3">让交易体验更轻、更稳、更有温度</h1>
        <p className="xy-subtitle mb-6 max-w-2xl">
          首页采用「探索 + 行动入口」双层结构，减少决策负担；并统一详情、发布、聊天、订单的视觉语言。
        </p>
        <div className="flex flex-wrap gap-3">
          <Link to="/publish" className="xy-btn-primary px-5 py-3 font-semibold">立即发布</Link>
          <Link to="/orders" className="xy-btn-secondary px-5 py-3 font-semibold">查看订单</Link>
        </div>
      </section>

      <section className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { to: '/detail', title: '商品详情', desc: '信息层级清晰，CTA固定可见', icon: Compass },
          { to: '/publish', title: '发布商品', desc: '任务流表单，降低发布中断率', icon: PackagePlus },
          { to: '/chat', title: '即时聊天', desc: '会话优先，输入反馈即时可感', icon: MessageCircle },
          { to: '/orders', title: '订单中心', desc: '状态前置，异常处理一步直达', icon: Receipt }
        ].map((item) => (
          <Link key={item.title} to={item.to} className="xy-card p-5 hover:-translate-y-0.5 transition-transform duration-200">
            <item.icon className="w-6 h-6 text-orange-500 mb-3" />
            <h2 className="font-semibold text-slate-900 mb-1">{item.title}</h2>
            <p className="text-sm text-slate-600">{item.desc}</p>
          </Link>
        ))}
      </section>

      <section className="xy-card-soft p-5 flex items-start gap-3">
        <Sparkles className="w-5 h-5 text-blue-600 mt-0.5" />
        <p className="text-sm text-slate-700">
          当前版本以「设计 token + 页面规范」驱动，暂无真实业务数据时统一展示空状态，不使用任何 mock 数据。
        </p>
      </section>
    </div>
  )
}

export default Home
