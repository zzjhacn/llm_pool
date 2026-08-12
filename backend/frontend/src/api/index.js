import axios from 'axios'

const http = axios.create({ baseURL: '' })

http.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('admin_token')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('admin_token')
      if (location.pathname !== '/login') location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export const api = {
  login: (username, password) => http.post('/admin/login', { username, password }),

  listPlatforms: () => http.get('/admin/platforms'),
  createPlatform: (d) => http.post('/admin/platforms', d),
  updatePlatform: (id, d) => http.put(`/admin/platforms/${id}`, d),
  deletePlatform: (id) => http.delete(`/admin/platforms/${id}`),

  listModels: () => http.get('/admin/models'),
  createModel: (d) => http.post('/admin/models', d),
  updateModel: (id, d) => http.put(`/admin/models/${id}`, d),
  deleteModel: (id) => http.delete(`/admin/models/${id}`),
  toggleModel: (id, enabled) => http.post(`/admin/models/${id}/toggle?enabled=${enabled}`),

  listPackages: () => http.get('/admin/packages'),
  createPackage: (d) => http.post('/admin/packages', d),
  updatePackage: (id, d) => http.put(`/admin/packages/${id}`, d),
  deletePackage: (id) => http.delete(`/admin/packages/${id}`),

  ledger: () => http.get('/admin/ledger'),
  sync: () => http.post('/admin/sync'),
  availableModels: () => http.get('/v1/models'),
}

export default http
