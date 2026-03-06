const request = require('supertest');
const app = require('../src/app');

describe('XianGuanJia Proxy API', () => {
  it('POST /api/xgj/proxy without apiPath returns 400', async () => {
    const res = await request(app)
      .post('/api/xgj/proxy')
      .send({ payload: {} });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid apiPath');
  });

  it('POST /api/xgj/proxy with invalid apiPath returns 400', async () => {
    const res = await request(app)
      .post('/api/xgj/proxy')
      .send({ apiPath: '/admin/secret', payload: {} });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid apiPath');
  });

  it('POST /api/xgj/proxy with non-string apiPath returns 400', async () => {
    const res = await request(app)
      .post('/api/xgj/proxy')
      .send({ apiPath: 123 });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid apiPath');
  });
});
