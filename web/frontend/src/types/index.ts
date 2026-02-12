export interface DashboardStats {
  active_products: number
  total_views: number
  total_wants: number
  new_listings_today: number
  views_today: number
  wants_today: number
  total_revenue: number
  polished_today: number
}

export interface Account {
  id: string
  name: string
  enabled: boolean
  priority: number
  cookie: string
}

export interface AccountHealth {
  account_id: string
  health_score: number
  total_published: number
  total_errors: number
  cookie_valid: boolean
}

export interface Product {
  id: string
  title: string
  price: number
  category: string
  condition: string
  views: number
  wants: number
}

export interface Alert {
  id: string
  title: string
  message: string
  level: 'info' | 'warning' | 'error' | 'critical'
  created_at: string
}
