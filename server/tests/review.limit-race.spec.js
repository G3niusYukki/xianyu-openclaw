const request = require('supertest');
const express = require('express');

jest.mock('../src/middleware/auth', () => ({
  auth: (req, res, next) => {
    req.user = { id: 1, language: 'en' };
    next();
  }
}));

jest.mock('../src/config/database', () => ({
  transaction: jest.fn(async (cb) => cb({ id: 'tx' }))
}));

jest.mock('../src/models/User', () => ({
  update: jest.fn(),
  findByPk: jest.fn(),
  decrement: jest.fn()
}));

jest.mock('../src/models/Review', () => ({
  create: jest.fn()
}));

jest.mock('../src/services/codeReviewService', () => ({
  reviewCode: jest.fn(),
  PLAN_CONFIGS: {
    free: { limit: 5 },
    basic: { limit: 50 },
    pro: { limit: 200 },
    team: { limit: 1000 }
  }
}));

const User = require('../src/models/User');
const Review = require('../src/models/Review');
const { reviewCode } = require('../src/services/codeReviewService');
const reviewRoutes = require('../src/routes/review');

describe('review quota atomicity', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  function createTestApp() {
    const app = express();
    app.use(express.json());
    app.use('/api/review', reviewRoutes);
    return app;
  }

  test('accepts analyze when atomic quota update succeeds', async () => {
    const app = createTestApp();

    User.update.mockResolvedValue([1]);
    Review.create.mockResolvedValue({ id: 123, update: jest.fn() });
    reviewCode.mockResolvedValue({
      issues: [],
      summary: 'ok',
      issuesFound: 0,
      securityIssues: 0,
      performanceIssues: 0,
      bestPracticeIssues: 0,
      processingTime: 1
    });

    const resp = await request(app)
      .post('/api/review/analyze')
      .send({ code: 'print(1)', language: 'python' });

    expect(resp.status).toBe(202);
    expect(resp.body.reviewId).toBe(123);
    expect(User.update).toHaveBeenCalledTimes(1);
  });

  test('rejects analyze when quota already exhausted', async () => {
    const app = createTestApp();

    User.update.mockResolvedValue([0]);
    User.findByPk.mockResolvedValue({ reviewsLimit: 5, reviewsUsed: 5 });

    const resp = await request(app)
      .post('/api/review/analyze')
      .send({ code: 'print(1)', language: 'python' });

    expect(resp.status).toBe(403);
    expect(resp.body.error).toBe('Review limit exceeded');
    expect(Review.create).not.toHaveBeenCalled();
  });
});
