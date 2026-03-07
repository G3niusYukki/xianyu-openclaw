require('dotenv').config();
const express = require('express');
const http = require('http');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');

const xianguanjiaRoutes = require('./routes/xianguanjia');
const { loadXgjConfig, signRequest } = require('./routes/xianguanjia');
const configRoutes = require('./routes/config');
const axios = require('axios');

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
  const pyUrl = process.env.PY_API_URL || 'http://localhost:8091';
  try {
    const pyResp = await axios.get(`${pyUrl}/api/health/check`, { timeout: 12000 });
    const data = pyResp.data || {};
    data.node = { ok: true, message: '运行中' };
    if (!data.services) data.services = {};
    data.services.python = { ok: true, message: '运行中' };
    res.json(data);
  } catch (err) {
    res.json({
      timestamp: new Date().toISOString(),
      node: { ok: true, message: '运行中' },
      services: { python: { ok: false, message: err.code === 'ECONNREFUSED' ? '服务未启动' : (err.message || '连接失败') } },
      python: { ok: false, message: err.code === 'ECONNREFUSED' ? '服务未启动' : (err.message || '连接失败') },
      cookie: { ok: false, message: 'Python 服务不可达' },
      ai: { ok: false, message: 'Python 服务不可达' },
      xgj: { ok: false, message: 'Python 服务不可达' },
    });
  }
});

app.get('/api/service-status', async (req, res) => {
  try {
    const pyUrl = process.env.PY_API_URL || 'http://localhost:8091';
    const resp = await axios.get(`${pyUrl}/api/status`, { timeout: 5000 });
    res.json(resp.data);
  } catch {
    res.json({ service_status: 'unknown' });
  }
});

app.use('/api', (req, res) => {
  const pyBase = process.env.PY_API_URL || 'http://localhost:8091';
  const target = new URL(pyBase);

  const headers = { ...req.headers, host: target.host };
  let body = null;
  let pipe = false;

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    if (req.is('json') && req.body) {
      body = JSON.stringify(req.body);
      headers['content-type'] = 'application/json';
      headers['content-length'] = String(Buffer.byteLength(body));
    } else {
      pipe = true;
    }
  }

  const proxyReq = http.request({
    hostname: target.hostname,
    port: target.port,
    path: req.originalUrl,
    method: req.method,
    headers,
    timeout: 15000,
  }, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (err) => {
    if (!res.headersSent) {
      res.status(502).json({ error: 'Python backend unavailable', detail: err.message });
    }
  });

  if (pipe) req.pipe(proxyReq);
  else if (body) proxyReq.end(body);
  else proxyReq.end();
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
