import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// During development proxy API calls to the FastAPI backend on :8000
export default defineConfig(({ mode }) => {
  const apiTarget = loadEnv(mode, '.', 'SUPPTRACKER_DEV_API_TARGET').SUPPTRACKER_DEV_API_TARGET || 'http://localhost:8000'

  return {
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // proxy the API endpoints used by the frontend
      '/search': { target: apiTarget, changeOrigin: true },
      '/interaction': { target: apiTarget, changeOrigin: true },
      '/stack': { target: apiTarget, changeOrigin: true },
      // fallback for any other API paths
      // The trailing slash matters: a bare '/api' prefix also swallows the source module /api.ts,
      // which left the page blank in development.
      '/api/': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
  },
  }
})
