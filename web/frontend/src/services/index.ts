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

export interface AccountUpsertPayload {
  id: string
  name: string
  cookie: string
  priority: number
  enabled: boolean
}

export interface AccountHealth {
  account_id: string
  health_score: number
  total_published: number
  total_errors: number
  cookie_valid: boolean
  total_polished?: number
  last_operation?: string
  health?: string
}

export interface ScheduledTask {
  task_id: string
  task_type: string
  name: string
  cron_expression?: string
  interval?: number
  enabled: boolean
  params: Record<string, any>
  status: string
  last_run?: string
  run_count: number
  created_at: string
  last_result?: any
}

export interface TaskPayload {
  task_type: string
  name?: string
  cron_expression?: string
  interval?: number
  params?: Record<string, any>
  enabled?: boolean
}

export interface PublishPayload {
  name: string
  category: string
  price: number
  condition?: string
  reason?: string
  features?: string[]
  images?: string[]
  title?: string
  description?: string
  tags?: string[]
}

export interface OperationLog {
  id: number
  operation_type: string
  product_id?: string
  account_id?: string
  details?: string
  status?: string
  error_message?: string
  timestamp: string
}

export interface ProductPerformance {
  product_id: string
  title?: string
  price?: number
  status?: string
  total_views?: number
  total_wants?: number
}

export const api = {
  products: {
    publish: (payload: PublishPayload): Promise<{ success: boolean; data: { url?: string }; error?: string }> =>
      apiClient.post('/products/publish', payload),
  },

  dashboard: {
    getStats: (): Promise<{ success: boolean; data: DashboardStats }> =>
      apiClient.get('/dashboard/stats'),
  },
  
  accounts: {
    list: (): Promise<{ success: boolean; data: Account[] }> =>
      apiClient.get('/accounts'),
    
    getHealth: (accountId: string): Promise<{ success: boolean; data: AccountHealth }> =>
      apiClient.get(`/accounts/${accountId}/health`),

    getAllHealth: (): Promise<{ success: boolean; data: AccountHealth[] }> =>
      apiClient.get('/accounts/health'),

    create: (payload: AccountUpsertPayload): Promise<{ success: boolean }> =>
      apiClient.post('/accounts', payload),

    update: (accountId: string, payload: AccountUpsertPayload): Promise<{ success: boolean }> =>
      apiClient.put(`/accounts/${accountId}`, payload),

    remove: (accountId: string): Promise<{ success: boolean }> =>
      apiClient.delete(`/accounts/${accountId}`),

    toggle: (accountId: string, enabled: boolean): Promise<{ success: boolean }> =>
      apiClient.post(`/accounts/${accountId}/toggle`, null, { params: { enabled } }),
  },
  
  operations: {
    polish: (productId: string): Promise<{ success: boolean }> =>
      apiClient.post(`/operations/polish/${productId}`),
    
    polishBatch: (maxItems: number = 50): Promise<{ success: boolean; data: any }> =>
      apiClient.post('/operations/polish/batch', null, { params: { max_items: maxItems } }),
    
    updatePrice: (productId: string, newPrice: number, originalPrice?: number): Promise<{ success: boolean }> =>
      apiClient.post('/operations/price', { product_id: productId, new_price: newPrice, original_price: originalPrice }),

    getLogs: (limit: number = 50): Promise<{ success: boolean; data: OperationLog[] }> =>
      apiClient.get('/operations/logs', { params: { limit } }),
  },
  
  analytics: {
    getDailyReport: (): Promise<{ success: boolean; data: any }> =>
      apiClient.get('/analytics/report/daily'),
    
    getWeeklyReport: (): Promise<{ success: boolean; data: any }> =>
      apiClient.get('/analytics/report/weekly'),
    
    getTrend: (metric: string = 'views', days: number = 30): Promise<{ success: boolean; data: any[] }> =>
      apiClient.get('/analytics/trend', { params: { metric, days } }),

    getProductPerformance: (days: number = 30): Promise<{ success: boolean; data: ProductPerformance[] }> =>
      apiClient.get('/analytics/products/performance', { params: { days } }),
  },
  
  alerts: {
    list: (): Promise<{ success: boolean; data: any[] }> =>
      apiClient.get('/alerts'),
  },

  tasks: {
    list: (enabledOnly: boolean = false): Promise<{ success: boolean; data: ScheduledTask[] }> =>
      apiClient.get('/tasks', { params: { enabled_only: enabledOnly } }),

    status: (): Promise<{ success: boolean; data: any }> =>
      apiClient.get('/tasks/status'),

    create: (payload: TaskPayload): Promise<{ success: boolean; data: ScheduledTask }> =>
      apiClient.post('/tasks', payload),

    update: (taskId: string, payload: TaskPayload): Promise<{ success: boolean }> =>
      apiClient.put(`/tasks/${taskId}`, payload),

    toggle: (taskId: string, enabled: boolean): Promise<{ success: boolean }> =>
      apiClient.post(`/tasks/${taskId}/toggle`, null, { params: { enabled } }),

    runNow: (taskId: string): Promise<{ success: boolean; data: any }> =>
      apiClient.post(`/tasks/${taskId}/run`),

    remove: (taskId: string): Promise<{ success: boolean }> =>
      apiClient.delete(`/tasks/${taskId}`),
  },
}
