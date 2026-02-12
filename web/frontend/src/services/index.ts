import apiClient from './api'

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

export const api = {
  dashboard: {
    getStats: (): Promise<{ success: boolean; data: DashboardStats }> =>
      apiClient.get('/dashboard/stats'),
  },
  
  accounts: {
    list: (): Promise<{ success: boolean; data: Account[] }> =>
      apiClient.get('/accounts'),
    
    getHealth: (accountId: string): Promise<{ success: boolean; data: AccountHealth }> =>
      apiClient.get(`/accounts/${accountId}/health`),
  },
  
  operations: {
    polish: (productId: string): Promise<{ success: boolean }> =>
      apiClient.post(`/operations/polish/${productId}`),
    
    polishBatch: (maxItems: number = 50): Promise<{ success: boolean; data: any }> =>
      apiClient.post('/operations/polish/batch', null, { params: { max_items: maxItems } }),
    
    updatePrice: (productId: string, newPrice: number, originalPrice?: number): Promise<{ success: boolean }> =>
      apiClient.post('/operations/price', { product_id: productId, new_price: newPrice, original_price: originalPrice }),
  },
  
  analytics: {
    getDailyReport: (): Promise<{ success: boolean; data: any }> =>
      apiClient.get('/analytics/report/daily'),
    
    getWeeklyReport: (): Promise<{ success: boolean; data: any }> =>
      apiClient.get('/analytics/report/weekly'),
    
    getTrend: (days: number = 30): Promise<{ success: boolean; data: any[] }> =>
      apiClient.get('/analytics/trend', { params: { days } }),
  },
  
  alerts: {
    list: (): Promise<{ success: boolean; data: any[] }> =>
      apiClient.get('/alerts'),
  },
}
