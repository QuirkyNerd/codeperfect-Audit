import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({ baseURL: BASE_URL, withCredentials: true });

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true;
      try {
        const refreshRes = await axios.post(`${BASE_URL}/auth/refresh`, {}, { withCredentials: true });
        const newToken   = refreshRes.data.access_token;
        sessionStorage.setItem('access_token', newToken);
        err.config.headers.Authorization = `Bearer ${newToken}`;
        return api(err.config);
      } catch {
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export const authApi = {
  login:   (data) => api.post('/auth/login', data),
  signup:  (data) => api.post('/auth/signup', data),
  me:      ()     => api.get('/auth/me'),
  refresh: ()     => api.post('/auth/refresh'),
  users:   ()     => api.get('/auth/users'),
  createUser: (data) => api.post('/auth/users', data),
  resetPassword: (id, payload) => api.patch(`/auth/users/${id}/reset-password`, payload),
  updateRole: (id, role) => api.patch(`/auth/users/${id}/role`, { role }),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
  orgs:       ()     => api.get('/auth/org'),
  createOrg:  (data) => api.post('/auth/org', data),
  branches:   ()     => api.get('/auth/branches'),
  createBranch: (data) => api.post('/auth/branches', data),
};

export const auditApi = {
  runAudit:   (data) => `${BASE_URL}/audit`,   // SSE endpoint — use EventSource
  submitFeedback: (data) => api.post('/feedback', data),
  health:     ()     => api.get('/health'),
};

export const caseApi = {
  list:   (params) => api.get('/cases', { params }),
  get:    (id)     => api.get(`/cases/${id}`),
  update: (id, data) => api.patch(`/cases/${id}`, data),
  delete: (id)     => api.delete(`/cases/${id}`),
};

export const analyticsApi = {
  overview: (days = 30, currency = 'usd') => api.get('/analytics/overview', { params: { days, currency } }),
  trends:   (days = 30, currency = 'usd') => api.get('/analytics/trends',   { params: { days, currency } }),
};

export default api;
