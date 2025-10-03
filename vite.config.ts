import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During development proxy API calls to the FastAPI backend on :8000
export default defineConfig({
        plugins: [react()],
        server: {
                port: 5173,
                proxy: {
                        // proxy the API endpoints used by the frontend
                        '/search': { target: 'http://localhost:8000', changeOrigin: true },
                        '/interaction': { target: 'http://localhost:8000', changeOrigin: true },
                        '/stack': { target: 'http://localhost:8000', changeOrigin: true },
                        // fallback for any other API paths
                        '/api': { target: 'http://localhost:8000', changeOrigin: true }
                }
        },
        test: {
                environment: 'jsdom',
                setupFiles: './vitest.setup.ts'
        }
})
