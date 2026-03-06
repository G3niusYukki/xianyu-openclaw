import React from 'react'
import { Link } from 'react-router-dom'
import { Store, MessageCircle, PackagePlus, Receipt, Sparkles } from 'lucide-react'

const Home = () => {
  return (
    <div className="xy-page space-y-6 xy-enter">
      <section className="xy-card p-6 md:p-8 bg-gradient-to-br from-xy-brand-50 via-white to-blue-50">
        <p className="text-sm font-medium text-xy-brand-600 mb-2">闲鱼管家多店铺版</p>
        <h1 className="xy-title mb-3">让虚拟商品运营更轻松</h1>
        <p className="xy-subtitle mb-6 max-w-2xl">
          自动化上架、AI智能意图识别回复、多店铺账号隔离、订单自动催单降价，打造高效的虚拟电商工作流。
        </p>
        <div className="flex flex-wrap gap-3">
          <Link to="/products/auto-publish" className="xy-btn-primary px-5 py-3 font-semibold">快速上架</Link>
          <Link to="/dashboard" className="xy-btn-secondary px-5 py-3 font-semibold">进入工作台</Link>
        </div>
      </section>

      <section className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { to: '/products', title: '商品管理', desc: '支持快捷上下架与自动补货', icon: PackagePlus },
          { to: '/orders', title: '订单中心', desc: '未支付订单阶梯催单与改价', icon: Receipt },
          { to: '/messages', title: '即时聊天', desc: 'AI意图识别与自动报价引擎', icon: MessageCircle },
          { to: '/accounts', title: '多店铺管理', desc: '账号级环境隔离与独立配置', icon: Store }
        ].map((item) => (
          <Link key={item.title} to={item.to} className="xy-card p-5 hover:-translate-y-0.5 transition-transform duration-200 group">
            <item.icon className="w-6 h-6 text-xy-brand-500 mb-3 group-hover:scale-110 transition-transform" />
            <h2 className="font-semibold text-xy-text-primary mb-1">{item.title}</h2>
            <p className="text-sm text-xy-text-secondary">{item.desc}</p>
          </Link>
        ))}
      </section>

      <section className="xy-card-soft p-5 flex items-start gap-3 border-l-4 border-l-blue-500 bg-blue-50/50">
        <Sparkles className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-xy-text-secondary">
          当前系统已打通 Node.js 和 Python 双引擎，实现本地自动化抓取与云端闲管家 API 的结合。请先在「多店铺管理」中配置您的环境。
        </p>
      </section>
    </div>
  )
}

export default Home
