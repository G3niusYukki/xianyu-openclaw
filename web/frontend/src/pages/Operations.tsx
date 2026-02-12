import React, { useState } from 'react'
import { Card, Tabs, Button, InputNumber, Slider, Table, message, Row, Col, Select, Space, Tag } from 'antd'
import { ReloadOutlined, DeleteOutlined, DollarOutlined } from '@ant-design/icons'

const { TabPane } = Tabs
const { Option } = Select

const Operations: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [polishSettings, setPolishSettings] = useState({
    maxItems: 50,
    delayMin: 3,
    delayMax: 6,
  })

  const mockProducts = [
    { id: 'item_001', title: 'iPhone 15 Pro 256GB', price: 6999, views: 1234, wants: 56 },
    { id: 'item_002', title: 'MacBook Pro M3', price: 12999, views: 890, wants: 23 },
    { id: 'item_003', title: 'AirPods Pro 2', price: 1599, views: 2345, wants: 89 },
  ]

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
      await new Promise(resolve => setTimeout(resolve, 2000))
      message.success(`成功擦亮 ${polishSettings.maxItems} 个商品`)
    } catch (error) {
      message.error('批量擦亮失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSinglePolish = async (productId: string) => {
    try {
      await new Promise(resolve => setTimeout(resolve, 500))
      message.success(`商品 ${productId} 擦亮成功`)
    } catch (error) {
      message.error('擦亮失败')
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
                💡 擦亮可以提高商品在搜索结果中的排名，建议每天执行一次
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

              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={loading}
                onClick={handleBatchPolish}
                size="large"
              >
                开始批量擦亮
              </Button>
            </div>

            <Divider />

            <h4>商品列表</h4>
            <Table
              dataSource={mockProducts}
              columns={[
                ...productColumns,
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
              pagination={false}
            />
          </TabPane>

          <TabPane tab="价格调整" key="price">
            <div style={{ marginBottom: 24 }}>
              <Row gutter={24}>
                <Col span={8}>
                  <Card title="单个调整">
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>
                        <label style={{ display: 'block', marginBottom: 8 }}>商品ID</label>
                        <Select placeholder="选择商品" style={{ width: '100%' }}>
                          {mockProducts.map(p => (
                            <Option key={p.id} value={p.id}>{p.title}</Option>
                          ))}
                        </Select>
                      </div>
                      <div>
                        <label style={{ display: 'block', marginBottom: 8 }}>新价格（元）</label>
                        <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="0.00" />
                      </div>
                      <Button type="primary" icon={<DollarOutlined />} block>
                        更新价格
                      </Button>
                    </Space>
                  </Card>
                </Col>
                <Col span={16}>
                  <Card title="批量调整">
                    <p style={{ color: 'rgba(0,0,0,0.45)', marginBottom: 16 }}>
                      支持从Excel/CSV文件批量调整商品价格
                    </p>
                    <Button type="dashed" block style={{ height: 120 }}>
                      点击上传文件
                    </Button>
                  </Card>
                </Col>
              </Row>
            </div>
          </TabPane>

          <TabPane tab="商品管理" key="manage">
            <div style={{ marginBottom: 24 }}>
              <Space>
                <Button danger icon={<DeleteOutlined />}>
                  批量下架
                </Button>
                <Button type="primary">
                  重新上架
                </Button>
              </Space>
            </div>

            <Table
              dataSource={mockProducts}
              columns={[
                ...productColumns,
                {
                  title: '状态',
                  dataIndex: 'status',
                  key: 'status',
                  render: () => <Tag color="green">在售</Tag>,
                },
                {
                  title: '操作',
                  key: 'action',
                  render: (_: any, record: any) => (
                    <Space>
                      <Button type="link" danger size="small">
                        下架
                      </Button>
                      <Button type="link" size="small">
                        编辑
                      </Button>
                    </Space>
                  ),
                },
              ]}
              rowKey="id"
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  )
}

export default Operations
