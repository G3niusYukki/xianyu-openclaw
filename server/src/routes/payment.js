const express = require('express');
const router = express.Router();
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const { auth } = require('../middleware/auth');
const User = require('../models/User');
const StripeEvent = require('../models/StripeEvent');
const { PLAN_CONFIGS } = require('../services/codeReviewService');

const PRICE_IDS = {
  basic: process.env.STRIPE_BASIC_PRICE_ID,
  pro: process.env.STRIPE_PRO_PRICE_ID,
  team: process.env.STRIPE_TEAM_PRICE_ID
};

router.post('/create-checkout-session', auth, async (req, res) => {
  try {
    const { plan } = req.body;

    if (!plan || !PRICE_IDS[plan]) {
      return res.status(400).json({
        error: 'Invalid plan',
        availablePlans: Object.keys(PRICE_IDS)
      });
    }

    const user = req.user;

    let customerId = user.stripeCustomerId;

    if (!customerId) {
      const customer = await stripe.customers.create({
        email: user.email,
        metadata: {
          userId: user.id
        }
      });

      customerId = customer.id;
      await user.update({ stripeCustomerId: customerId });
    }

    const session = await stripe.checkout.sessions.create({
      customer: customerId,
      payment_method_types: ['card'],
      line_items: [
        {
          price: PRICE_IDS[plan],
          quantity: 1
        }
      ],
      mode: 'subscription',
      success_url: `${process.env.FRONTEND_URL}/payment/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${process.env.FRONTEND_URL}/pricing`,
      metadata: {
        userId: user.id,
        plan: plan
      }
    });

    res.json({
      sessionId: session.id,
      url: session.url
    });
  } catch (error) {
    console.error('Create checkout session error:', error);
    res.status(500).json({ error: 'Failed to create checkout session' });
  }
});

router.post('/webhook', async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event;

  try {
    const payload = req.rawBody || req.body;
    event = stripe.webhooks.constructEvent(
      payload,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  try {
    await StripeEvent.create({
      eventId: event.id,
      eventType: event.type
    });
  } catch (error) {
    if (error.name === 'SequelizeUniqueConstraintError') {
      return res.status(200).json({ received: true, duplicate: true });
    }

    console.error('Webhook idempotency error:', error);
    return res.status(500).json({ error: 'Webhook idempotency check failed' });
  }

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        const { userId, plan } = session.metadata;

        const user = await User.findByPk(userId);
        if (user && PLAN_CONFIGS[plan]) {
          await user.update({
            plan: plan,
            reviewsLimit: PLAN_CONFIGS[plan].limit,
            reviewsUsed: 0,
            subscriptionId: session.subscription,
            subscriptionStatus: 'active',
            currentPeriodEnd: new Date(session.expires_at * 1000)
          });
        }
        break;
      }

      case 'customer.subscription.updated': {
        const subscription = event.data.object;
        const customerId = subscription.customer;

        const user = await User.findOne({
          where: { stripeCustomerId: customerId }
        });

        if (user) {
          await user.update({
            subscriptionStatus: subscription.status,
            currentPeriodEnd: new Date(subscription.current_period_end * 1000)
          });
        }
        break;
      }

      case 'customer.subscription.deleted': {
        const subscription = event.data.object;
        const customerId = subscription.customer;

        const user = await User.findOne({
          where: { stripeCustomerId: customerId }
        });

        if (user) {
          await user.update({
            plan: 'free',
            reviewsLimit: PLAN_CONFIGS.free.limit,
            subscriptionId: null,
            subscriptionStatus: 'canceled'
          });
        }
        break;
      }

      case 'invoice.payment_failed': {
        const invoice = event.data.object;
        const customerId = invoice.customer;

        const user = await User.findOne({
          where: { stripeCustomerId: customerId }
        });

        if (user) {
          await user.update({
            subscriptionStatus: 'past_due'
          });
        }
        break;
      }
    }

    res.json({ received: true });
  } catch (error) {
    console.error('Webhook handler error:', error);
    res.status(500).json({ error: 'Webhook handler failed' });
  }
});

router.post('/create-portal-session', auth, async (req, res) => {
  try {
    const user = req.user;

    if (!user.stripeCustomerId) {
      return res.status(400).json({ error: 'No subscription found' });
    }

    const portalSession = await stripe.billingPortal.sessions.create({
      customer: user.stripeCustomerId,
      return_url: `${process.env.FRONTEND_URL}/settings/billing`
    });

    res.json({ url: portalSession.url });
  } catch (error) {
    console.error('Create portal session error:', error);
    res.status(500).json({ error: 'Failed to create portal session' });
  }
});

router.get('/plans', (req, res) => {
  const plans = Object.entries(PLAN_CONFIGS).map(([key, value]) => ({
    id: key,
    name: value.name,
    price: value.price,
    limit: value.limit,
    features: getPlanFeatures(key)
  }));

  res.json({ plans });
});

function getPlanFeatures(plan) {
  const features = {
    free: [
      '5 code reviews per month',
      'Basic security checks',
      'Email support'
    ],
    basic: [
      '50 code reviews per month',
      'Security vulnerability detection',
      'Performance optimization suggestions',
      'Email support'
    ],
    pro: [
      '200 code reviews per month',
      'Advanced security analysis',
      'Performance & best practices review',
      'Priority email support',
      'API access'
    ],
    team: [
      '1000 code reviews per month',
      'Team collaboration features',
      'All Pro features',
      'Dedicated support',
      'Custom integrations'
    ]
  };

  return features[plan] || [];
}

module.exports = router;
