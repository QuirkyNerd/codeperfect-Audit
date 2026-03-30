import axios from "axios";

/**
 * Base URL
 */
const BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

/**
 * Axios instance
 */
const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

/**
 * 🔥 ALWAYS USE localStorage (multi-tab support)
 */
const getToken = () => localStorage.getItem("access_token");

/**
 * 🔥 SET TOKEN GLOBALLY ON APP LOAD
 */
const token = getToken();
if (token) {
  api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
}

/**
 * 🔥 REQUEST INTERCEPTOR
 */
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * 🔥 RESPONSE INTERCEPTOR (REFRESH TOKEN HANDLING)
 */
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const originalRequest = err.config;

    if (
      err.response?.status === 401 &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;

      try {
        const refreshRes = await axios.post(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true }
        );

        const newToken = refreshRes.data.access_token;

        // ✅ STORE NEW TOKEN
        localStorage.setItem("access_token", newToken);

        // ✅ SET HEADER
        api.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
        originalRequest.headers.Authorization = `Bearer ${newToken}`;

        return api(originalRequest);
      } catch (refreshError) {
        // ❌ LOGOUT
        localStorage.removeItem("access_token");
        localStorage.removeItem("user");

        window.location.href = "/login";
      }
    }

    return Promise.reject(err);
  }
);

/**
 * 🔥 AUTH APIs
 */
export const authApi = {
  login: async (data) => {
    const res = await api.post("/auth/login", data);

    // ✅ STORE TOKEN AFTER LOGIN
    const token = res.data.access_token;

    localStorage.setItem("access_token", token);
    localStorage.setItem("user", JSON.stringify(res.data.user));

    // ✅ SET GLOBAL HEADER
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

/**
 * 🔥 AUDIT APIs
 */
export const auditApi = {
  runAudit: (data) => `${BASE_URL}/audit`, // SSE
  submitFeedback: (data) => api.post("/feedback", data),
  health: () => api.get("/health"),
};

/**
 * 🔥 CASE APIs
 */
export const caseApi = {
  list: (params) => api.get("/cases", { params }),
  get: (id) => api.get(`/cases/${id}`),
  update: (id, data) => api.patch(`/cases/${id}`, data),
  delete: (id) => api.delete(`/cases/${id}`),
};

/**
 * 🔥 ANALYTICS APIs
 */
export const analyticsApi = {
  overview: (days = 30, currency = "usd") =>
    api.get("/analytics/overview", { params: { days, currency } }),

  trends: (days = 30, currency = "usd") =>
    api.get("/analytics/trends", { params: { days, currency } }),
};

export default api;