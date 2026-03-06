import React, { useEffect, useState } from 'react';
import { pyApi } from '../../api/index';
import {
  Activity,
  AlertCircle,
  BarChart3,
  Bot,
  MessageCircle,
  MessagesSquare,
  RefreshCw,
  Zap,
} from 'lucide-react';

export default function Messages() {
  const [stats, setStats] = useState(null);
  const [logLines, setLogLines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [statusRes, logsRes] = await Promise.all([
        pyApi.get('/api/status'),
        pyApi.get('/api/logs/content', { params: { file: 'presales', tail: 80 } }),
      ]);
      setStats(statusRes.data?.message_stats || null);
      setLogLines(logsRes.data?.lines || []);
    } catch (err) {
      setError(err.message || '无法读取消息运行状态');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const statCards = stats
    ? [
        { label: '总会话数', value: stats.total_conversations ?? '-', icon: MessagesSquare, color: 'text-blue-600 bg-blue-50' },
        { label: '总消息量', value: stats.total_messages ?? '-', icon: BarChart3, color: 'text-indigo-600 bg-indigo-50' },
        { label: '今日自动回复', value: stats.today_replied ?? '-', icon: Zap, color: 'text-amber-600 bg-amber-50' },
        { label: '累计自动回复', value: stats.total_replied ?? '-', icon: Bot, color: 'text-green-600 bg-green-50' },
        { label: '近一小时回复', value: stats.recent_replied ?? '-', icon: Activity, color: 'text-purple-600 bg-purple-50' },
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
    <div className="xy-page xy-enter max-w-6xl space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="xy-title">消息中心</h1>
          <p className="xy-subtitle mt-1">展示 Python 消息工作流的真实运行统计和最近日志。</p>
        </div>
        <button onClick={fetchData} className="xy-btn-secondary px-3" aria-label="刷新消息中心">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="grid md:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <div key={card.label} className="xy-card p-5">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${card.color}`}>
              <card.icon className="w-5 h-5" />
            </div>
            <p className="text-2xl font-bold text-xy-text-primary">{card.value}</p>
            <p className="text-sm text-xy-text-secondary mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      <div className="xy-card overflow-hidden">
        <div className="px-6 py-4 border-b border-xy-border bg-xy-gray-50 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-xy-text-primary flex items-center gap-2">
              <MessageCircle className="w-4 h-4 text-xy-brand-500" /> 最近消息模块日志
            </h2>
            <p className="text-sm text-xy-text-secondary mt-1">来源：`presales` 运行日志</p>
          </div>
          <span className="text-xs text-xy-text-muted">{logLines.length} 行</span>
        </div>

        <div className="bg-xy-gray-950 text-slate-100 text-sm font-mono p-4 max-h-[560px] overflow-y-auto space-y-2">
          {logLines.length === 0 ? (
            <div className="text-xy-text-muted py-6 text-center">暂无消息模块日志</div>
          ) : (
            logLines.map((line, index) => (
              <div key={`${index}-${line.slice(0, 16)}`} className="whitespace-pre-wrap break-all">
                {line}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
