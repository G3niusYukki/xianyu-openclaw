const request = require('supertest');
const express = require('express');

const mockConstructEvent = jest.fn();

jest.mock('stripe', () => {
  return jest.fn(() => ({
    webhooks: {
      constructEvent: mockConstructEvent
    },
    customers: { create: jest.fn() },
    checkout: { sessions: { create: jest.fn() } },
    billingPortal: { sessions: { create: jest.fn() } }
  }));
});

jest.mock('../src/models/User', () => ({
  findByPk: jest.fn(),
  findOne: jest.fn()
}));

jest.mock('../src/models/StripeEvent', () => ({
  create: jest.fn()
}));

const User = require('../src/models/User');
const StripeEvent = require('../src/models/StripeEvent');
const paymentRoutes = require('../src/routes/payment');

describe('payment webhook', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  function createTestApp() {
    const app = express();

    app.use(express.json({
      verify: (req, res, buf) => {
        if (req.originalUrl === '/api/payment/webhook') {
          req.rawBody = buf;
        }
      }
    }));

    app.use('/api/payment', paymentRoutes);
    return app;
  }

  test('uses raw body for stripe signature verification', async () => {
    const app = createTestApp();

    const update = jest.fn().mockResolvedValue();
    User.findByPk.mockResolvedValue({ update });
    StripeEvent.create.mockResolvedValue({ id: 1 });

    mockConstructEvent.mockReturnValue({
      id: 'evt_1',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { userId: 1, plan: 'basic' },
          subscription: 'sub_1',
          expires_at: 2000000000
        }
      }
    });

    const payload = JSON.stringify({ hello: 'world' });
    const resp = await request(app)
      .post('/api/payment/webhook')
      .set('stripe-signature', 'sig_test')
      .set('content-type', 'application/json')
      .send(payload);

    expect(resp.status).toBe(200);
    expect(mockConstructEvent).toHaveBeenCalledTimes(1);

    const calledPayload = mockConstructEvent.mock.calls[0][0];
    expect(Buffer.isBuffer(calledPayload)).toBe(true);
    expect(calledPayload.toString()).toBe(payload);
  });

  test('rejects invalid stripe signature', async () => {
    const app = createTestApp();

    const update = jest.fn().mockResolvedValue();
    User.findByPk.mockResolvedValue({ update });

    mockConstructEvent.mockImplementation(() => {
      throw new Error('No signatures found matching the expected signature for payload');
    });

    const payload = JSON.stringify({ hello: 'world' });
    const resp = await request(app)
      .post('/api/payment/webhook')
      .set('stripe-signature', 'sig_bad')
      .set('content-type', 'application/json')
      .send(payload);

    expect(resp.status).toBe(400);
    expect(resp.text).toContain('Webhook Error');
    expect(StripeEvent.create).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });

  test('deduplicates duplicated stripe event id', async () => {
    const app = createTestApp();

    const update = jest.fn().mockResolvedValue();
    User.findByPk.mockResolvedValue({ update });

    mockConstructEvent.mockReturnValue({
      id: 'evt_dup',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { userId: 1, plan: 'basic' },
          subscription: 'sub_1',
          expires_at: 2000000000
        }
      }
    });

    StripeEvent.create
      .mockResolvedValueOnce({ id: 1 })
      .mockRejectedValueOnce({ name: 'SequelizeUniqueConstraintError' });

    const payload = JSON.stringify({ hello: 'world' });

    const first = await request(app)
      .post('/api/payment/webhook')
      .set('stripe-signature', 'sig_test')
      .set('content-type', 'application/json')
      .send(payload);

    const second = await request(app)
      .post('/api/payment/webhook')
      .set('stripe-signature', 'sig_test')
      .set('content-type', 'application/json')
      .send(payload);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(second.body).toEqual({ received: true, duplicate: true });
    expect(update).toHaveBeenCalledTimes(1);
  });

  test('marks subscription as past_due on invoice.payment_failed', async () => {
    const app = createTestApp();
    const update = jest.fn().mockResolvedValue();

    User.findOne.mockResolvedValue({ update });
    StripeEvent.create.mockResolvedValue({ id: 1 });
    mockConstructEvent.mockReturnValue({
      id: 'evt_failed',
      type: 'invoice.payment_failed',
      data: {
        object: {
          customer: 'cus_123'
        }
      }
    });

    const payload = JSON.stringify({ invoice: 'failed' });
    const resp = await request(app)
      .post('/api/payment/webhook')
      .set('stripe-signature', 'sig_test')
      .set('content-type', 'application/json')
      .send(payload);

    expect(resp.status).toBe(200);
    expect(User.findOne).toHaveBeenCalledWith({ where: { stripeCustomerId: 'cus_123' } });
    expect(update).toHaveBeenCalledWith({ subscriptionStatus: 'past_due' });
  });

  test('downgrades plan on customer.subscription.deleted', async () => {
    const app = createTestApp();
    const update = jest.fn().mockResolvedValue();

    User.findOne.mockResolvedValue({ update });
    StripeEvent.create.mockResolvedValue({ id: 1 });
    mockConstructEvent.mockReturnValue({
      id: 'evt_deleted',
      type: 'customer.subscription.deleted',
      data: {
        object: {
          customer: 'cus_456'
        }
      }
    });

    const payload = JSON.stringify({ sub: 'deleted' });
    const resp = await request(app)
      .post('/api/payment/webhook')
      .set('stripe-signature', 'sig_test')
      .set('content-type', 'application/json')
      .send(payload);

    expect(resp.status).toBe(200);
    expect(User.findOne).toHaveBeenCalledWith({ where: { stripeCustomerId: 'cus_456' } });
    expect(update).toHaveBeenCalledWith({
      plan: 'free',
      reviewsLimit: 5,
      subscriptionId: null,
      subscriptionStatus: 'canceled'
    });
  });
});
