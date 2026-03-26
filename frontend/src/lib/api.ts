import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: BASE,
  withCredentials: false,
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;

export const authApi = {
  register: (data: { tenant_name: string; slug: string; email: string; password: string }) =>
    api.post("/api/v1/auth/register", data),
  login: (email: string, password: string) =>
    api.post("/api/v1/auth/login", { email, password }),
  me: () => api.get("/api/v1/auth/me"),
};

export const projectsApi = {
  list: (skip = 0, limit = 20) => api.get("/api/v1/projects", { params: { skip, limit } }),
  create: (data: { name: string; address: string; building_type: string; description?: string }) =>
    api.post("/api/v1/projects", data),
  get: (id: string) => api.get(`/api/v1/projects/${id}`),
  update: (id: string, data: object) => api.put(`/api/v1/projects/${id}`, data),
  delete: (id: string) => api.delete(`/api/v1/projects/${id}`),
};

export const inspectionsApi = {
  list: (projectId: string) => api.get(`/api/v1/projects/${projectId}/inspections`),
  create: (projectId: string, data: object) =>
    api.post(`/api/v1/projects/${projectId}/inspections`, data),
  get: (projectId: string, inspId: string) =>
    api.get(`/api/v1/projects/${projectId}/inspections/${inspId}`),
  requestUploadUrl: (projectId: string, inspId: string, data: object) =>
    api.post(`/api/v1/projects/${projectId}/inspections/${inspId}/files`, data),
  confirmUpload: (projectId: string, inspId: string) =>
    api.post(`/api/v1/projects/${projectId}/inspections/${inspId}/files/confirm`),
};

export const analysisApi = {
  getJob: (jobId: string) => api.get(`/api/v1/analysis/jobs/${jobId}`),
  getResults: (jobId: string, params?: object) =>
    api.get(`/api/v1/analysis/jobs/${jobId}/results`, { params }),
};

export const tracksApi = {
  list: (projectId: string, params?: object) =>
    api.get(`/api/v1/projects/${projectId}/defect-tracks`, { params }),
  get: (trackId: string) => api.get(`/api/v1/defect-tracks/${trackId}`),
  compare: (trackId: string, a: string, b: string) =>
    api.get(`/api/v1/defect-tracks/${trackId}/compare`, { params: { a, b } }),
  patch: (trackId: string, data: object) =>
    api.patch(`/api/v1/defect-tracks/${trackId}`, data),
};

export const reportsApi = {
  create: (inspId: string) => api.post(`/api/v1/inspections/${inspId}/reports`),
  download: (reportId: string) => api.get(`/api/v1/reports/${reportId}/download`),
};

export const alertsApi = {
  list: (unreadOnly = false) => api.get("/api/v1/alerts", { params: { unread_only: unreadOnly } }),
  markRead: (id: string) => api.post(`/api/v1/alerts/${id}/read`),
  markAllRead: () => api.post("/api/v1/alerts/read-all"),
};
