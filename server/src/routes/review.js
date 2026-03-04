const express = require('express');
const router = express.Router();
const { auth } = require('../middleware/auth');
const { Op, literal } = require('sequelize');
const sequelize = require('../config/database');
const Review = require('../models/Review');
const User = require('../models/User');
const { reviewCode } = require('../services/codeReviewService');
const multer = require('multer');

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 5 * 1024 * 1024 }
});

router.post('/analyze', auth, async (req, res) => {
  try {
    const { code, language, fileName, repository, branch } = req.body;

    if (!code || !language) {
      return res.status(400).json({
        error: 'Missing required fields',
        required: ['code', 'language']
      });
    }

    if (code.length > 100000) {
      return res.status(400).json({
        error: 'Code too large',
        maxSize: '100KB'
      });
    }

    let review;

    await sequelize.transaction(async (transaction) => {
      const [affectedRows] = await User.update(
        { reviewsUsed: literal('"reviewsUsed" + 1') },
        {
          where: {
            id: req.user.id,
            reviewsUsed: { [Op.lt]: literal('"reviewsLimit"') }
          },
          transaction
        }
      );

      if (affectedRows !== 1) {
        const freshUser = await User.findByPk(req.user.id, { transaction });
        const error = new Error('REVIEW_LIMIT_EXCEEDED');
        error.statusCode = 403;
        error.payload = {
          error: 'Review limit exceeded',
          message: 'You have reached your monthly review limit. Please upgrade your plan.',
          limit: freshUser?.reviewsLimit,
          used: freshUser?.reviewsUsed
        };
        throw error;
      }

      review = await Review.create({
        userId: req.user.id,
        codeContent: code,
        language,
        fileName,
        repository,
        branch,
        status: 'processing'
      }, { transaction });
    });

    reviewCode(code, language, { language: req.user.language })
      .then(async (result) => {
        await review.update({
          status: 'completed',
          result: result.issues,
          summary: result.summary,
          issuesFound: result.issuesFound,
          securityIssues: result.securityIssues,
          performanceIssues: result.performanceIssues,
          bestPracticeIssues: result.bestPracticeIssues,
          processingTime: result.processingTime
        });
      })
      .catch(async (error) => {
        console.error('Review processing error:', error);
        await review.update({
          status: 'failed',
          errorMessage: error.message
        });

        await User.decrement('reviewsUsed', {
          by: 1,
          where: {
            id: req.user.id,
            reviewsUsed: { [Op.gt]: 0 }
          }
        });
      });

    res.status(202).json({
      message: 'Review started',
      reviewId: review.id,
      status: 'processing'
    });
  } catch (error) {
    if (error.statusCode) {
      return res.status(error.statusCode).json(error.payload);
    }

    console.error('Create review error:', error);
    res.status(500).json({ error: 'Failed to create review' });
  }
});

router.get('/status/:id', auth, async (req, res) => {
  try {
    const review = await Review.findOne({
      where: {
        id: req.params.id,
        userId: req.user.id
      }
    });

    if (!review) {
      return res.status(404).json({ error: 'Review not found' });
    }

    res.json({
      id: review.id,
      status: review.status,
      result: review.result,
      summary: review.summary,
      issuesFound: review.issuesFound,
      securityIssues: review.securityIssues,
      performanceIssues: review.performanceIssues,
      bestPracticeIssues: review.bestPracticeIssues,
      processingTime: review.processingTime,
      errorMessage: review.errorMessage,
      createdAt: review.createdAt
    });
  } catch (error) {
    console.error('Get review status error:', error);
    res.status(500).json({ error: 'Failed to get review status' });
  }
});

router.get('/history', auth, async (req, res) => {
  try {
    const { page = 1, limit = 20, status } = req.query;
    const offset = (page - 1) * limit;

    const whereClause = { userId: req.user.id };
    if (status) {
      whereClause.status = status;
    }

    const { count, rows: reviews } = await Review.findAndCountAll({
      where: whereClause,
      order: [['createdAt', 'DESC']],
      limit: parseInt(limit),
      offset: parseInt(offset),
      attributes: [
        'id', 'fileName', 'language', 'status', 'repository',
        'issuesFound', 'securityIssues', 'performanceIssues',
        'bestPracticeIssues', 'processingTime', 'createdAt'
      ]
    });

    res.json({
      reviews,
      pagination: {
        total: count,
        page: parseInt(page),
        pages: Math.ceil(count / limit),
        limit: parseInt(limit)
      }
    });
  } catch (error) {
    console.error('Get history error:', error);
    res.status(500).json({ error: 'Failed to get review history' });
  }
});

router.get('/:id', auth, async (req, res) => {
  try {
    const review = await Review.findOne({
      where: {
        id: req.params.id,
        userId: req.user.id
      }
    });

    if (!review) {
      return res.status(404).json({ error: 'Review not found' });
    }

    res.json({
      id: review.id,
      fileName: review.fileName,
      repository: review.repository,
      branch: review.branch,
      codeContent: review.codeContent,
      language: review.language,
      status: review.status,
      result: review.result,
      summary: review.summary,
      issuesFound: review.issuesFound,
      securityIssues: review.securityIssues,
      performanceIssues: review.performanceIssues,
      bestPracticeIssues: review.bestPracticeIssues,
      processingTime: review.processingTime,
      errorMessage: review.errorMessage,
      createdAt: review.createdAt,
      updatedAt: review.updatedAt
    });
  } catch (error) {
    console.error('Get review error:', error);
    res.status(500).json({ error: 'Failed to get review' });
  }
});

router.delete('/:id', auth, async (req, res) => {
  try {
    const review = await Review.findOne({
      where: {
        id: req.params.id,
        userId: req.user.id
      }
    });

    if (!review) {
      return res.status(404).json({ error: 'Review not found' });
    }

    await review.destroy();

    res.json({ message: 'Review deleted successfully' });
  } catch (error) {
    console.error('Delete review error:', error);
    res.status(500).json({ error: 'Failed to delete review' });
  }
});

module.exports = router;
