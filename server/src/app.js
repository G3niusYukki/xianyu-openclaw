require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');

const xianguanjiaRoutes = require('./routes/xianguanjia');
const configRoutes = require('./routes/config');

const app = express();

app.use(helmet());
app.use(cors({
  origin: process.env.FRONTEND_URL || '*',
  credentials: true
}));
app.use(morgan('combined'));
app.use(express.json({
  limit: '10mb',
  verify: (req, res, buf) => {
    const rawBodyPaths = ['/api/xgj/order/receive', '/api/xgj/product/receive'];
    if (rawBodyPaths.some(p => req.originalUrl.startsWith(p))) {
      req.rawBody = buf;
    }
  }
}));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

app.use('/api/xgj', xianguanjiaRoutes);
app.use('/api/config', configRoutes);

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    error: 'Internal server error',
    message: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

const PORT = process.env.PORT || 3001;

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
    console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  });
}

module.exports = app;
