import { useState, useEffect, useCallback, useRef } from 'react';
import { nodeApi, pyApi } from '../api/index';

const POLL_INTERVAL = 60_000;

const EMPTY = {
  loading: true,
  lastChecked: null,
  node:   { ok: false, message: '检查中...' },
  python: { ok: false, message: '检查中...' },
  cookie: { ok: false, message: '检查中...' },
  ai:     { ok: false, message: '检查中...' },
  xgj:    { ok: false, message: '检查中...' },
};

export default function useHealthCheck(enabled = true) {
  const [health, setHealth] = useState(EMPTY);
  const timerRef = useRef(null);

  const check = useCallback(async () => {
    const next = { loading: false, lastChecked: new Date().toISOString() };

    const [nodeRes, pyRes] = await Promise.allSettled([
      nodeApi.get('/health/check'),
      pyApi.get('/api/health/check'),
    ]);

    if (nodeRes.status === 'fulfilled') {
      const d = nodeRes.value.data;
      next.node   = d.node   || { ok: true, message: '运行中' };
      next.python = d.python || { ok: false, message: '未知' };
      next.xgj    = d.xgj    || { ok: false, message: '未检查' };
    } else {
      next.node   = { ok: false, message: '不可达' };
      next.python = { ok: false, message: '未知' };
      next.xgj    = { ok: false, message: '未知' };
    }

    if (pyRes.status === 'fulfilled') {
      const d = pyRes.value.data;
      next.cookie = d.cookie || { ok: false, message: '未知' };
      next.ai     = d.ai     || { ok: false, message: '未知' };
      if (!next.python.ok && d.services?.python?.ok) {
        next.python = d.services.python;
      }
    } else {
      next.cookie = { ok: false, message: '后端不可达' };
      next.ai     = { ok: false, message: '后端不可达' };
      if (!next.python?.ok) {
        next.python = { ok: false, message: '不可达' };
      }
    }

    setHealth(next);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    check();
    timerRef.current = setInterval(check, POLL_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [enabled, check]);

  return { ...health, refresh: check };
}
