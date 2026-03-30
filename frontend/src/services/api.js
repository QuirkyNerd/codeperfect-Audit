import axios from "axios";

const BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: false,
});

const getToken = () => localStorage.getItem("access_token");

const token = getToken();
if (token) {
  api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const originalRequest = err.config;

    if (err.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshRes = await axios.post(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: false }
        );

        const newToken = refreshRes.data.access_token;

        localStorage.setItem("access_token", newToken);

        api.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
        originalRequest.headers.Authorization = `Bearer ${newToken}`;

        return api(originalRequest);
      } catch {
        localStorage.removeItem("access_token");
        localStorage.removeItem("user");
        window.location.href = "/login";
      }
    }

    return Promise.reject(err);
  }
);

export const authApi = {
  login: async (data) => {
    const res = await api.post("/auth/login", data);

    const token = res.data.access_token;

    localStorage.setItem("access_token", token);
    localStorage.setItem("user", JSON.stringify(res.data.user));

    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;

    return res;
  },

  signup: (data) => api.post("/auth/signup", data),

  me: () => api.get("/auth/me"),

  refresh: () => api.post("/auth/refresh"),

  users: () => api.get("/auth/users"),

  createUser: (data) => api.post("/auth/users", data),

  resetPassword: (id, payload) =>
    api.patch(`/auth/users/${id}/reset-password`, payload),

  updateRole: (id, role) =>
    api.patch(`/auth/users/${id}/role`, { role }),

  deleteUser: (id) => api.delete(`/auth/users/${id}`),

  orgs: () => api.get("/auth/org"),

  createOrg: (data) => api.post("/auth/org", data),

  branches: () => api.get("/auth/branches"),

  createBranch: (data) => api.post("/auth/branches", data),
};

export const auditApi = {
  runAudit: (data) => `${BASE_URL}/audit`,
  submitFeedback: (data) => api.post("/feedback", data),
  health: () => api.get("/health"),
};

export const caseApi = {
  list: (params) => api.get("/cases", { params }),
  get: (id) => api.get(`/cases/${id}`),
  update: (id, data) => api.patch(`/cases/${id}`, data),
  delete: (id) => api.delete(`/cases/${id}`),
};

export const analyticsApi = {
  overview: (days = 30, currency = "usd") =>
    api.get("/analytics/overview", { params: { days, currency } }),

  trends: (days = 30, currency = "usd") =>
    api.get("/analytics/trends", { params: { days, currency } }),
};

export default api;