const express = require('express');
const axios = require('axios');

const router = express.Router();
const PYTHON_API_URL = (process.env.PYTHON_API_URL || 'http://localhost:8091').replace(/\/$/, '');

async function proxyConfig(req, res, targetPath, method = 'get') {
  try {
    const response = await axios({
      method,
      url: `${PYTHON_API_URL}${targetPath}`,
      data: req.body,
      headers: { 'Content-Type': 'application/json' },
      timeout: 15000,
    });
    res.status(response.status).json(response.data);
  } catch (error) {
    const status = error.response?.status || 502;
    const payload = error.response?.data || { ok: false, error: 'Python config API unavailable' };
    res.status(status).json(payload);
  }
}

router.get('/', async (req, res) => {
  await proxyConfig(req, res, '/api/config', 'get');
});

router.post('/', async (req, res) => {
  await proxyConfig(req, res, '/api/config', 'post');
});

router.put('/', async (req, res) => {
  await proxyConfig(req, res, '/api/config', 'post');
});

router.get('/sections', async (req, res) => {
  await proxyConfig(req, res, '/api/config/sections', 'get');
});

module.exports = router;
