import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Fish, Menu, X } from 'lucide-react'

const Navbar = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = React.useState(false)

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const guestLinks = [
    { to: '/detail', label: '详情' },
    { to: '/publish', label: '发布' },
    { to: '/chat', label: '聊天' },
    { to: '/orders', label: '订单' }
  ]

  return (
    <nav className="bg-white/90 backdrop-blur border-b border-slate-200 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link to="/" className="flex items-center">
              <Fish className="h-7 w-7 text-orange-500" />
              <span className="ml-2 text-xl font-bold text-slate-900">闲鱼前端</span>
            </Link>
          </div>

          <div className="hidden md:flex items-center space-x-6">
            {guestLinks.map((item) => (
              <Link key={item.to} to={item.to} className="text-slate-600 hover:text-slate-900 transition">
                {item.label}
              </Link>
            ))}

            {user ? (
              <>
                <Link to="/dashboard" className="text-slate-600 hover:text-slate-900 transition">Dashboard</Link>
                <button onClick={handleLogout} className="text-slate-600 hover:text-slate-900 transition">Logout</button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-slate-600 hover:text-slate-900 transition">Login</Link>
                <Link to="/register" className="xy-btn-primary px-4 py-2 font-medium">Get Started</Link>
              </>
            )}
          </div>

          <div className="md:hidden flex items-center">
            <button onClick={() => setIsOpen(!isOpen)} className="text-slate-600">
              {isOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </div>

      {isOpen && (
        <div className="md:hidden border-t border-slate-200 bg-white">
          <div className="px-3 py-2 space-y-1">
            {guestLinks.map((item) => (
              <Link key={item.to} to={item.to} className="block px-3 py-2 text-slate-600 hover:bg-slate-50 rounded-lg" onClick={() => setIsOpen(false)}>
                {item.label}
              </Link>
            ))}
            {user ? (
              <button onClick={handleLogout} className="block w-full text-left px-3 py-2 text-slate-600 hover:bg-slate-50 rounded-lg">
                Logout
              </button>
            ) : (
              <>
                <Link to="/login" className="block px-3 py-2 text-slate-600 hover:bg-slate-50 rounded-lg" onClick={() => setIsOpen(false)}>Login</Link>
                <Link to="/register" className="block px-3 py-2 text-slate-600 hover:bg-slate-50 rounded-lg" onClick={() => setIsOpen(false)}>Register</Link>
              </>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}

export default Navbar
