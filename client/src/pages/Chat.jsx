import React from 'react'
import { SendHorizontal } from 'lucide-react'

const Chat = () => {
  return (
    <div className="xy-page xy-enter">
      <div className="xy-card overflow-hidden grid lg:grid-cols-[320px_1fr] min-h-[68vh]">
        <aside className="border-r border-slate-200 bg-slate-50 p-4">
          <h2 className="font-semibold mb-3">会话列表</h2>
          <div className="xy-card-soft p-3 text-sm text-slate-600">暂无会话，待消息服务接入。</div>
        </aside>

        <section className="flex flex-col">
          <header className="px-5 py-4 border-b border-slate-200">
            <h1 className="font-semibold">聊天窗口</h1>
            <p className="text-sm text-slate-500">消息时间轴与已读状态将由真实消息接口驱动。</p>
          </header>
          <div className="flex-1 p-5 bg-white" />
          <footer className="p-4 border-t border-slate-200 bg-white">
            <div className="flex gap-3">
              <input className="flex-1 rounded-xl border border-slate-200 px-3 py-2.5" placeholder="输入消息..." />
              <button className="xy-btn-primary px-4 inline-flex items-center gap-2">
                <SendHorizontal className="w-4 h-4" /> 发送
              </button>
            </div>
          </footer>
        </section>
      </div>
    </div>
  )
}

export default Chat
