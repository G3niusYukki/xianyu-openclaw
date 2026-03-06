const request = require('supertest');

jest.mock('axios', () => jest.fn());

const axios = require('axios');
const app = require('../src/app');

describe('Config API proxy', () => {
  beforeEach(() => {
    axios.mockReset();
  });

  it('GET /api/config proxies to Python backend', async () => {
    axios.mockResolvedValueOnce({
      status: 200,
      data: { ok: true, config: { ai: { provider: 'deepseek' } } },
    });

    const res = await request(app).get('/api/config');

    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);
    expect(axios).toHaveBeenCalledWith(
      expect.objectContaining({
        method: 'get',
        url: 'http://localhost:8091/api/config',
      }),
    );
  });

  it('PUT /api/config forwards body as POST to Python backend', async () => {
    axios.mockResolvedValueOnce({
      status: 200,
      data: { ok: true, config: { ai: { provider: 'qwen' } } },
    });

    const payload = { ai: { provider: 'qwen' } };
    const res = await request(app).put('/api/config').send(payload);

    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);
    expect(axios).toHaveBeenCalledWith(
      expect.objectContaining({
        method: 'post',
        url: 'http://localhost:8091/api/config',
        data: payload,
      }),
    );
  });

  it('GET /api/config/sections returns upstream errors as 502 fallback', async () => {
    axios.mockRejectedValueOnce(new Error('connect ECONNREFUSED'));

    const res = await request(app).get('/api/config/sections');

    expect(res.status).toBe(502);
    expect(res.body).toEqual({ ok: false, error: 'Python config API unavailable' });
  });
});
