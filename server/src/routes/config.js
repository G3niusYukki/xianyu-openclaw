const express = require('express');
const fs = require('fs');
const path = require('path');
const router = express.Router();
const CONFIG_FILE = path.join(__dirname, '../../data/system_config.json');

const ALLOWED_SECTIONS = new Set([
  'xianguanjia', 'ai', 'oss', 'auto_reply', 'auto_publish', 'order_reminder',
  'pricing', 'delivery', 'notifications',
]);

function readConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
    }
  } catch (e) {
    console.error('Failed to read config:', e.message);
  }
  return {};
}

function writeConfig(data) {
  try {
    const dir = path.dirname(CONFIG_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const tmp = CONFIG_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
    fs.renameSync(tmp, CONFIG_FILE);
  } catch (err) {
    console.error('Failed to write config:', err.message);
    throw err;
  }
}

const SENSITIVE_KEYS = ['app_secret', 'api_key', 'access_key_secret', 'mch_secret', 'webhook'];

router.get('/', (req, res) => {
  const config = readConfig();
  res.json({ ok: true, config });
});

router.put('/', (req, res) => {
  const current = readConfig();
  const updates = req.body || {};

  for (const [section, values] of Object.entries(updates)) {
    if (!ALLOWED_SECTIONS.has(section)) {
      continue;
    }
    if (typeof values === 'object' && values !== null && !Array.isArray(values)) {
      const clean = {};
      for (const [k, v] of Object.entries(values)) {
        if (typeof k === 'string' && !k.startsWith('__')) {
          if (SENSITIVE_KEYS.some(s => k.toLowerCase().includes(s))
              && typeof v === 'string' && v.includes('****')) {
            continue;
          }
          clean[k] = v;
        }
      }
      current[section] = { ...(current[section] || {}), ...clean };
    }
  }

  writeConfig(current);
  res.json({ ok: true, message: 'Configuration updated', config: current });
});

router.get('/sections', (req, res) => {
  res.json({
    ok: true,
    sections: [
      {
        key: 'xianguanjia',
        name: '闲管家配置',
        fields: [
          { key: 'mode', label: '接入模式', type: 'select', options: ['self_developed', 'business'], default: 'self_developed', labels: { self_developed: '自研应用', business: '商务对接' }, hint: '自研应用：个人或自有 ERP 直连；商务对接：第三方代商家接入' },
          { key: 'app_key', label: 'AppKey', type: 'text', required: true, hint: '在闲管家开放平台创建应用后获取' },
          { key: 'app_secret', label: 'AppSecret', type: 'password', required: true, hint: '应用密钥，请妥善保管不要泄露' },
          { key: 'seller_id', label: '商家 ID (Seller ID)', type: 'text', required_when: { mode: 'business' }, hint: '商务对接模式下的商家标识，自研模式无需填写' },
          { key: 'base_url', label: 'API 网关', type: 'text', default: 'https://open.goofish.pro', hint: '默认无需修改，仅在私有化部署时更改' },
        ],
      },
      {
        key: 'ai',
        name: 'AI 配置',
        fields: [
          { key: 'provider', label: '提供商', type: 'select', options: ['qwen', 'deepseek', 'openai'], default: 'qwen', labels: { qwen: '百炼千问 (Qwen)', deepseek: 'DeepSeek', openai: 'OpenAI' } },
          { key: 'api_key', label: 'API Key', type: 'text', required: true },
          { key: 'model', label: '模型', type: 'combobox', default: 'qwen-plus-latest', options: ['qwen-plus-latest', 'qwen-max-latest', 'qwen-turbo-latest', 'qwen-flash', 'qwen3-max', 'qwen3.5-plus', 'qwq-plus-latest'] },
          { key: 'base_url', label: 'API 地址', type: 'text', placeholder: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
        ],
      },
      {
        key: 'oss',
        name: '阿里云 OSS',
        fields: [
          { key: 'access_key_id', label: 'Access Key ID', type: 'text', required: true },
          { key: 'access_key_secret', label: 'Access Key Secret', type: 'password', required: true },
          { key: 'bucket', label: 'Bucket', type: 'text', required: true },
          { key: 'endpoint', label: 'Endpoint', type: 'text', required: true },
          { key: 'prefix', label: '路径前缀', type: 'text', default: 'xianyu/listing/' },
          { key: 'custom_domain', label: '自定义域名', type: 'text' },
        ],
      },
      {
        key: 'auto_reply',
        name: '自动回复',
        fields: [
          { key: 'enabled', label: '启用', type: 'toggle', default: true },
          { key: 'ai_intent_enabled', label: 'AI意图识别', type: 'toggle', default: false },
          { key: 'default_reply', label: '默认回复', type: 'textarea' },
          { key: 'virtual_default_reply', label: '虚拟商品默认回复', type: 'textarea' },
        ],
      },
      {
        key: 'auto_publish',
        name: '自动上架',
        fields: [
          { key: 'enabled', label: '启用', type: 'toggle', default: false },
          { key: 'default_category', label: '默认品类', type: 'select', options: ['express', 'recharge', 'exchange', 'account', 'movie_ticket', 'game'], default: 'exchange' },
          { key: 'auto_compliance', label: '自动合规检查', type: 'toggle', default: true },
        ],
      },
      {
        key: 'order_reminder',
        name: '催单设置',
        fields: [
          { key: 'enabled', label: '启用', type: 'toggle', default: true },
          { key: 'max_daily', label: '每日最大次数', type: 'number', default: 2 },
          { key: 'min_interval_hours', label: '最小间隔(小时)', type: 'number', default: 4 },
          { key: 'silent_start', label: '静默开始(时)', type: 'number', default: 22 },
          { key: 'silent_end', label: '静默结束(时)', type: 'number', default: 8 },
        ],
      },
      {
        key: 'pricing',
        name: '定价规则',
        fields: [
          { key: 'auto_adjust', label: '自动调价', type: 'toggle', default: false },
          { key: 'min_margin_percent', label: '最低利润率(%)', type: 'number', default: 10 },
          { key: 'max_discount_percent', label: '最大降价幅度(%)', type: 'number', default: 20 },
        ],
      },
      {
        key: 'delivery',
        name: '发货规则',
        fields: [
          { key: 'auto_delivery', label: '自动发货', type: 'toggle', default: true },
          { key: 'delivery_timeout_minutes', label: '发货超时(分钟)', type: 'number', default: 30 },
          { key: 'notify_on_delivery', label: '发货通知', type: 'toggle', default: true },
        ],
      },
      {
        key: 'notifications',
        name: '告警通知',
        fields: [
          { key: 'feishu_enabled', label: '飞书通知', type: 'toggle', default: false },
          { key: 'feishu_webhook', label: '飞书 Webhook URL', type: 'password', placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/xxx' },
          { key: 'wechat_enabled', label: '企业微信通知', type: 'toggle', default: false },
          { key: 'wechat_webhook', label: '企业微信 Webhook URL', type: 'password', placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx' },
          { key: 'notify_cookie_expire', label: 'Cookie 过期告警', type: 'toggle', default: true },
          { key: 'notify_cookie_refresh', label: 'Cookie 刷新成功通知', type: 'toggle', default: true },
          { key: 'notify_sla_alert', label: 'SLA 异常告警', type: 'toggle', default: true },
          { key: 'notify_order_fail', label: '订单异常告警', type: 'toggle', default: true },
          { key: 'notify_after_sales', label: '售后介入告警', type: 'toggle', default: true },
          { key: 'notify_ship_fail', label: '发货失败告警', type: 'toggle', default: true },
          { key: 'notify_manual_takeover', label: '人工接管告警', type: 'toggle', default: true },
        ],
      },
    ],
  });
});

module.exports = router;
