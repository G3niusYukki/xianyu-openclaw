import React, { useEffect, useMemo, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, InputNumber, message, Tabs, Badge, Space, Tag, Switch, Select } from 'antd'
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { api, Account, AccountHealth, ScheduledTask } from '../services'

const { TabPane } = Tabs
const { TextArea } = Input
const { Option } = Select

interface AccountFormValues {
  id: string
  name: string
  cookie: string
  priority: number
  enabled: boolean
}

interface TaskFormValues {
  task_type: string
  name: string
  cron_expression?: string
  interval?: number
  enabled: boolean
  max_items?: number
}

const Accounts: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [healthMap, setHealthMap] = useState<Record<string, AccountHealth>>({})
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState<Account | null>(null)
  const [form] = Form.useForm<AccountFormValues>()
  const [taskForm] = Form.useForm<TaskFormValues>()
  const [taskModalVisible, setTaskModalVisible] = useState(false)
  const [loading, setLoading] = useState(false)
  const [tasks, setTasks] = useState<ScheduledTask[]>([])

  const loadAccounts = async () => {
    setLoading(true)
    try {
      const [accountsResp, healthResp, tasksResp] = await Promise.all([
        api.accounts.list(),
        api.accounts.getAllHealth(),
        api.tasks.list(false),
      ])

      if (accountsResp.success) {
        setAccounts(accountsResp.data || [])
      }
      if (healthResp.success) {
        const map: Record<string, AccountHealth> = {}
        ;(healthResp.data || []).forEach((h) => {
          map[h.account_id] = h
        })
        setHealthMap(map)
      }
      if (tasksResp.success) {
        setTasks(tasksResp.data || [])
      }
    } catch (error) {
      message.error('加载账号数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAccounts()
  }, [])

  const columns = useMemo(
    () => [
      { title: '账号ID', dataIndex: 'id', key: 'id' },
      { title: '账号名称', dataIndex: 'name', key: 'name' },
      {
        title: '状态',
        dataIndex: 'enabled',
        key: 'enabled',
        render: (enabled: boolean, record: Account) => (
          <Space>
            <Badge status={enabled ? 'success' : 'default'} text={enabled ? '启用' : '禁用'} />
            <Switch
              size="small"
              checked={enabled}
              onChange={(checked) => handleToggle(record.id, checked)}
            />
          </Space>
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
        render: (_: any, record: Account) => {
          const score = healthMap[record.id]?.health_score ?? 0
          const color = score >= 80 ? '#52c41a' : score >= 50 ? '#faad14' : '#ff4d4f'
          return <span style={{ color }}>{score}%</span>
        },
      },
      {
        title: '操作',
        key: 'action',
        render: (_: any, record: Account) => (
          <Space>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
              编辑
            </Button>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)}>
              删除
            </Button>
          </Space>
        ),
      },
    ],
    [healthMap],
  )

  const handleAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ priority: 1, enabled: true } as AccountFormValues)
    setModalVisible(true)
  }

  const handleEdit = (account: Account) => {
    setEditing(account)
    form.setFieldsValue({
      id: account.id,
      name: account.name,
      cookie: account.cookie || '',
      priority: account.priority,
      enabled: account.enabled,
    })
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个账号吗？',
      onOk: async () => {
        try {
          await api.accounts.remove(id)
          message.success('删除成功')
          await loadAccounts()
        } catch (error) {
          message.error('删除失败')
        }
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      if (editing) {
        await api.accounts.update(editing.id, values)
      } else {
        await api.accounts.create(values)
      }

      setModalVisible(false)
      message.success(editing ? '账号更新成功' : '账号添加成功')
      await loadAccounts()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '保存账号失败')
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await api.accounts.toggle(id, enabled)
      await loadAccounts()
    } catch (error) {
      message.error('切换状态失败')
    }
  }

  const handleCreateTask = async () => {
    try {
      const values = await taskForm.validateFields()
      setLoading(true)
      const payload = {
        task_type: values.task_type,
        name: values.name,
        cron_expression: values.cron_expression || undefined,
        interval: values.interval || undefined,
        enabled: values.enabled,
        params: values.task_type === 'polish' ? { max_items: values.max_items || 50 } : {},
      }
      await api.tasks.create(payload)
      message.success('任务创建成功')
      setTaskModalVisible(false)
      taskForm.resetFields()
      await loadAccounts()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '创建任务失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRunTaskNow = async (taskId: string) => {
    try {
      await api.tasks.runNow(taskId)
      message.success('任务已触发执行')
      await loadAccounts()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '触发任务失败')
    }
  }

  const handleToggleTask = async (taskId: string, enabled: boolean) => {
    try {
      await api.tasks.toggle(taskId, enabled)
      await loadAccounts()
    } catch (error) {
      message.error('切换任务状态失败')
    }
  }

  const handleDeleteTask = async (taskId: string) => {
    try {
      await api.tasks.remove(taskId)
      message.success('任务删除成功')
      await loadAccounts()
    } catch (error) {
      message.error('删除任务失败')
    }
  }

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>👥 账号管理</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>管理多个闲鱼账号，设置定时任务</p>
      </div>

      <Card loading={loading}>
        <Tabs defaultActiveKey="accounts">
          <TabPane tab="账号列表" key="accounts">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                  添加账号
                </Button>
                <Button icon={<ReloadOutlined />} onClick={() => loadAccounts()}>
                  刷新
                </Button>
              </Space>
            </div>

            <Table dataSource={accounts} columns={columns as any} rowKey="id" pagination={false} />
          </TabPane>

          <TabPane tab="定时任务" key="tasks">
            <div style={{ marginBottom: 16 }}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  taskForm.resetFields()
                  taskForm.setFieldsValue({ task_type: 'polish', enabled: true, max_items: 50 } as TaskFormValues)
                  setTaskModalVisible(true)
                }}
              >
                创建任务
              </Button>
            </div>
            <Table
              dataSource={tasks}
              rowKey="task_id"
              pagination={false}
              columns={[
                { title: '任务名称', dataIndex: 'name', key: 'name' },
                { title: '类型', dataIndex: 'task_type', key: 'task_type' },
                {
                  title: '计划',
                  key: 'schedule',
                  render: (_: any, task: ScheduledTask) => task.cron_expression || (task.interval ? `${task.interval}s` : '-'),
                },
                {
                  title: '状态',
                  key: 'enabled',
                  render: (_: any, task: ScheduledTask) => (
                    <Space>
                      <Badge status={task.enabled ? 'processing' : 'default'} text={task.enabled ? '运行中' : '已暂停'} />
                      <Switch size="small" checked={task.enabled} onChange={(checked) => handleToggleTask(task.task_id, checked)} />
                    </Space>
                  ),
                },
                { title: '上次运行', dataIndex: 'last_run', key: 'last_run' },
                {
                  title: '操作',
                  key: 'action',
                  render: (_: any, task: ScheduledTask) => (
                    <Space>
                      <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => handleRunTaskNow(task.task_id)}>
                        立即执行
                      </Button>
                      <Button type="link" size="small" danger onClick={() => handleDeleteTask(task.task_id)}>
                        删除
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title={editing ? '编辑账号' : '添加账号'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={loading}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="id" label="账号ID" rules={[{ required: true, message: '请输入账号ID' }]}>
            <Input placeholder="例如：account_1" disabled={!!editing} />
          </Form.Item>

          <Form.Item name="name" label="账号名称" rules={[{ required: true, message: '请输入账号名称' }]}>
            <Input placeholder="例如：主账号" />
          </Form.Item>

          <Form.Item name="priority" label="优先级" rules={[{ required: true, message: '请输入优先级' }]}>
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item name="cookie" label="Cookie" rules={[{ required: true, message: '请输入Cookie' }]}>
            <TextArea rows={6} placeholder="从浏览器开发者工具中复制Cookie" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="创建定时任务"
        open={taskModalVisible}
        onOk={handleCreateTask}
        onCancel={() => setTaskModalVisible(false)}
        confirmLoading={loading}
      >
        <Form form={taskForm} layout="vertical">
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input placeholder="例如：每日擦亮" />
          </Form.Item>

          <Form.Item name="task_type" label="任务类型" rules={[{ required: true, message: '请选择任务类型' }]}>
            <Select>
              <Option value="polish">擦亮</Option>
              <Option value="metrics">数据采集</Option>
              <Option value="publish">发布</Option>
              <Option value="custom">自定义</Option>
            </Select>
          </Form.Item>

          <Form.Item name="cron_expression" label="Cron表达式">
            <Input placeholder="例如：0 9 * * *（每天9点）" />
          </Form.Item>

          <Form.Item name="interval" label="间隔秒数（可选）">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="max_items" label="擦亮数量（仅擦亮任务）">
            <InputNumber min={1} max={200} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Accounts
