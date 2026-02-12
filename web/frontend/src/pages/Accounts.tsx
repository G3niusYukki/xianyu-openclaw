import React, { useState, useEffect } from 'react'
import { Card, Table, Button, Modal, Form, Input, InputNumber, message, Tabs, Badge, Space, Tag } from 'antd'
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { Account } from '../types'

const { TabPane } = Tabs
const { TextArea } = Input

const Accounts: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([
    { id: 'account_1', name: '主账号', enabled: true, priority: 1, cookie: '' },
    { id: 'account_2', name: '副账号', enabled: true, priority: 2, cookie: '' },
  ])
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

  const columns = [
    {
      title: '账号名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Badge status={enabled ? 'success' : 'default'} text={enabled ? '启用' : '禁用'} />
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (priority: number) => <Tag>{priority}</Tag>,
    },
    {
      title: '健康度',
      key: 'health',
      render: () => <span style={{ color: '#52c41a' }}>85%</span>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Account) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const handleAdd = () => {
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (account: Account) => {
    form.setFieldsValue(account)
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个账号吗？',
      onOk: () => {
        setAccounts(accounts.filter(a => a.id !== id))
        message.success('删除成功')
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      const newAccount: Account = {
        id: `account_${Date.now()}`,
        ...values,
      }
      
      setAccounts([...accounts, newAccount])
      setModalVisible(false)
      message.success('账号添加成功')
    } catch (error) {
      message.error('添加失败')
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = (id: string) => {
    setAccounts(accounts.map(a => 
      a.id === id ? { ...a, enabled: !a.enabled } : a
    ))
  }

  const mockTasks = [
    { id: 'task_1', name: '每日擦亮', type: 'polish', enabled: true, cron: '0 9 * * *', lastRun: '2024-02-12 09:00' },
    { id: 'task_2', name: '数据采集', type: 'metrics', enabled: true, cron: '0 */4 * * *', lastRun: '2024-02-12 08:00' },
    { id: 'task_3', name: '健康检查', type: 'health_check', enabled: false, cron: '0 10 * * *', lastRun: '2024-02-11 10:00' },
  ]

  const taskColumns = [
    { title: '任务名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (type: string) => {
      const typeMap: { [key: string]: string } = {
        polish: '擦亮',
        metrics: '数据采集',
        health_check: '健康检查',
      }
      return typeMap[type] || type
    }},
    { title: 'Cron表达式', dataIndex: 'cron', key: 'cron', code: true },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', render: (enabled: boolean) => (
      <Badge status={enabled ? 'processing' : 'default'} text={enabled ? '运行中' : '已暂停'} />
    )},
    { title: '上次运行', dataIndex: 'lastRun', key: 'lastRun' },
    { title: '操作', key: 'action', render: () => (
      <Space>
        <Button type="link" size="small" icon={<ReloadOutlined />}>立即执行</Button>
        <Button type="link" size="small">编辑</Button>
      </Space>
    )},
  ]

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>👥 账号管理</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>
          管理多个闲鱼账号，设置定时任务
        </p>
      </div>

      <Card>
        <Tabs defaultActiveKey="accounts">
          <TabPane tab="账号列表" key="accounts">
            <div style={{ marginBottom: 16 }}>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                添加账号
              </Button>
            </div>

            <Table
              dataSource={accounts}
              columns={columns}
              rowKey="id"
              pagination={false}
            />
          </TabPane>

          <TabPane tab="定时任务" key="tasks">
            <div style={{ marginBottom: 16 }}>
              <Button type="primary" icon={<PlusOutlined />}>
                创建任务
              </Button>
            </div>

            <Table
              dataSource={mockTasks}
              columns={taskColumns}
              rowKey="id"
              pagination={false}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title={form.getFieldValue('id') ? '编辑账号' : '添加账号'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={loading}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="账号名称"
            rules={[{ required: true, message: '请输入账号名称' }]}
          >
            <Input placeholder="例如：主账号" />
          </Form.Item>

          <Form.Item
            name="priority"
            label="优先级"
            rules={[{ required: true, message: '请输入优先级' }]}
          >
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="cookie"
            label="Cookie"
            rules={[{ required: true, message: '请输入Cookie' }]}
          >
            <TextArea rows={6} placeholder="从浏览器开发者工具中复制Cookie" />
          </Form.Item>

          <div style={{ padding: 12, backgroundColor: '#f5f5f5', borderRadius: 4 }}>
            <p style={{ margin: 0, fontSize: 12, color: 'rgba(0,0,0,0.65)' }}>
              💡 如何获取Cookie：<br />
              1. 在浏览器中登录闲鱼<br />
              2. 按F12打开开发者工具<br />
              3. 切换到Network标签<br />
              4. 刷新页面，找到任意请求<br />
              5. 在Request Headers中复制Cookie
            </p>
          </div>
        </Form>
      </Modal>
    </div>
  )
}

export default Accounts
