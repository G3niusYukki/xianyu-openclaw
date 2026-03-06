import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import ErrorBoundary from './components/ErrorBoundary'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Orders from './pages/Orders'
import AutoPublish from './pages/products/AutoPublish'
import ProductList from './pages/products/ProductList'
import AccountList from './pages/accounts/AccountList'
import SystemConfig from './pages/config/SystemConfig'
import Analytics from './pages/analytics/Analytics'
import Messages from './pages/messages/Messages'

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <div className="min-h-screen bg-xy-bg text-xy-text-primary">
          <Navbar />
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/products" element={<ProductList />} />
            <Route path="/products/auto-publish" element={<AutoPublish />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/messages" element={<Messages />} />
            <Route path="/accounts" element={<AccountList />} />
            <Route path="/config" element={<SystemConfig />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
          <Toaster position="top-right" toastOptions={{ className: 'text-sm font-medium' }} />
        </div>
      </Router>
    </ErrorBoundary>
  )
}

export default App
