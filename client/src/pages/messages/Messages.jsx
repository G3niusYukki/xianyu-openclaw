import React, { useState, useEffect } from 'react';
import { useCurrentAccount } from '../../contexts/AccountContext';
import { MessageCircle, Search, Send, Bot, User, Clock } from 'lucide-react';

export default function Messages() {
  const { currentAccountId } = useCurrentAccount();
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');

  // 模拟数据加载
  useEffect(() => {
    // 这里在真实业务中应调用 pyApi 去获取 WebSocket 会话列表
    // 或者连上前端的 WebSocket
    setSessions([
      { id: '1', name: '咸鱼买家123', itemTitle: '爱奇艺会员', lastMsg: '在吗？', time: '10:32', unread: 1 },
      { id: '2', name: '数码发烧友', itemTitle: '顺丰快递代发', lastMsg: '多少钱', time: '09:15', unread: 0 },
    ]);
  }, [currentAccountId]);

  useEffect(() => {
    if (activeSession) {
      // 模拟加载对话记录
      setMessages([
        { id: 1, sender: 'buyer', text: activeSession.lastMsg, time: '10:32', intent: '询价' },
        { id: 2, sender: 'bot', text: '在的，自动发货，请直接下单', time: '10:32' },
      ]);
    }
  }, [activeSession]);

  const handleSend = () => {
    if (!inputText.trim() || !activeSession) return;
    setMessages(prev => [...prev, { id: Date.now(), sender: 'me', text: inputText, time: new Date().toLocaleTimeString().slice(0,5) }]);
    setInputText('');
  };

  return (
    <div className="xy-page xy-enter max-w-6xl h-[calc(100vh-100px)]">
      <div className="xy-card flex h-full overflow-hidden">
        {/* 左侧会话列表 */}
        <div className="w-1/3 min-w-[280px] max-w-[320px] border-r border-xy-border flex flex-col bg-xy-gray-50">
          <div className="p-4 border-b border-xy-border bg-white">
            <h2 className="font-bold text-lg flex items-center gap-2 mb-3">
              <MessageCircle className="w-5 h-5 text-xy-brand-500" /> 会话中心
            </h2>
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-xy-text-muted" />
              <input 
                type="text" 
                placeholder="搜索买家名称" 
                className="xy-input pl-9 pr-3 py-1.5 text-sm bg-xy-gray-50"
              />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto">
            {sessions.map(s => (
              <button
                key={s.id}
                onClick={() => setActiveSession(s)}
                className={`w-full text-left p-4 border-b border-xy-border transition-colors ${
                  activeSession?.id === s.id ? 'bg-white border-l-4 border-l-xy-brand-500' : 'hover:bg-xy-gray-100 border-l-4 border-l-transparent'
                }`}
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="font-medium text-xy-text-primary truncate pr-2">{s.name}</span>
                  <span className="text-xs text-xy-text-muted flex-shrink-0">{s.time}</span>
                </div>
                <div className="text-xs text-xy-text-secondary truncate mb-1">商品: {s.itemTitle}</div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-xy-text-secondary truncate pr-2">{s.lastMsg}</span>
                  {s.unread > 0 && (
                    <span className="w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center flex-shrink-0">
                      {s.unread}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 右侧聊天区域 */}
        <div className="flex-1 flex flex-col bg-white">
          {activeSession ? (
            <>
              {/* Chat Header */}
              <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-white shadow-sm z-10">
                <div>
                  <h3 className="font-bold text-lg text-xy-text-primary">{activeSession.name}</h3>
                  <p className="text-sm text-xy-text-secondary flex items-center gap-1 mt-0.5">
                    商品: <span className="text-xy-brand-600">{activeSession.itemTitle}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 bg-green-50 text-green-700 rounded-full border border-green-200">
                  <Bot className="w-3.5 h-3.5" /> AI托管中
                </div>
              </div>

              {/* Messages Area */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-xy-gray-50/50">
                {messages.map(msg => {
                  const isMe = msg.sender === 'me' || msg.sender === 'bot';
                  return (
                    <div key={msg.id} className={`flex gap-3 ${isMe ? 'flex-row-reverse' : ''}`}>
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                        msg.sender === 'buyer' ? 'bg-blue-100 text-blue-600' :
                        msg.sender === 'bot' ? 'bg-orange-100 text-orange-600' :
                        'bg-xy-gray-200 text-xy-gray-600'
                      }`}>
                        {msg.sender === 'buyer' ? <User className="w-5 h-5" /> :
                         msg.sender === 'bot' ? <Bot className="w-5 h-5" /> : 
                         <User className="w-5 h-5" />}
                      </div>
                      
                      <div className={`flex flex-col ${isMe ? 'items-end' : 'items-start'} max-w-[70%]`}>
                        <div className="flex items-center gap-2 mb-1 px-1 text-xs text-xy-text-muted">
                          {msg.sender === 'bot' && <span className="text-orange-500 font-medium">自动回复</span>}
                          {msg.intent && <span className="bg-xy-gray-200 px-1.5 py-0.5 rounded text-xy-gray-600">意图: {msg.intent}</span>}
                          <span>{msg.time}</span>
                        </div>
                        <div className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
                          isMe 
                            ? 'bg-xy-brand-500 text-white rounded-tr-sm' 
                            : 'bg-white border border-xy-border text-xy-text-primary rounded-tl-sm'
                        }`}>
                          {msg.text}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Input Area */}
              <div className="p-4 bg-white border-t border-xy-border">
                <div className="flex gap-3 items-end">
                  <textarea 
                    className="flex-1 xy-input py-3 px-4 resize-none h-[80px]"
                    placeholder="人工接管回复..."
                    value={inputText}
                    onChange={e => setInputText(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                  />
                  <button 
                    onClick={handleSend}
                    disabled={!inputText.trim()}
                    className="xy-btn-primary h-[80px] px-6"
                  >
                    <Send className="w-5 h-5" />
                  </button>
                </div>
                <div className="flex justify-between items-center mt-2 px-1">
                  <p className="text-xs text-xy-text-muted flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" /> 人工回复将自动暂停该会话的 AI 托管 30 分钟
                  </p>
                  <p className="text-xs text-xy-text-muted">Enter 发送，Shift+Enter 换行</p>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-xy-text-muted bg-xy-gray-50/30">
              <MessageCircle className="w-16 h-16 mb-4 text-xy-gray-200" />
              <p>在左侧选择一个会话开始聊天</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
