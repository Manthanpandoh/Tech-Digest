import axios from "axios";

// Backend URL is configured via environment variable.
// - Local dev: set VITE_API_BASE_URL=http://localhost:8000 in frontend/.env
// - Production: set VITE_API_BASE_URL=https://your-backend.onrender.com in Vercel dashboard
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const API = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000, // 30 second timeout
});

// Response interceptor: log errors in dev, avoid leaking details in prod
API.interceptors.response.use(
  (response) => response,
  (error) => {
    if (import.meta.env.DEV) {
      console.error("[API Error]", error.response?.status, error.config?.url);
    }
    return Promise.reject(error);
  }
);

export default API;
