import { useState, useEffect } from 'react'
import { Layout, Menu, theme } from 'antd'
import {
  DashboardOutlined,
  ShoppingOutlined,
  SettingOutlined,
  TeamOutlined,
  LineChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'

const { Sider } = Layout

interface SidebarProps {
  collapsed: boolean
  setCollapsed: (collapsed: boolean) => void
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed, setCollapsed }) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: '仪表盘',
    },
    {
      key: '/publish',
      icon: <ShoppingOutlined />,
      label: '商品发布',
    },
    {
      key: '/operations',
      icon: <SettingOutlined />,
      label: '运营管理',
    },
    {
      key: '/accounts',
      icon: <TeamOutlined />,
      label: '账号管理',
    },
    {
      key: '/analytics',
      icon: <LineChartOutlined />,
      label: '数据分析',
    },
  ]

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
  }

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={collapsed}
      theme="light"
      style={{
        overflow: 'auto',
        height: '100vh',
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
        borderRight: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      <div
        style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 24px',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        {!collapsed ? (
          <span style={{ fontSize: 18, fontWeight: 'bold', color: token.colorPrimary }}>
            🦞 闲鱼自动化工具
          </span>
        ) : (
          <span style={{ fontSize: 24 }}>🦞</span>
        )}
      </div>

      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={handleMenuClick}
        style={{ marginTop: 16 }}
      />

      <div
        style={{
          position: 'absolute',
          bottom: 16,
          left: 0,
          right: 0,
          padding: '0 16px',
        }}
      >
        <div
          style={{
            cursor: 'pointer',
            padding: '8px 12px',
            borderRadius: 6,
            backgroundColor: token.colorBgTextHover,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      </div>
    </Sider>
  )
}

export default Sidebar
