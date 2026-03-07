require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');

const xianguanjiaRoutes = require('./routes/xianguanjia');
const configRoutes = require('./routes/config');

const app = express();

app.use(helmet());
app.use(cors({
  origin: process.env.FRONTEND_URL || '*',
  credentials: true
}));
app.use(morgan('combined'));
app.use(express.json({
  limit: '10mb',
  verify: (req, res, buf) => {
    const rawBodyPaths = ['/api/xgj/order/receive', '/api/xgj/product/receive'];
    if (rawBodyPaths.some(p => req.originalUrl.startsWith(p))) {
      req.rawBody = buf;
    }
  }
}));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

app.use('/api/xgj', xianguanjiaRoutes);
app.use('/api/config', configRoutes);

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.get('/api/health/check', async (req, res) => {
  const result = { timestamp: new Date().toISOString() };

  result.node = { ok: true, message: '运行中' };

  // Python backend connectivity
  try {
    const pyUrl = process.env.PY_API_URL || 'http://localhost:8091';
    const pyResp = await axios.get(`${pyUrl}/healthz`, { timeout: 5000 });
    result.python = { ok: pyResp.data?.status === 'ok', message: pyResp.data?.status || 'unknown' };
  } catch (err) {
    result.python = { ok: false, message: err.code === 'ECONNREFUSED' ? '服务未启动' : (err.message || '连接失败') };
  }

  // XGJ API connectivity
  const { loadXgjConfig, signRequest } = (() => {
    const crypto = require('crypto');
    const fs = require('fs');
    const path = require('path');
    const CONFIG_FILE = path.join(__dirname, '../data/system_config.json');
    function md5(str) { return crypto.createHash('md5').update(str, 'utf8').digest('hex'); }
    function sign(appKey, appSecret, body, ts) { return md5(`${appKey},${md5(body || '')},${ts},${appSecret}`); }
    function load() {
      try {
        if (fs.existsSync(CONFIG_FILE)) {
          const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
          const xgj = config.xianguanjia || {};
          return { appKey: xgj.app_key || process.env.XGJ_APP_KEY || '', appSecret: xgj.app_secret || process.env.XGJ_APP_SECRET || '', baseUrl: xgj.base_url || process.env.XGJ_BASE_URL || 'https://open.goofish.pro' };
        }
      } catch {}
      return { appKey: process.env.XGJ_APP_KEY || '', appSecret: process.env.XGJ_APP_SECRET || '', baseUrl: process.env.XGJ_BASE_URL || 'https://open.goofish.pro' };
    }
    return { loadXgjConfig: load, signRequest: sign };
  })();

  try {
    const cfg = loadXgjConfig();
    if (!cfg.appKey || !cfg.appSecret) {
      result.xgj = { ok: false, message: 'AppKey 或 AppSecret 未配置' };
    } else {
      const ts = Date.now().toString();
      const body = JSON.stringify({ method: 'health.check' });
      const sign = signRequest(cfg.appKey, cfg.appSecret, body, ts);
      const t0 = Date.now();
      const xgjResp = await axios.post(`${cfg.baseUrl}/api/open/proxy`, body, {
        headers: { 'Content-Type': 'application/json', 'x-app-key': cfg.appKey, 'x-timestamp': ts, 'x-sign': sign },
        timeout: 8000,
        validateStatus: () => true,
      });
      const latency = Date.now() - t0;
      if (xgjResp.status < 500) {
        result.xgj = { ok: true, message: '连通', latency_ms: latency };
      } else {
        result.xgj = { ok: false, message: `HTTP ${xgjResp.status}`, latency_ms: latency };
      }
    }
  } catch (err) {
    result.xgj = { ok: false, message: err.code === 'ECONNREFUSED' ? '闲管家服务不可达' : (err.message || '连接失败') };
  }

  res.json(result);
});

app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    error: 'Internal server error',
    message: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

const PORT = process.env.PORT || 3001;

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
    console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  });
}

module.exports = app;
