const request = require('supertest');
const app = require('../src/app');

describe('Config API', () => {
  it('GET /api/config returns 200 with ok: true', async () => {
    const res = await request(app).get('/api/config');
    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);
  });

  it('PUT /api/config returns 200 with ok: true', async () => {
    const res = await request(app)
      .put('/api/config')
      .send({ ai: { provider: 'deepseek' } });
    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);
  });

  it('GET /api/config/sections returns 200 with sections array', async () => {
    const res = await request(app).get('/api/config/sections');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body.sections)).toBe(true);
    expect(res.body.sections.length).toBeGreaterThan(0);

    const keys = res.body.sections.map(s => s.key);
    expect(keys).toContain('pricing');
    expect(keys).toContain('delivery');
  });
});
