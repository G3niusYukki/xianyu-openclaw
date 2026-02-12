import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, DatePicker, Button, Select, Table, Space, Divider, message } from 'antd'
import { DownloadOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import dayjs from 'dayjs'

const { RangePicker } = DatePicker
const { Option } = Select

const Analytics: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [reportType, setReportType] = useState<'daily' | 'weekly' | 'monthly'>('daily')

  const mockTrendData = [
    { date: '02-06', views: 1234, wants: 56, revenue: 8900 },
    { date: '02-07', views: 1567, wants: 78, revenue: 12300 },
    { date: '02-08', views: 1423, wants: 65, revenue: 9800 },
    { date: '02-09', views: 1789, wants: 89, revenue: 15600 },
    { date: '02-10', views: 1654, wants: 72, revenue: 13400 },
    { date: '02-11', views: 1890, wants: 95, revenue: 17800 },
    { date: '02-12', views: 2100, wants: 108, revenue: 19800 },
  ]

  const mockProductData = [
    { id: 'item_001', name: 'iPhone 15 Pro 256GB', views: 2345, wants: 108, revenue: 6999, conversion: 4.6 },
    { id: 'item_002', name: 'MacBook Pro M3', views: 890, wants: 23, revenue: 12999, conversion: 2.6 },
    { id: 'item_003', name: 'AirPods Pro 2', views: 3456, wants: 156, revenue: 1599, conversion: 4.5 },
  ]

  const productColumns = [
    { title: '商品名称', dataIndex: 'name', key: 'name' },
    { title: '浏览量', dataIndex: 'views', key: 'views' },
    { title: '想要数', dataIndex: 'wants', key: 'wants' },
    { title: '成交价', dataIndex: 'revenue', key: 'revenue', render: (v: number) => `¥${v}` },
    { title: '转化率', dataIndex: 'conversion', key: 'conversion', render: (v: number) => `${v}%` },
  ]

  const handleGenerateReport = async () => {
    setLoading(true)
    try {
      await new Promise(resolve => setTimeout(resolve, 2000))
      message.success('报表生成成功')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    setLoading(true)
    try {
      await new Promise(resolve => setTimeout(resolve, 1500))
      message.success('数据已导出')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>📈 数据分析</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>
          查看运营报表、趋势分析和商品数据
        </p>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="今日新增"
              value={12}
              suffix="个"
              valueStyle={{ color: '#3f8600' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="今日浏览"
              value={2100}
              valueStyle={{ color: '#cf1322' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="今日成交"
              value={108}
              valueStyle={{ color: '#3f8600' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="今日营收"
              value={19800}
              precision={0}
              prefix="¥"
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Space>
            <Select
              value={reportType}
              onChange={setReportType}
              style={{ width: 120 }}
            >
              <Option value="daily">日报</Option>
              <Option value="weekly">周报</Option>
              <Option value="monthly">月报</Option>
            </Select>
            <RangePicker />
            <Button type="primary" loading={loading} onClick={handleGenerateReport}>
              生成报表
            </Button>
            <Button icon={<DownloadOutlined />} loading={loading} onClick={handleExport}>
              导出数据
            </Button>
          </Space>
        </div>

        <Divider />

        <h3 style={{ marginBottom: 16 }}>📊 数据趋势</h3>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={mockTrendData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis yAxisId="left" />
            <YAxis yAxisId="right" orientation="right" />
            <Tooltip />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="views" stroke="#ff6a00" name="浏览量" strokeWidth={2} />
            <Line yAxisId="right" type="monotone" dataKey="wants" stroke="#1890ff" name="想要数" strokeWidth={2} />
            <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="#52c41a" name="营收" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="🏆 商品排行榜">
            <Table
              dataSource={mockProductData}
              columns={productColumns}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="📦 成交分布">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={mockProductData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="views" fill="#ff6a00" name="浏览量" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default Analytics
