const express = require('express');
const crypto = require('crypto');
const axios = require('axios');
const fs = require('fs');
const path = require('path');

const router = express.Router();

const ENV_FILE = path.join(__dirname, '../../.env');
const PYTHON_WEBHOOK_URL = process.env.PYTHON_WEBHOOK_URL || 'http://localhost:8091/api/orders/callback';

function md5(value) {
  return crypto.createHash('md5').update(value, 'utf8').digest('hex');
}

function parseEnvFile() {
  try {
    if (!fs.existsSync(ENV_FILE)) return {};
    const lines = fs.readFileSync(ENV_FILE, 'utf8').split(/\r?\n/);
    const parsed = {};
    for (const line of lines) {
      if (!line || line.trim().startsWith('#')) continue;
      const index = line.indexOf('=');
      if (index <= 0) continue;
      parsed[line.slice(0, index).trim()] = line.slice(index + 1).trim();
    }
    return parsed;
  } catch (error) {
    console.error('Failed to parse .env:', error.message);
    return {};
  }
}

function loadXgjConfig() {
  const env = parseEnvFile();
  return {
    appKey: env.XGJ_APP_KEY || process.env.XGJ_APP_KEY || '',
    appSecret: env.XGJ_APP_SECRET || process.env.XGJ_APP_SECRET || '',
    sellerId: env.XGJ_MERCHANT_ID || process.env.XGJ_MERCHANT_ID || '',
    baseUrl: env.XGJ_BASE_URL || process.env.XGJ_BASE_URL || 'https://open.goofish.pro',
  };
}

function signRequest(appKey, appSecret, body, timestamp, sellerId = '') {
  const bodyMd5 = md5(body || '');
  const parts = [String(appKey), bodyMd5, String(timestamp)];
  if (sellerId) parts.push(String(sellerId));
  parts.push(String(appSecret));
  return md5(parts.join(''));
}

function normalizeTimestampSeconds(rawValue) {
  const text = String(rawValue || '').trim();
  if (!/^\d+$/.test(text)) return 0;
  if (text.length > 10) return Math.floor(Number(text) / 1000);
  return Number(text);
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
      return res.status(400).json({ ok: false, error: 'Invalid apiPath' });
    }

    const cfg = loadXgjConfig();
    if (!cfg.appKey || !cfg.appSecret) {
      return res.status(400).json({ ok: false, error: 'XianGuanJia API not configured' });
    }

    const body = JSON.stringify(reqBody || payload || {});
    const timestamp = Date.now().toString();
    const sign = signRequest(cfg.appKey, cfg.appSecret, body, timestamp, cfg.sellerId);

    const params = { appKey: cfg.appKey, timestamp, sign };
    if (cfg.sellerId) params.sellerId = cfg.sellerId;

    const response = await axios.post(`${cfg.baseUrl}${resolvedPath}`, body, {
      params,
      headers: { 'Content-Type': 'application/json' },
      timeout: 15000,
    });

    const ok = response.data?.code === 0 || response.status < 400;
    res.json({
      ok,
      data: response.data?.data ?? response.data,
      raw: response.data,
    });
  } catch (error) {
    console.error('XGJ proxy error:', error.response?.data || error.message);
    res.status(error.response?.status || 500).json({
      ok: false,
      error: error.response?.data?.msg || error.response?.data?.error || 'Request failed',
    });
  }
});

async function handleWebhook(req, res) {
  try {
    const cfg = loadXgjConfig();
    if (!cfg.appKey || !cfg.appSecret) {
      return res.status(400).json({ code: 1, msg: 'Not configured' });
    }

    const rawTimestamp = String(req.body.timestamp || req.query.timestamp || '').trim();
    const normalizedTimestamp = normalizeTimestampSeconds(rawTimestamp);
    const nowSeconds = Math.floor(Date.now() / 1000);
    if (!normalizedTimestamp || Math.abs(nowSeconds - normalizedTimestamp) > 300) {
      return res.status(400).json({ error: 'Timestamp expired' });
    }

    const sign = String(req.query.sign || '').trim().toLowerCase();
    const rawBody = req.rawBody ? req.rawBody.toString('utf8') : JSON.stringify(req.body || {});
    const expected = signRequest(cfg.appKey, cfg.appSecret, rawBody, rawTimestamp, cfg.sellerId);

    if (!timingSafeCompare(expected, sign)) {
      return res.status(401).json({ code: 401, msg: 'Invalid signature' });
    }

    const forwarded = await axios.post(PYTHON_WEBHOOK_URL, rawBody, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 10000,
    });

    res.status(forwarded.status).json(forwarded.data);
  } catch (error) {
    console.error('Webhook error:', error.response?.data || error.message);
    if (error.response) {
      return res.status(error.response.status).json(error.response.data);
    }
    res.status(500).json({ code: 500, msg: 'Internal error' });
  }
}

router.post('/order/receive', handleWebhook);
router.post('/product/receive', handleWebhook);

module.exports = router;
