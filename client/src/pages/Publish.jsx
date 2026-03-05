import React from 'react'
import { AlertCircle, Camera, FileText } from 'lucide-react'

const Publish = () => {
  return (
    <div className="xy-page xy-enter space-y-5">
      <header>
        <h1 className="xy-title">发布商品</h1>
        <p className="xy-subtitle mt-1">任务流输入：先图后文再价格，降低发布失败率。</p>
      </header>

      <section className="xy-card p-6 space-y-5">
        <div className="xy-card-soft p-4 flex items-center gap-3">
          <Camera className="w-5 h-5 text-orange-500" />
          <span className="text-sm text-slate-700">图片上传区域（待接入真实上传接口）</span>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <label className="space-y-2">
            <span className="text-sm font-medium">标题</span>
            <input className="w-full rounded-xl border border-slate-200 px-3 py-2.5 bg-white" placeholder="请输入商品标题" />
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium">价格</span>
            <input className="w-full rounded-xl border border-slate-200 px-3 py-2.5 bg-white" placeholder="请输入价格" />
          </label>
        </div>

        <label className="space-y-2 block">
          <span className="text-sm font-medium">商品描述</span>
          <textarea rows={5} className="w-full rounded-xl border border-slate-200 px-3 py-2.5 bg-white" placeholder="补充成色、配件、交易方式等" />
        </label>

        <div className="flex flex-wrap gap-3">
          <button className="xy-btn-primary px-5 py-2.5 font-semibold inline-flex items-center gap-2">
            <FileText className="w-4 h-4" /> 提交发布
          </button>
          <button className="xy-btn-secondary px-5 py-2.5 font-semibold">存为草稿</button>
        </div>
      </section>

      <section className="xy-card-soft p-4 flex items-start gap-2">
        <AlertCircle className="w-4 h-4 mt-0.5 text-amber-600" />
        <p className="text-sm text-slate-700">未接入发布 API 前，提交按钮仅保留交互反馈，不创建任何假订单/假商品。</p>
      </section>
    </div>
  )
}

export default Publish
