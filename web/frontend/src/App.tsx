import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from 'antd'
import Sidebar from './components/layout/Sidebar'
import Dashboard from './pages/Dashboard'
import Publish from './pages/Publish'
import Operations from './pages/Operations'
import Accounts from './pages/Accounts'
import Analytics from './pages/Analytics'

const { Content } = Layout

function App() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
      <Layout>
        <Content style={{ margin: '16px', overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/publish" element={<Publish />} />
            <Route path="/operations" element={<Operations />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/analytics" element={<Analytics />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

export default App
