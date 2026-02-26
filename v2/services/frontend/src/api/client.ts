import axios from 'axios';
import type {
  Prospect,
  Settings,
  ActivityEvent,
  AuthResponse,
  User,
  HealthStatus,
} from '@/types';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true, // send httpOnly cookie on every request
  headers: {
    'Content-Type': 'application/json',
  },
});

// Handle 401 responses — redirect to login without touching localStorage
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

// ── Prospects API ────────────────────────────────────────────────────
export const prospectApi = {
  list: async (params?: { page?: number; per_page?: number; state?: string }) => {
    const response = await api.get<{ data: Prospect[]; total: number }>('/prospects', { params });
    return response.data;
  },

  get: async (id: string) => {
    const response = await api.get<{ data: Prospect }>(`/prospects/${id}`);
    return response.data.data;
  },

  create: async (data: {
    name: string;
    email: string;
    phone?: string;
    company_domain?: string;
    title?: string;
  }) => {
    const response = await api.post<{ data: Prospect }>('/prospects', data);
    return response.data.data;
  },

  startPipeline: async (id: string) => {
    const response = await api.post<{ data: Prospect }>(`/prospects/${id}/start-pipeline`);
    return response.data.data;
  },
};

// ── Settings API ─────────────────────────────────────────────────────
export const settingsApi = {
  get: async () => {
    const response = await api.get<{ data: Settings }>('/settings');
    return response.data.data;
  },

  save: async (settings: Partial<Settings>) => {
    const response = await api.put<{ data: Settings }>('/settings', settings);
    return response.data.data;
  },
};

// ── Activity API ─────────────────────────────────────────────────────
export const activityApi = {
  getRecent: async (params?: { limit?: number; prospect_id?: string }) => {
    const response = await api.get<{ data: ActivityEvent[] }>('/activity', { params });
    return response.data.data;
  },
};

// ── Auth API ─────────────────────────────────────────────────────────
export const authApi = {
  register: async (data: { email: string; password: string; name: string }) => {
    const response = await api.post<AuthResponse>('/auth/register', data);
    return response.data;
  },

  login: async (data: { email: string; password: string }) => {
    const response = await api.post<AuthResponse>('/auth/login', data);
    return response.data;
  },

  logout: async () => {
    await api.post('/auth/logout');
  },

  getProfile: async () => {
    const response = await api.get<{ data: User }>('/auth/profile');
    return response.data.data;
  },
};

// ── Health API ───────────────────────────────────────────────────────
export const healthApi = {
  check: async () => {
    const response = await api.get<HealthStatus>('/health');
    return response.data;
  },

  ready: async () => {
    const response = await api.get<HealthStatus>('/health/ready');
    return response.data;
  },
};

export default api;
