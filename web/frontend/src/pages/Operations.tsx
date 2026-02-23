import React, { useEffect, useMemo, useState } from 'react'
import { Card, Tabs, Button, InputNumber, Slider, Table, message, Row, Col, Select, Space, Tag, Divider, Input } from 'antd'
import { ReloadOutlined, DollarOutlined } from '@ant-design/icons'
import { api, OperationLog, ProductPerformance } from '../services'

const { TabPane } = Tabs
const { Option } = Select

const Operations: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [logsLoading, setLogsLoading] = useState(false)
  const [logs, setLogs] = useState<OperationLog[]>([])
  const [products, setProducts] = useState<ProductPerformance[]>([])
  const [singleProductId, setSingleProductId] = useState('')
  const [priceProductId, setPriceProductId] = useState<string | undefined>()
  const [newPrice, setNewPrice] = useState<number | null>(null)
  const [polishSettings, setPolishSettings] = useState({
    maxItems: 50,
    delayMin: 3,
    delayMax: 6,
  })

  const loadData = async () => {
    setLogsLoading(true)
    try {
      const [logResp, productResp] = await Promise.all([
        api.operations.getLogs(50),
        api.analytics.getProductPerformance(30),
      ])
      if (logResp.success) setLogs(logResp.data || [])
      if (productResp.success) setProducts(productResp.data || [])
    } catch (error) {
      message.error('加载运营数据失败')
    } finally {
      setLogsLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  const selectableProductIds = useMemo(() => {
    const fromPerformance = (products || []).map((p) => p.product_id).filter(Boolean)
    const fromLogs = (logs || []).map((l) => l.product_id || '').filter(Boolean)
    return Array.from(new Set([...fromPerformance, ...fromLogs]))
  }, [products, logs])

  const productRows = useMemo(() => {
    if (products.length > 0) {
      return products.map((p) => ({
        id: p.product_id,
        title: p.title || p.product_id,
        price: p.price || 0,
        views: p.total_views || 0,
        wants: p.total_wants || 0,
        status: p.status || 'unknown',
      }))
    }
    return logs
      .filter((l) => l.product_id)
      .map((l) => ({
        id: l.product_id as string,
        title: l.product_id as string,
        price: 0,
        views: 0,
        wants: 0,
        status: 'unknown',
      }))
  }, [products, logs])

  const productColumns = [
    { title: '商品ID', dataIndex: 'id', key: 'id' },
    { title: '商品名称', dataIndex: 'title', key: 'title' },
    { title: '价格', dataIndex: 'price', key: 'price', render: (price: number) => `¥${price}` },
    { title: '浏览量', dataIndex: 'views', key: 'views' },
    { title: '想要数', dataIndex: 'wants', key: 'wants' },
  ]

  const handleBatchPolish = async () => {
    setLoading(true)
    try {
      const resp = await api.operations.polishBatch(polishSettings.maxItems)
      if (!resp.success) {
        message.error('批量擦亮失败')
        return
      }
      message.success(`批量擦亮完成，成功 ${resp.data?.success ?? 0} 个`)
      await loadData()
    } catch (error) {
      message.error('批量擦亮失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSinglePolish = async (productId?: string) => {
    const targetId = (productId || singleProductId).trim()
    if (!targetId) {
      message.warning('请先输入商品ID')
      return
    }
    try {
      const resp = await api.operations.polish(targetId)
      if (!resp.success) {
        message.error('擦亮失败')
        return
      }
      message.success(`商品 ${targetId} 擦亮成功`)
      await loadData()
    } catch (error) {
      message.error('擦亮失败')
    }
  }

  const handleUpdatePrice = async () => {
    if (!priceProductId) {
      message.warning('请选择商品')
      return
    }
    if (newPrice === null || Number.isNaN(newPrice)) {
      message.warning('请输入新价格')
      return
    }

    setLoading(true)
    try {
      const resp = await api.operations.updatePrice(priceProductId, Number(newPrice))
      if (!resp.success) {
        message.error('更新价格失败')
        return
      }
      message.success('价格更新成功')
      await loadData()
    } catch (error) {
      message.error('更新价格失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>⚙️ 运营管理</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>
          批量擦亮、价格调整、商品管理等运营操作
        </p>
      </div>

      <Card>
        <Tabs defaultActiveKey="polish">
          <TabPane tab="批量擦亮" key="polish">
            <div style={{ marginBottom: 24 }}>
              <p style={{ color: 'rgba(0,0,0,0.45)', marginBottom: 16 }}>
                擦亮可以提高商品在搜索结果中的排名，建议每天执行一次
              </p>

              <Row gutter={24} style={{ marginBottom: 24 }}>
                <Col span={8}>
                  <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
                    擦亮商品数量: {polishSettings.maxItems}
                  </label>
                  <Slider
                    min={10}
                    max={200}
                    step={10}
                    value={polishSettings.maxItems}
                    onChange={(value) => setPolishSettings({ ...polishSettings, maxItems: value })}
                  />
                </Col>
                <Col span={8}>
                  <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
                    最小间隔: {polishSettings.delayMin}秒
                  </label>
                  <Slider
                    min={1}
                    max={10}
                    value={polishSettings.delayMin}
                    onChange={(value) => setPolishSettings({ ...polishSettings, delayMin: value })}
                  />
                </Col>
                <Col span={8}>
                  <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
                    最大间隔: {polishSettings.delayMax}秒
                  </label>
                  <Slider
                    min={1}
                    max={10}
                    value={polishSettings.delayMax}
                    onChange={(value) => setPolishSettings({ ...polishSettings, delayMax: value })}
                  />
                </Col>
              </Row>

              <Space>
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  loading={loading}
                  onClick={handleBatchPolish}
                  size="large"
                >
                  开始批量擦亮
                </Button>
                <Input
                  placeholder="输入商品ID执行单个擦亮"
                  value={singleProductId}
                  onChange={(e) => setSingleProductId(e.target.value)}
                  style={{ width: 300 }}
                />
                <Button icon={<ReloadOutlined />} onClick={() => handleSinglePolish()}>
                  单个擦亮
                </Button>
              </Space>
            </div>

            <Divider />

            <h4>商品列表</h4>
            <Table
              loading={logsLoading}
              dataSource={productRows}
              columns={[
                ...productColumns,
                {
                  title: '状态',
                  dataIndex: 'status',
                  key: 'status',
                  render: (status: string) => (
                    <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag>
                  ),
                },
                {
                  title: '操作',
                  key: 'action',
                  render: (_: any, record: any) => (
                    <Button
                      type="link"
                      icon={<ReloadOutlined />}
                      onClick={() => handleSinglePolish(record.id)}
                    >
                      擦亮
                    </Button>
                  ),
                },
              ]}
              rowKey="id"
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="价格调整" key="price">
            <div style={{ marginBottom: 24 }}>
              <Card title="单个调整">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <label style={{ display: 'block', marginBottom: 8 }}>商品ID</label>
                    <Select
                      placeholder="选择商品"
                      style={{ width: '100%' }}
                      value={priceProductId}
                      onChange={(value) => setPriceProductId(value)}
                      showSearch
                      optionFilterProp="children"
                    >
                      {selectableProductIds.map((id) => (
                        <Option key={id} value={id}>
                          {id}
                        </Option>
                      ))}
                    </Select>
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 8 }}>新价格（元）</label>
                    <InputNumber
                      style={{ width: '100%' }}
                      min={0}
                      precision={2}
                      placeholder="0.00"
                      value={newPrice as number | null}
                      onChange={(value) => setNewPrice(value)}
                    />
                  </div>
                  <Button type="primary" icon={<DollarOutlined />} block loading={loading} onClick={handleUpdatePrice}>
                    更新价格
                  </Button>
                </Space>
              </Card>
            </div>
          </TabPane>

          <TabPane tab="最近操作" key="logs">
            <Table
              loading={logsLoading}
              dataSource={logs}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: '时间', dataIndex: 'timestamp', key: 'timestamp' },
                { title: '操作类型', dataIndex: 'operation_type', key: 'operation_type' },
                { title: '商品ID', dataIndex: 'product_id', key: 'product_id' },
                { title: '账号', dataIndex: 'account_id', key: 'account_id' },
                {
                  title: '状态',
                  dataIndex: 'status',
                  key: 'status',
                  render: (status: string) => (
                    <Tag color={status === 'success' ? 'green' : 'red'}>{status || 'unknown'}</Tag>
                  ),
                },
              ]}
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  )
}

export default Operations
