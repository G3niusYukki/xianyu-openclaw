import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Fish, Menu, X, Settings } from 'lucide-react'

const Navbar = () => {
  const [isOpen, setIsOpen] = React.useState(false)
  const location = useLocation()

  const navLinks = [
    { to: '/dashboard', label: '工作台' },
    { to: '/products', label: '商品' },
    { to: '/orders', label: '订单' },
    { to: '/messages', label: '消息' },
  ]

  const isActive = (path: string): boolean => location.pathname === path || location.pathname.startsWith(path + '/')
  const isConfigActive = isActive('/config')

  return (
    <nav className="bg-xy-surface/90 backdrop-blur border-b border-xy-border sticky top-0 z-30" role="navigation" aria-label="主导航">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2" aria-label="返回首页">
              <div className="bg-xy-brand-50 p-1.5 rounded-lg">
                <Fish className="h-6 w-6 text-xy-brand-500" />
              </div>
              <span className="text-lg font-bold text-xy-text-primary hidden sm:block">闲鱼管家</span>
            </Link>

            <div className="hidden md:flex items-center gap-1">
              {navLinks.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  aria-current={isActive(item.to) ? 'page' : undefined}
                  className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-xy-brand-500 ${
                    isActive(item.to)
                      ? 'text-xy-brand-600 bg-xy-brand-50'
                      : 'text-xy-text-secondary hover:text-xy-brand-500 hover:bg-xy-gray-50'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>

          <div className="hidden md:flex items-center gap-4">
            <Link
              to="/config"
              className={`p-2 rounded-lg transition-colors ${
                isConfigActive
                  ? 'bg-xy-brand-50 text-xy-brand-600'
                  : 'hover:bg-xy-gray-50 text-xy-text-secondary'
              }`}
              title="系统配置" aria-label="系统配置"
            >
              <Settings className="w-5 h-5" />
            </Link>
          </div>

          <div className="md:hidden flex items-center gap-2">
            <button onClick={() => setIsOpen(!isOpen)} className="text-xy-text-secondary p-1" aria-label={isOpen ? '关闭菜单' : '打开菜单'}>
              {isOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </div>

      {isOpen && (
        <div className="md:hidden border-t border-xy-border bg-white pb-3 shadow-lg">
          <div className="px-4 py-2 space-y-1 border-b border-xy-border mb-2">
            {navLinks.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={`block py-2 px-3 text-base font-medium rounded-lg ${
                  isActive(item.to)
                    ? 'text-xy-brand-600 bg-xy-brand-50'
                    : 'text-xy-text-primary hover:bg-xy-gray-50'
                }`}
                onClick={() => setIsOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="px-4 space-y-1">
            <Link
              to="/config"
              className={`block py-2 px-3 text-sm rounded-lg ${
                isConfigActive
                  ? 'text-xy-brand-600 bg-xy-brand-50 font-medium'
                  : 'text-xy-text-secondary hover:bg-xy-gray-50'
              }`}
              onClick={() => setIsOpen(false)}
            >
              系统配置
            </Link>
          </div>
        </div>
      )}
    </nav>
  )
}

export default Navbar
