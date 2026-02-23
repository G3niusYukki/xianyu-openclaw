import React, { useEffect, useMemo, useState } from 'react'
import { Card, Row, Col, Statistic, DatePicker, Button, Select, Table, Space, Divider, message } from 'antd'
import { DownloadOutlined, ArrowUpOutlined } from '@ant-design/icons'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { api, ProductPerformance } from '../services'

const { RangePicker } = DatePicker
const { Option } = Select

type ReportType = 'daily' | 'weekly' | 'monthly'

const Analytics: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [reportType, setReportType] = useState<ReportType>('daily')
  const [dashboard, setDashboard] = useState<any>({})
  const [dailyReport, setDailyReport] = useState<any>({})
  const [trendData, setTrendData] = useState<Array<{ date: string; value: number }>>([])
  const [productData, setProductData] = useState<ProductPerformance[]>([])
  const [reportData, setReportData] = useState<any>(null)

  const loadAnalyticsData = async () => {
    setLoading(true)
    try {
      const [dashboardResp, dailyResp, trendResp, productResp] = await Promise.all([
        api.dashboard.getStats(),
        api.analytics.getDailyReport(),
        api.analytics.getTrend('views', 30),
        api.analytics.getProductPerformance(30),
      ])
      if (dashboardResp.success) setDashboard(dashboardResp.data || {})
      if (dailyResp.success) setDailyReport(dailyResp.data || {})
      if (trendResp.success) {
        setTrendData((trendResp.data || []).map((item: any) => ({
          date: item.date,
          value: Number(item.value || 0),
        })))
      }
      if (productResp.success) setProductData(productResp.data || [])
    } catch (error) {
      message.error('加载分析数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAnalyticsData()
  }, [])

  const tableData = useMemo(
    () =>
      (productData || []).map((p) => ({
        id: p.product_id,
        name: p.title || p.product_id,
        views: p.total_views || 0,
        wants: p.total_wants || 0,
        revenue: p.price || 0,
        conversion: 0,
      })),
    [productData],
  )

  const productColumns = [
    { title: '商品名称', dataIndex: 'name', key: 'name' },
    { title: '浏览量', dataIndex: 'views', key: 'views' },
    { title: '想要数', dataIndex: 'wants', key: 'wants' },
    { title: '价格', dataIndex: 'revenue', key: 'revenue', render: (v: number) => `¥${v}` },
    { title: '转化率', dataIndex: 'conversion', key: 'conversion', render: (v: number) => `${v}%` },
  ]

  const handleGenerateReport = async () => {
    setLoading(true)
    try {
      let resp: any
      if (reportType === 'daily') {
        resp = await api.analytics.getDailyReport()
      } else if (reportType === 'weekly') {
        resp = await api.analytics.getWeeklyReport()
      } else {
        message.info('月报接口暂未开放，已展示周报数据')
        resp = await api.analytics.getWeeklyReport()
      }
      if (resp.success) {
        setReportData(resp.data)
        message.success('报表生成成功')
      } else {
        message.error('报表生成失败')
      }
    } catch (error) {
      message.error('报表生成失败')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    try {
      const payload = {
        dashboard,
        dailyReport,
        trendData,
        productData,
        reportType,
        reportData,
        exportedAt: new Date().toISOString(),
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `analytics-${Date.now()}.json`
      link.click()
      URL.revokeObjectURL(url)
      message.success('数据已导出')
    } catch (error) {
      message.error('数据导出失败')
    }
  }

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>📈 数据分析</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>查看运营报表、趋势分析和商品数据</p>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic title="活跃商品" value={dashboard.active_products || 0} suffix="个" prefix={<ArrowUpOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic title="今日浏览" value={dashboard.today_views || 0} prefix={<ArrowUpOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic title="今日想要" value={dashboard.today_wants || 0} prefix={<ArrowUpOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card loading={loading}>
            <Statistic title="累计营收" value={dashboard.total_revenue || 0} precision={0} prefix="¥" />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 24 }} loading={loading}>
        <div style={{ marginBottom: 16 }}>
          <Space>
            <Select value={reportType} onChange={setReportType} style={{ width: 120 }}>
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

        <h3 style={{ marginBottom: 16 }}>📊 浏览趋势（30天）</h3>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="value" stroke="#ff6a00" name="浏览量" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="🏆 商品排行榜" loading={loading}>
            <Table dataSource={tableData} columns={productColumns} rowKey="id" pagination={false} size="small" />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="📦 商品浏览分布" loading={loading}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={tableData}>
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
