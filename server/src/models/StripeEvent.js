const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');

const StripeEvent = sequelize.define('StripeEvent', {
  id: {
    type: DataTypes.INTEGER,
    primaryKey: true,
    autoIncrement: true
  },
  eventId: {
    type: DataTypes.STRING,
    allowNull: false,
    unique: true
  },
  eventType: {
    type: DataTypes.STRING,
    allowNull: false
  },
  processedAt: {
    type: DataTypes.DATE,
    allowNull: false,
    defaultValue: DataTypes.NOW
  }
}, {
  timestamps: true,
  indexes: [
    { unique: true, fields: ['eventId'] },
    { fields: ['eventType'] }
  ]
});

module.exports = StripeEvent;
