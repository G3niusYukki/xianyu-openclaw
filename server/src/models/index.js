const User = require('./User');
const Review = require('./Review');
const { Team, TeamMember } = require('./Team');
const StripeEvent = require('./StripeEvent');

User.hasMany(Review, {
  foreignKey: 'userId',
  as: 'reviews',
  onDelete: 'CASCADE'
});

Review.belongsTo(User, {
  foreignKey: 'userId',
  as: 'user'
});

User.hasMany(Team, {
  foreignKey: 'ownerId',
  as: 'ownedTeams'
});

Team.belongsTo(User, {
  foreignKey: 'ownerId',
  as: 'owner'
});

User.belongsToMany(Team, {
  through: TeamMember,
  as: 'teams',
  foreignKey: 'userId'
});

Team.belongsToMany(User, {
  through: TeamMember,
  as: 'members',
  foreignKey: 'teamId'
});

module.exports = {
  User,
  Review,
  Team,
  TeamMember,
  StripeEvent
};
