const express = require('express');
const crypto = require('crypto');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const router = express.Router();

const CONFIG_FILE = path.join(__dirname, '../../data/system_config.json');


function md5(str) {
  return crypto.createHash('md5').update(str, 'utf8').digest('hex');
}

function signRequest(appKey, appSecret, body, timestamp) {
  const bodyMd5 = md5(body || '');
  return md5(`${appKey},${bodyMd5},${timestamp},${appSecret}`);
}

function loadXgjConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
      const xgj = config.xianguanjia || {};
      return {
        appKey: xgj.app_key || process.env.XGJ_APP_KEY || '',
        appSecret: xgj.app_secret || process.env.XGJ_APP_SECRET || '',
        baseUrl: xgj.base_url || process.env.XGJ_BASE_URL || 'https://open.goofish.pro',
      };
    }
  } catch (e) {
    console.error('Failed to load XGJ config:', e.message);
  }
  return {
    appKey: process.env.XGJ_APP_KEY || '',
    appSecret: process.env.XGJ_APP_SECRET || '',
    baseUrl: process.env.XGJ_BASE_URL || 'https://open.goofish.pro',
  };
}

function timingSafeCompare(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const bufA = Buffer.from(a, 'utf8');
  const bufB = Buffer.from(b, 'utf8');
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

router.post('/proxy', async (req, res) => {
  try {
    const { apiPath, body: reqBody, path: legacyPath, payload } = req.body;
    const resolvedPath = apiPath || legacyPath;

    if (!resolvedPath || typeof resolvedPath !== 'string' || !resolvedPath.startsWith('/api/open/')) {
      return res.status(400).json({ error: 'Invalid apiPath' });
    }

    const cfg = loadXgjConfig();
    if (!cfg.appKey || !cfg.appSecret) {
      return res.status(400).json({ ok: false, error: 'XianGuanJia API not configured. Please configure in Settings.' });
    }

    const body = JSON.stringify(reqBody || payload || {});
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const sign = signRequest(cfg.appKey, cfg.appSecret, body, timestamp);

    const url = `${cfg.baseUrl}${resolvedPath}`;
    const response = await axios.post(url, body, {
      params: { appid: cfg.appKey, timestamp, sign },
      headers: { 'Content-Type': 'application/json' },
      timeout: 15000,
    });

    res.json({ ok: true, data: response.data });
  } catch (error) {
    console.error('XGJ proxy error:', error.response?.data || error.message);
    res.status(error.response?.status || 500).json({
      ok: false,
      error: error.response?.data?.msg || 'Request failed',
    });
  }
});

const PYTHON_WEBHOOK_URL = process.env.PYTHON_WEBHOOK_URL || 'http://localhost:8091/api/webhook';

async function handleWebhook(req, res) {
  try {
    const cfg = loadXgjConfig();
    if (!cfg.appKey || !cfg.appSecret) {
      return res.status(400).json({ code: 1, msg: 'Not configured' });
    }

    const timestamp = parseInt(req.body.timestamp || req.query.timestamp);
    const now = Math.floor(Date.now() / 1000);
    if (!timestamp || Math.abs(now - timestamp) > 300) {
      return res.status(400).json({ error: 'Timestamp expired' });
    }

    const { sign } = req.query;
    const rawBody = req.rawBody
      ? req.rawBody.toString('utf8')
      : JSON.stringify(req.body);
    const expected = signRequest(cfg.appKey, cfg.appSecret, rawBody, String(timestamp));

    if (!timingSafeCompare(expected, sign || '')) {
      return res.status(401).json({ code: 401, msg: 'Invalid signature' });
    }

    const forwarded = await axios.post(PYTHON_WEBHOOK_URL, rawBody, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 10000,
    });

    res.json(forwarded.data);
  } catch (error) {
    console.error('Webhook error:', error.message);
    if (error.response) {
      return res.status(error.response.status).json(error.response.data);
    }
    res.status(500).json({ code: 500, msg: 'Internal error' });
  }
}

router.post('/order/receive', handleWebhook);
router.post('/product/receive', handleWebhook);

module.exports = router;
