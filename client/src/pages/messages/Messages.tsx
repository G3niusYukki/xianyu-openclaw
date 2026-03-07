import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/index';
import {
  MessageCircle, Send, Bot, User,
  RefreshCw, BarChart3, MessagesSquare, Zap,
  AlertCircle, Activity, Beaker,
} from 'lucide-react';
import toast from 'react-hot-toast';

const MSG_TABS = [
  { key: 'logs', label: '回复日志' },
  { key: 'sandbox', label: '测试沙盒' },
];

export default function Messages() {
  const [activeTab, setActiveTab] = useState('logs');
  const [logView, setLogView] = useState('list');
  const [stats, setStats] = useState<any>(null);
  const [replies, setReplies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sandboxInput, setSandboxInput] = useState('');
  const [sandboxResult, setSandboxResult] = useState<any>(null);
  const [sandboxTesting, setSandboxTesting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const statusRes = await api.get('/status');
      setStats(statusRes.data.message_stats || null);

      try {
        const repliesRes = await api.get('/replies');
        const d = repliesRes.data;
        if (Array.isArray(d)) {
          setReplies(d);
        } else if (d?.logs && Array.isArray(d.logs)) {
          setReplies(d.logs);
        } else {
          setReplies([]);
        }
      } catch {
        setReplies([]);
      }
    } catch (err: any) {
      setError(err.message || '无法连接后端');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleTestReply = async () => {
    if (!sandboxInput.trim()) return;
    setSandboxTesting(true);
    setSandboxResult(null);
    try {
      const res = await api.post('/test-reply', { message: sandboxInput });
      setSandboxResult(res.data);
    } catch (e: any) { setSandboxResult({ error: e.message }); }
    finally { setSandboxTesting(false); }
  };

  const statCards = stats ? [
    { label: '总会话数', value: stats.total_conversations ?? '-', icon: MessagesSquare, color: 'text-blue-600 bg-blue-50' },
    { label: '总消息量', value: stats.total_messages ?? '-', icon: BarChart3, color: 'text-indigo-600 bg-indigo-50' },
    { label: '今日自动回复', value: stats.today_replied ?? '-', icon: Zap, color: 'text-amber-600 bg-amber-50' },
    { label: '累计自动回复', value: stats.total_replied ?? '-', icon: Bot, color: 'text-green-600 bg-green-50' },
    { label: '近期回复', value: stats.recent_replied ?? '-', icon: Activity, color: 'text-purple-600 bg-purple-50' },
  ] : [];

  if (loading) {
    return (
      <div className="xy-page xy-enter max-w-6xl">
        <div className="flex justify-between mb-6">
          <div className="w-1/3">
            <div className="h-8 bg-xy-gray-200 rounded-lg w-1/2 mb-3 animate-pulse"></div>
            <div className="h-4 bg-xy-gray-200 rounded w-2/3 animate-pulse"></div>
          </div>
        </div>
        <div className="xy-card flex h-[calc(100vh-200px)]">
          <div className="w-1/3 border-r border-xy-border p-4 space-y-4">
            <div className="h-6 bg-xy-gray-200 rounded w-1/3 animate-pulse mb-6"></div>
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="h-16 bg-xy-gray-100 rounded-xl animate-pulse"></div>
            ))}
          </div>
          <div className="flex-1 p-6 space-y-6">
            <div className="h-6 bg-xy-gray-200 rounded w-1/4 animate-pulse mb-8"></div>
            {[1, 2, 3].map(i => (
              <div key={i} className="h-24 bg-xy-gray-100 rounded-xl animate-pulse"></div>
            ))}
          </div>
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
    <div className="xy-page xy-enter max-w-6xl">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title flex items-center gap-2">
            <MessageCircle className="w-6 h-6 text-xy-brand-500" /> 消息中心
          </h1>
          <p className="xy-subtitle mt-1">自动回复日志和测试沙盒（模板配置已移至「系统设置 &gt; 自动回复」）</p>
        </div>
        <div className="flex bg-xy-gray-100 p-1 rounded-xl">
          {MSG_TABS.map(t => (
            <button key={t.key} onClick={() => setActiveTab(t.key)}
              aria-selected={activeTab === t.key}
              role="tab"
              className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-xy-brand-500 focus-visible:ring-offset-2 ${activeTab === t.key ? 'bg-white shadow-sm text-xy-text-primary' : 'text-xy-text-secondary hover:text-xy-text-primary'}`}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'logs' && (
        <>
        <div className="md:hidden flex bg-xy-gray-100 p-1 rounded-xl mb-4">
          <button onClick={() => setLogView('stats')} className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${logView === 'stats' ? 'bg-white shadow-sm text-xy-text-primary' : 'text-xy-text-secondary'}`}>统计概览</button>
          <button onClick={() => setLogView('list')} className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${logView === 'list' ? 'bg-white shadow-sm text-xy-text-primary' : 'text-xy-text-secondary'}`}>回复日志</button>
        </div>

        <div className="xy-card flex flex-col md:flex-row h-[calc(100vh-200px)] md:h-[calc(100vh-200px)] overflow-hidden">
          <div className={`${logView === 'list' ? 'hidden md:flex' : 'flex'} md:w-1/3 md:min-w-[260px] md:max-w-[320px] border-b md:border-b-0 md:border-r border-xy-border flex-col bg-xy-gray-50`}>
            <div className="p-4 border-b border-xy-border bg-white">
              <div className="flex items-center justify-between mb-1">
                <h2 className="font-bold text-lg flex items-center gap-2"><MessageCircle className="w-5 h-5 text-xy-brand-500" /> 消息概览</h2>
                <button onClick={fetchData} className="p-1.5 rounded-lg hover:bg-xy-gray-100 text-xy-text-muted transition-colors" title="刷新数据">
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {statCards.map(card => {
                const IconComponent = card.icon;
                return (
                  <div key={card.label} className="bg-white rounded-xl p-4 border border-xy-border shadow-sm">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${card.color}`}>
                        <IconComponent className="w-5 h-5" />
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-xy-text-primary">{card.value}</p>
                        <p className="text-xs text-xy-text-secondary">{card.label}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className={`${logView === 'stats' ? 'hidden md:flex' : 'flex'} flex-1 flex-col bg-white`}>
            <div className="px-6 py-4 border-b border-xy-border flex justify-between items-center bg-white shadow-sm z-10">
              <div>
                <h3 className="font-bold text-lg text-xy-text-primary">自动回复日志</h3>
                <p className="text-sm text-xy-text-secondary mt-0.5">共 <span className="text-xy-brand-600 font-medium">{replies.length}</span> 条记录</p>
              </div>
              <div className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 bg-green-50 text-green-700 rounded-full border border-green-200">
                <Bot className="w-3.5 h-3.5" /> AI 自动回复
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-xy-gray-50/50">
              {replies.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <div className="w-20 h-20 bg-white rounded-full flex items-center justify-center mb-4 shadow-sm border border-xy-border">
                    <MessageCircle className="w-10 h-10 text-xy-gray-300" />
                  </div>
                  <p className="text-base font-medium text-xy-text-primary mb-1">暂无自动回复记录</p>
                  <p className="text-sm text-xy-text-secondary max-w-xs">系统启动后，自动回复的消息会在此处显示。回复模板可在「系统设置 &gt; 自动回复」中配置。</p>
                </div>
              ) : (
                replies.map((reply, idx) => (
                  <div key={reply.id || idx} className="bg-white rounded-xl border border-xy-border p-4 shadow-sm space-y-3">
                    {reply.buyer_message && (
                      <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center bg-blue-100 text-blue-600 flex-shrink-0"><User className="w-4 h-4" /></div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 text-xs text-xy-text-muted">
                            <span className="font-medium text-blue-600">买家</span>
                            {reply.item_title && <span className="bg-xy-gray-100 px-1.5 py-0.5 rounded truncate max-w-[200px]">{reply.item_title}</span>}
                          </div>
                          <div className="px-3 py-2 rounded-xl bg-xy-gray-50 border border-xy-border text-sm text-xy-text-primary rounded-tl-sm">{reply.buyer_message}</div>
                        </div>
                      </div>
                    )}
                    {reply.reply_text && (
                      <div className="flex gap-3 flex-row-reverse">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center bg-orange-100 text-orange-600 flex-shrink-0"><Bot className="w-4 h-4" /></div>
                        <div className="flex flex-col items-end flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 text-xs text-xy-text-muted">
                            <span className="font-medium text-orange-500">自动回复</span>
                            {reply.intent && <span className="bg-xy-gray-200 px-1.5 py-0.5 rounded text-xy-gray-600">意图: {reply.intent}</span>}
                            {reply.replied_at && <span>{new Date(reply.replied_at).toLocaleString()}</span>}
                          </div>
                          <div className="px-3 py-2 rounded-xl bg-orange-50 border border-orange-200 text-sm text-xy-text-primary rounded-tr-sm">{reply.reply_text}</div>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
        </>
      )}

      {activeTab === 'sandbox' && (
        <div className="xy-card p-6 space-y-6 animate-in fade-in slide-in-from-right-4">
          <div>
            <h2 className="text-lg font-bold text-xy-text-primary flex items-center gap-2"><Beaker className="w-5 h-5" /> 测试沙盒</h2>
            <p className="text-sm text-xy-text-secondary mt-1">模拟买家消息，测试 AI 自动回复效果</p>
          </div>
          <div className="flex gap-3">
            <textarea
              className="flex-1 xy-input px-4 py-3 h-24 resize-none"
              placeholder='输入模拟的买家消息，如："这个怎么卖？还有货吗？"'
              value={sandboxInput}
              onChange={e => setSandboxInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleTestReply(); } }}
            />
            <button onClick={handleTestReply} disabled={sandboxTesting || !sandboxInput.trim()} className="xy-btn-primary px-6 self-end">
              {sandboxTesting ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            </button>
          </div>
          {sandboxResult && (
            <div className="space-y-4">
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0"><User className="w-4 h-4" /></div>
                <div className="px-4 py-3 rounded-xl bg-blue-50 border border-blue-200 text-sm flex-1">{sandboxInput}</div>
              </div>
              <div className="flex gap-3 flex-row-reverse">
                <div className="w-8 h-8 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center flex-shrink-0"><Bot className="w-4 h-4" /></div>
                <div className="flex-1 min-w-0">
                  {sandboxResult.error ? (
                    <div className="px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">{sandboxResult.error}</div>
                  ) : (
                    <div className="px-4 py-3 rounded-xl bg-orange-50 border border-orange-200 text-sm">
                      <p className="text-xy-text-primary">{sandboxResult.reply || sandboxResult.response || sandboxResult.text || JSON.stringify(sandboxResult)}</p>
                      {sandboxResult.intent && <p className="text-xs text-xy-text-muted mt-2">识别意图: {sandboxResult.intent}</p>}
                      {sandboxResult.latency_ms != null && <p className="text-xs text-xy-text-muted">延迟: {sandboxResult.latency_ms}ms</p>}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
