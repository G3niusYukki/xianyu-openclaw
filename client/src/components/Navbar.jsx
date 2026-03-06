import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Fish, Menu, X, Settings, LogOut, User } from 'lucide-react'
import AccountSelector from './business/AccountSelector'

const Navbar = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = React.useState(false)
  const [showUserMenu, setShowUserMenu] = React.useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navLinks = [
    { to: '/dashboard', label: '工作台' },
    { to: '/products', label: '商品' },
    { to: '/orders', label: '订单' },
    { to: '/messages', label: '消息' },
  ]

  return (
    <nav className="bg-xy-surface/90 backdrop-blur border-b border-xy-border sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2">
              <div className="bg-xy-brand-50 p-1.5 rounded-lg">
                <Fish className="h-6 w-6 text-xy-brand-500" />
              </div>
              <span className="text-lg font-bold text-xy-text-primary hidden sm:block">闲鱼管家</span>
            </Link>
            
            {user && (
              <div className="hidden md:flex items-center gap-4">
                {navLinks.map((item) => (
                  <Link key={item.to} to={item.to} className="text-sm font-medium text-xy-text-secondary hover:text-xy-brand-500 transition-colors">
                    {item.label}
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="hidden md:flex items-center gap-4">
            {user && <AccountSelector />}

            {user ? (
              <div className="relative">
                <button 
                  onClick={() => setShowUserMenu(!showUserMenu)}
                  className="flex items-center gap-2 hover:bg-xy-gray-50 px-2 py-1.5 rounded-lg transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-xy-brand-100 text-xy-brand-600 flex items-center justify-center font-bold text-sm">
                    {user.username?.[0]?.toUpperCase() || 'U'}
                  </div>
                  <span className="text-sm font-medium text-xy-text-primary">{user.username}</span>
                </button>

                {showUserMenu && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)}></div>
                    <div className="absolute right-0 mt-2 w-48 bg-white rounded-xl shadow-lg border border-xy-border z-50 py-1">
                      <div className="px-4 py-2 border-b border-xy-border">
                        <p className="text-sm font-medium text-xy-text-primary truncate">{user.username}</p>
                        <p className="text-xs text-xy-text-secondary truncate">{user.email}</p>
                      </div>
                      <Link to="/settings" onClick={() => setShowUserMenu(false)} className="flex items-center gap-2 px-4 py-2 text-sm text-xy-text-primary hover:bg-xy-gray-50">
                        <User className="w-4 h-4 text-xy-text-secondary" /> 用户设置
                      </Link>
                      <Link to="/config" onClick={() => setShowUserMenu(false)} className="flex items-center gap-2 px-4 py-2 text-sm text-xy-text-primary hover:bg-xy-gray-50">
                        <Settings className="w-4 h-4 text-xy-text-secondary" /> 系统配置
                      </Link>
                      <div className="h-px bg-xy-border my-1"></div>
                      <button onClick={handleLogout} className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50">
                        <LogOut className="w-4 h-4" /> 退出登录
                      </button>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <Link to="/login" className="text-sm font-medium text-xy-text-secondary hover:text-xy-text-primary">登录</Link>
                <Link to="/register" className="xy-btn-primary">免费注册</Link>
              </div>
            )}
          </div>

          <div className="md:hidden flex items-center gap-2">
            {user && <div className="scale-90"><AccountSelector /></div>}
            <button onClick={() => setIsOpen(!isOpen)} className="text-xy-text-secondary p-1">
              {isOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </div>

      {isOpen && (
        <div className="md:hidden border-t border-xy-border bg-white pb-3 shadow-lg">
          {user && (
            <div className="px-4 py-2 space-y-1 border-b border-xy-border mb-2">
              {navLinks.map((item) => (
                <Link key={item.to} to={item.to} className="block py-2 text-base font-medium text-xy-text-primary" onClick={() => setIsOpen(false)}>
                  {item.label}
                </Link>
              ))}
            </div>
          )}
          <div className="px-4 space-y-1">
            {user ? (
              <>
                <Link to="/settings" className="block py-2 text-sm text-xy-text-secondary" onClick={() => setIsOpen(false)}>用户设置</Link>
                <Link to="/config" className="block py-2 text-sm text-xy-text-secondary" onClick={() => setIsOpen(false)}>系统配置</Link>
                <button onClick={handleLogout} className="block w-full text-left py-2 text-sm text-red-600">退出登录</button>
              </>
            ) : (
              <div className="flex flex-col gap-2 pt-2">
                <Link to="/login" className="xy-btn-secondary w-full text-center" onClick={() => setIsOpen(false)}>登录</Link>
                <Link to="/register" className="xy-btn-primary w-full text-center" onClick={() => setIsOpen(false)}>注册</Link>
              </div>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}

export default Navbar
