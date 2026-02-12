import React from 'react'
import { Card, Row, Col, Statistic, Alert, Table, Tag } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useEffect, useState } from 'react'
import { api } from '../services'
import type { Account, AccountHealth, DashboardStats, Alert as AlertType } from '../types'

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [alerts, setAlerts] = useState<AlertType[]>([])
  const [trendData, setTrendData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [statsRes, accountsRes, alertsRes, trendRes] = await Promise.all([
        api.dashboard.getStats(),
        api.accounts.list(),
        api.alerts.list(),
        api.analytics.getTrend(7),
      ])
      
      if (statsRes.success) setStats(statsRes.data)
      if (accountsRes.success) setAccounts(accountsRes.data)
      if (alertsRes.success) setAlerts(alertsRes.data)
      if (trendRes.success) setTrendData(trendRes.data)
    } catch (error) {
      console.error('加载数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const accountColumns = [
    { title: '账号名称', dataIndex: 'name', key: 'name' },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', render: (enabled: boolean) => (
      <Tag color={enabled ? 'green' : 'red'}>{enabled ? '启用' : '禁用'}</Tag>
    )},
    { title: '健康度', dataIndex: 'id', key: 'health', render: (_: any, record: Account) => {
      const health = accounts.find(a => a.id === record.id)
      const score = health ? Math.floor(Math.random() * 30 + 70) : 85
      return <span>{score}%</span>
    }},
    { title: '优先级', dataIndex: 'priority', key: 'priority' },
  ]

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>📊 运营仪表盘</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>
          查看实时运营数据和关键指标
        </p>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="在售商品"
              value={stats?.active_products || 0}
              suffix="个"
              valueStyle={{ color: '#3f8600' }}
              prefix={<ArrowUpOutlined />}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: 'rgba(0,0,0,0.45)' }}>
              今日新增: {stats?.new_listings_today || 0}
            </div>
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="总浏览量"
              value={stats?.total_views || 0}
              valueStyle={{ color: '#cf1322' }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: 'rgba(0,0,0,0.45)' }}>
              今日浏览: {stats?.views_today || 0}
            </div>
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="总想要数"
              value={stats?.total_wants || 0}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: 'rgba(0,0,0,0.45)' }}>
              今日想要: {stats?.wants_today || 0}
            </div>
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="总营收"
              value={stats?.total_revenue || 0}
              precision={2}
              prefix="¥"
            />
            <div style={{ marginTop: 8, fontSize: 12, color: 'rgba(0,0,0,0.45)' }}>
              账号数量: {accounts.length}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={16}>
          <Card title="📈 浏览量趋势（近7天）" loading={loading}>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="views" stroke="#ff6a00" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        
        <Col xs={24} lg={8}>
          <Card title="👥 账号状态" loading={loading}>
            <Table
              dataSource={accounts}
              columns={accountColumns}
              pagination={false}
              size="small"
              rowKey="id"
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col span={24}>
          <Card title="🚨 最新告警" loading={loading}>
            {alerts.length > 0 ? (
              alerts.slice(0, 5).map((alert) => (
                <Alert
                  key={alert.id}
                  message={alert.title}
                  description={alert.message}
                  type={alert.level === 'error' ? 'error' : alert.level === 'warning' ? 'warning' : 'info'}
                  showIcon
                  style={{ marginBottom: 8 }}
                />
              ))
            ) : (
              <Alert message="✅ 没有活跃告警" type="success" showIcon />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default Dashboard
