import React, { useState, useEffect, useCallback } from 'react';
import { pyApi } from '../../api/index';
import {
  MessageCircle, Send, Bot, User, Clock,
  RefreshCw, BarChart3, MessagesSquare, Zap,
  AlertCircle, Activity,
} from 'lucide-react';

export default function Messages() {
  const [stats, setStats] = useState(null);
  const [replies, setReplies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [inputText, setInputText] = useState('');
  const [localMessages, setLocalMessages] = useState([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, repliesRes] = await Promise.all([
        pyApi.get('/api/status'),
        pyApi.get('/api/replies'),
      ]);
      setStats(statusRes.data.message_stats || null);
      setReplies(Array.isArray(repliesRes.data) ? repliesRes.data : []);
    } catch (err) {
      setError(err.message || '无法连接 Python 后端');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSend = () => {
    if (!inputText.trim()) return;
    setLocalMessages(prev => [
      ...prev,
      {
        id: Date.now(),
        text: inputText,
        time: new Date().toLocaleTimeString().slice(0, 5),
      },
    ]);
    setInputText('');
  };

  const statCards = stats
    ? [
        { label: '总会话数', value: stats.total_conversations ?? '-', icon: MessagesSquare, color: 'text-blue-600 bg-blue-50' },
        { label: '总消息量', value: stats.total_messages ?? '-', icon: BarChart3, color: 'text-indigo-600 bg-indigo-50' },
        { label: '今日自动回复', value: stats.today_replied ?? '-', icon: Zap, color: 'text-amber-600 bg-amber-50' },
        { label: '累计自动回复', value: stats.total_replied ?? '-', icon: Bot, color: 'text-green-600 bg-green-50' },
        { label: '近期回复', value: stats.recent_replied ?? '-', icon: Activity, color: 'text-purple-600 bg-purple-50' },
      ]
    : [];

  if (loading) {
    return (
      <div className="xy-page xy-enter max-w-6xl flex items-center justify-center h-[calc(100vh-100px)]">
        <div className="flex flex-col items-center gap-3 text-xy-text-muted">
          <RefreshCw className="w-8 h-8 animate-spin text-xy-brand-500" />
          <span>正在加载消息数据…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="xy-page xy-enter max-w-6xl flex items-center justify-center h-[calc(100vh-100px)]">
        <div className="xy-card p-8 flex flex-col items-center gap-4 max-w-md text-center">
          <AlertCircle className="w-10 h-10 text-red-500" />
          <p className="text-xy-text-primary font-medium">连接失败</p>
          <p className="text-sm text-xy-text-secondary">{error}</p>
          <button onClick={fetchData} className="xy-btn-primary mt-2 flex items-center gap-2">
            <RefreshCw className="w-4 h-4" /> 重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="xy-page xy-enter max-w-6xl h-[calc(100vh-100px)]">
      <div className="xy-card flex h-full overflow-hidden">
        {/* 左侧：消息统计概览 */}
        <div className="w-1/3 min-w-[280px] max-w-[320px] border-r border-xy-border flex flex-col bg-xy-gray-50">
          <div className="p-4 border-b border-xy-border bg-white">
            <div className="flex items-center justify-between mb-1">
              <h2 className="font-bold text-lg flex items-center gap-2">
                <MessageCircle className="w-5 h-5 text-xy-brand-500" /> 消息概览
              </h2>
              <button
                onClick={fetchData}
                className="p-1.5 rounded-lg hover:bg-xy-gray-100 text-xy-text-muted transition-colors"
                title="刷新数据"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-xy-text-muted">来自 Python 后端实时数据</p>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {statCards.map((card) => (
              <div
                key={card.label}
                className="bg-white rounded-xl p-4 border border-xy-border shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${card.color}`}>
                    <card.icon className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-xy-text-primary">{card.value}</p>
                    <p className="text-xs text-xy-text-secondary">{card.label}</p>
                  </div>
                </div>
              </div>
            ))}

            {stats?.hourly_replies && Object.keys(stats.hourly_replies).length > 0 && (
              <div className="bg-white rounded-xl p-4 border border-xy-border shadow-sm">
                <p className="text-sm font-medium text-xy-text-primary mb-3">每小时回复分布</p>
                <div className="space-y-1.5">
                  {Object.entries(stats.hourly_replies)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([hour, count]) => {
                      const max = Math.max(...Object.values(stats.hourly_replies), 1);
                      return (
                        <div key={hour} className="flex items-center gap-2 text-xs">
                          <span className="w-10 text-xy-text-muted text-right">{hour}时</span>
                          <div className="flex-1 h-4 bg-xy-gray-100 rounded overflow-hidden">
                            <div
                              className="h-full bg-xy-brand-400 rounded"
                              style={{ width: `${(count / max) * 100}%` }}
                            />
                          </div>
                          <span className="w-6 text-xy-text-muted text-right">{count}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {stats?.daily_replies && Object.keys(stats.daily_replies).length > 0 && (
              <div className="bg-white rounded-xl p-4 border border-xy-border shadow-sm">
                <p className="text-sm font-medium text-xy-text-primary mb-3">每日回复趋势</p>
                <div className="space-y-1.5">
                  {Object.entries(stats.daily_replies)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([date, count]) => {
                      const max = Math.max(...Object.values(stats.daily_replies), 1);
                      return (
                        <div key={date} className="flex items-center gap-2 text-xs">
                          <span className="w-16 text-xy-text-muted text-right">{date}</span>
                          <div className="flex-1 h-4 bg-xy-gray-100 rounded overflow-hidden">
                            <div
                              className="h-full bg-green-400 rounded"
                              style={{ width: `${(count / max) * 100}%` }}
                            />
                          </div>
                          <span className="w-6 text-xy-text-muted text-right">{count}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 右侧：自动回复日志 */}
        <div className="flex-1 flex flex-col bg-white">
          <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-white shadow-sm z-10">
            <div>
              <h3 className="font-bold text-lg text-xy-text-primary">自动回复日志</h3>
              <p className="text-sm text-xy-text-secondary mt-0.5">
                共 <span className="text-xy-brand-600 font-medium">{replies.length}</span> 条记录
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 bg-green-50 text-green-700 rounded-full border border-green-200">
              <Bot className="w-3.5 h-3.5" /> AI 自动回复
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-xy-gray-50/50">
            {replies.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-xy-text-muted">
                <MessageCircle className="w-16 h-16 mb-4 text-xy-gray-200" />
                <p>暂无自动回复记录</p>
              </div>
            ) : (
              replies.map((reply, idx) => (
                <div key={reply.id || idx} className="bg-white rounded-xl border border-xy-border p-4 shadow-sm space-y-3">
                  {/* 买家消息 */}
                  {reply.buyer_message && (
                    <div className="flex gap-3">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center bg-blue-100 text-blue-600 flex-shrink-0">
                        <User className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 text-xs text-xy-text-muted">
                          <span className="font-medium text-blue-600">买家</span>
                          {reply.item_title && (
                            <span className="bg-xy-gray-100 px-1.5 py-0.5 rounded truncate max-w-[200px]">
                              {reply.item_title}
                            </span>
                          )}
                        </div>
                        <div className="px-3 py-2 rounded-xl bg-xy-gray-50 border border-xy-border text-sm text-xy-text-primary rounded-tl-sm">
                          {reply.buyer_message}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* AI 回复 */}
                  {reply.reply_text && (
                    <div className="flex gap-3 flex-row-reverse">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center bg-orange-100 text-orange-600 flex-shrink-0">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div className="flex flex-col items-end flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 text-xs text-xy-text-muted">
                          <span className="font-medium text-orange-500">自动回复</span>
                          {reply.intent && (
                            <span className="bg-xy-gray-200 px-1.5 py-0.5 rounded text-xy-gray-600">
                              意图: {reply.intent}
                            </span>
                          )}
                          {reply.replied_at && (
                            <span>{new Date(reply.replied_at).toLocaleString()}</span>
                          )}
                        </div>
                        <div className="px-3 py-2 rounded-xl bg-orange-50 border border-orange-200 text-sm text-xy-text-primary rounded-tr-sm">
                          {reply.reply_text}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}

            {localMessages.map((msg) => (
              <div key={msg.id} className="flex gap-3 flex-row-reverse">
                <div className="w-8 h-8 rounded-full flex items-center justify-center bg-xy-gray-200 text-xy-gray-600 flex-shrink-0">
                  <User className="w-4 h-4" />
                </div>
                <div className="flex flex-col items-end max-w-[70%]">
                  <div className="flex items-center gap-2 mb-1 text-xs text-xy-text-muted">
                    <span className="font-medium text-xy-text-secondary">模拟发送</span>
                    <span>{msg.time}</span>
                  </div>
                  <div className="px-4 py-2.5 rounded-2xl bg-xy-brand-500 text-white text-sm leading-relaxed shadow-sm rounded-tr-sm">
                    {msg.text}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* 手动回复输入框 */}
          <div className="p-4 bg-white border-t border-xy-border">
            <div className="flex gap-3 items-end">
              <textarea
                className="flex-1 xy-input py-3 px-4 resize-none h-[80px]"
                placeholder="模拟发送（需要 Python 后端运行才能真正送达）"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
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
                <Clock className="w-3.5 h-3.5" /> 实际消息发送需要 Python 后端 WebSocket 运行
              </p>
              <p className="text-xs text-xy-text-muted">Enter 发送，Shift+Enter 换行</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
