import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './hooks/useAuth'
import { AccountProvider } from './contexts/AccountContext'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Review from './pages/Review'
import History from './pages/History'
import Pricing from './pages/Pricing'
import Settings from './pages/Settings'
import PrivateRoute from './components/PrivateRoute'
import Detail from './pages/Detail'
import Publish from './pages/Publish'
import Chat from './pages/Chat'
import Orders from './pages/Orders'
import AutoPublish from './pages/products/AutoPublish'
import ProductList from './pages/products/ProductList'
import AccountList from './pages/accounts/AccountList'
import SystemConfig from './pages/config/SystemConfig'
import Analytics from './pages/analytics/Analytics'
import Messages from './pages/messages/Messages'

function App() {
  return (
    <AuthProvider>
      <AccountProvider>
        <Router>
          <div className="min-h-screen bg-xy-bg text-xy-text-primary">
            <Navbar />
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/detail" element={<Detail />} />
              <Route path="/publish" element={<Publish />} />
              <Route path="/chat" element={<Navigate to="/messages" replace />} />
              <Route
                path="/orders"
                element={
                  <PrivateRoute>
                    <Orders />
                  </PrivateRoute>
                }
              />
              <Route
                path="/products"
                element={
                  <PrivateRoute>
                    <ProductList />
                  </PrivateRoute>
                }
              />
              <Route
                path="/products/auto-publish"
                element={
                  <PrivateRoute>
                    <AutoPublish />
                  </PrivateRoute>
                }
              />
              <Route
                path="/accounts"
                element={
                  <PrivateRoute>
                    <AccountList />
                  </PrivateRoute>
                }
              />
              <Route
                path="/config"
                element={
                  <PrivateRoute>
                    <SystemConfig />
                  </PrivateRoute>
                }
              />
              <Route
                path="/analytics"
                element={
                  <PrivateRoute>
                    <Analytics />
                  </PrivateRoute>
                }
              />
              <Route
                path="/messages"
                element={
                  <PrivateRoute>
                    <Messages />
                  </PrivateRoute>
                }
              />
              <Route
                path="/dashboard"
                element={
                  <PrivateRoute>
                    <Dashboard />
                  </PrivateRoute>
                }
              />
              <Route
                path="/review"
                element={
                  <PrivateRoute>
                    <Review />
                  </PrivateRoute>
                }
              />
              <Route
                path="/review/:id"
                element={
                  <PrivateRoute>
                    <div>Review Detail Page Placeholder</div>
                  </PrivateRoute>
                }
              />
              <Route
                path="/history"
                element={
                  <PrivateRoute>
                    <History />
                  </PrivateRoute>
                }
              />
              <Route
                path="/history/:id"
                element={<Navigate to="/review/:id" replace />}
              />
              <Route
                path="/settings"
                element={
                  <PrivateRoute>
                    <Settings />
                  </PrivateRoute>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
            <Toaster position="top-right" toastOptions={{ className: 'text-sm font-medium' }} />
          </div>
        </Router>
      </AccountProvider>
    </AuthProvider>
  )
}

export default App
