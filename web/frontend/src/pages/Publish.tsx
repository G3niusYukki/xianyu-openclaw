import React, { useState } from 'react'
import { Card, Form, Input, InputNumber, Select, Button, Upload, message, Steps, Divider, Row, Col, Switch, Space } from 'antd'
import { UploadOutlined, ShoppingOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'

const { Step } = Steps
const { TextArea } = Input
const { Option } = Select

const Publish: React.FC = () => {
  const [form] = Form.useForm()
  const [current, setCurrent] = useState(0)
  const [loading, setLoading] = useState(false)
  const [publishMode, setPublishMode] = useState<'single' | 'batch'>('single')
  const [fileList, setFileList] = useState<any[]>([])

  const uploadProps: UploadProps = {
    onRemove: (file) => {
      const index = fileList.indexOf(file)
      const newFileList = fileList.slice()
      newFileList.splice(index, 1)
      setFileList(newFileList)
    },
    beforeUpload: (file) => {
      setFileList([...fileList, file])
      return false
    },
    fileList,
    maxCount: 9,
    multiple: true,
    accept: 'image/*',
  }

  const steps = [
    {
      title: '基本信息',
      content: (
        <div>
          <Form.Item name="name" label="商品名称" rules={[{ required: true, message: '请输入商品名称' }]}>
            <Input placeholder="例如：iPhone 15 Pro 256GB" size="large" />
          </Form.Item>
          
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="category" label="商品分类" rules={[{ required: true }]}>
                <Select placeholder="选择分类" size="large">
                  <Option value="数码手机">数码手机</Option>
                  <Option value="电脑办公">电脑办公</Option>
                  <Option value="家居日用">家居日用</Option>
                  <Option value="服饰鞋包">服饰鞋包</Option>
                  <Option value="美妆护肤">美妆护肤</Option>
                  <Option value="运动户外">运动户外</Option>
                  <Option value="其他">其他</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="condition" label="商品成色" rules={[{ required: true }]}>
                <Select placeholder="选择成色" size="large">
                  <Option value="全新">全新</Option>
                  <Option value="99新">99新</Option>
                  <Option value="95新">95新</Option>
                  <Option value="9成新">9成新</Option>
                  <Option value="8成新">8成新</Option>
                  <Option value="使用痕迹明显">使用痕迹明显</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="price" label="售价（元）" rules={[{ required: true, message: '请输入售价' }]}>
                <InputNumber style={{ width: '100%' }} placeholder="0.00" min={0} precision={2} size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="original_price" label="原价（元）">
                <InputNumber style={{ width: '100%' }} placeholder="0.00" min={0} precision={2} size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="reason" label="出售原因">
            <TextArea rows={3} placeholder="例如：换新手机，闲置处理" />
          </Form.Item>

          <Form.Item name="features" label="商品特性">
            <TextArea rows={2} placeholder="例如：256GB, 原色钛金属, 国行（用逗号分隔）" />
          </Form.Item>
        </div>
      ),
    },
    {
      title: '图片上传',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <p style={{ color: 'rgba(0,0,0,0.45)' }}>
              上传商品图片，最多9张，建议尺寸1000x1000像素
            </p>
          </div>
          <Upload.Dragger {...uploadProps}>
            <p className="ant-upload-drag-icon">
              <UploadOutlined style={{ fontSize: 48, color: '#ff6a00' }} />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            <p className="ant-upload-hint">支持 JPG、PNG、WEBP 格式</p>
          </Upload.Dragger>
          
          <div style={{ marginTop: 16 }}>
            <Space>
              <span>已选择：</span>
              <span style={{ color: '#ff6a00' }}>{fileList.length} 张图片</span>
            </Space>
          </div>
        </div>
      ),
    },
    {
      title: '智能生成',
      content: (
        <div>
          <Form.Item name="use_ai_title" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            <span style={{ marginLeft: 8 }}>AI生成标题</span>
          </Form.Item>

          <Form.Item name="use_ai_desc" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            <span style={{ marginLeft: 8 }}>AI生成描述</span>
          </Form.Item>

          <Divider />

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="enable_delivery" valuePropName="checked" initialValue={true}>
                <Switch checkedChildren="支持" unCheckedChildren="不支持" />
                <span style={{ marginLeft: 8 }}>邮寄</span>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="enable_face" valuePropName="checked">
                <Switch checkedChildren="支持" unCheckedChildren="不支持" />
                <span style={{ marginLeft: 8 }}>面交</span>
              </Form.Item>
            </Col>
          </Row>
        </div>
      ),
    },
  ]

  const handleNext = () => {
    form.validateFields().then(() => {
      setCurrent(current + 1)
    })
  }

  const handlePrev = () => {
    setCurrent(current - 1)
  }

  const handlePublish = async () => {
    try {
      const values = await form.validateFields()
      if (fileList.length === 0) {
        message.error('请至少上传一张图片')
        return
      }

      setLoading(true)
      // TODO: 调用API发布商品
      await new Promise(resolve => setTimeout(resolve, 2000))
      
      message.success('商品发布成功！')
      form.resetFields()
      setFileList([])
      setCurrent(0)
    } catch (error) {
      console.error('发布失败:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginLeft: 200 }}>
      <div style={{ marginBottom: 24 }}>
        <h2>🛒 商品发布</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)' }}>
          简单三步，快速发布商品到闲鱼
        </p>
      </div>

      <Card>
        <div style={{ marginBottom: 24 }}>
          <Space size="large">
            <Button 
              type={publishMode === 'single' ? 'primary' : 'default'} 
              icon={<ShoppingOutlined />}
              onClick={() => setPublishMode('single')}
            >
              单个发布
            </Button>
            <Button 
              type={publishMode === 'batch' ? 'primary' : 'default'} 
              onClick={() => setPublishMode('batch')}
            >
              批量发布
            </Button>
          </Space>
        </div>

        {publishMode === 'single' ? (
          <>
            <Steps current={current} style={{ marginBottom: 32 }}>
              <Step title="基本信息" />
              <Step title="图片上传" />
              <Step title="智能生成" />
            </Steps>

            <Form form={form} layout="vertical">
              <div className="steps-content">{steps[current].content}</div>
            </Form>

            <div style={{ marginTop: 32, textAlign: 'right' }}>
              {current > 0 && (
                <Button style={{ marginRight: 8 }} onClick={handlePrev}>
                  上一步
                </Button>
              )}
              {current < steps.length - 1 && (
                <Button type="primary" onClick={handleNext}>
                  下一步
                </Button>
              )}
              {current === steps.length - 1 && (
                <Button type="primary" loading={loading} onClick={handlePublish}>
                  立即发布
                </Button>
              )}
            </div>
          </>
        ) : (
          <div>
            <div style={{ textAlign: 'center', padding: '48px 0' }}>
              <ShoppingOutlined style={{ fontSize: 64, color: 'rgba(0,0,0,0.2)' }} />
              <p style={{ marginTop: 16, color: 'rgba(0,0,0,0.45)' }}>
                批量发布功能，支持从Excel/CSV导入商品信息
              </p>
              <Button type="primary" style={{ marginTop: 16 }}>
                下载模板
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

export default Publish
