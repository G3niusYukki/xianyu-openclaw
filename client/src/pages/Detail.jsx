import React from 'react'
import { Heart, MessageCircle, ShieldCheck } from 'lucide-react'

const Detail = () => {
  return (
    <div className="xy-page xy-enter">
      <div className="grid lg:grid-cols-5 gap-6">
        <section className="lg:col-span-3 xy-card p-4 md:p-6">
          <div className="aspect-[4/3] rounded-2xl bg-slate-100 grid place-items-center text-slate-400 text-sm">
            暂无商品图片
          </div>
          <h1 className="text-2xl font-bold mt-5 mb-2">商品详情</h1>
          <p className="text-slate-600 leading-relaxed">
            当前暂无真实商品数据。接入 API 后将按「标题 → 价格 → 成色与交易方式 → 卖家承诺」顺序渲染，避免信息噪音。
          </p>
        </section>

        <aside className="lg:col-span-2 space-y-4">
          <div className="xy-card p-5">
            <p className="text-sm text-slate-500 mb-1">当前价格</p>
            <p className="text-3xl font-bold text-orange-600">--</p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button className="xy-btn-secondary py-2.5 font-medium inline-flex items-center justify-center gap-2">
                <Heart className="w-4 h-4" /> 收藏
              </button>
              <button className="xy-btn-primary py-2.5 font-medium inline-flex items-center justify-center gap-2">
                <MessageCircle className="w-4 h-4" /> 聊一聊
              </button>
            </div>
          </div>

          <div className="xy-card-soft p-4">
            <div className="flex items-center gap-2 text-blue-700 font-medium mb-1">
              <ShieldCheck className="w-4 h-4" /> 交易保障
            </div>
            <p className="text-sm text-slate-600">页面已预留保障信息区，后端可直接映射服务承诺标签。</p>
          </div>
        </aside>
      </div>
    </div>
  )
}

export default Detail
