import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During development proxy API calls to the FastAPI backend on :8000
export default defineConfig({
	plugins: [react()],
	optimizeDeps: {
		include: ['react', 'react-dom'],
	},
	server: {
		port: 5174,
		watch: {
			// Exclude large binary files, zip archives, and non-source dirs
			// from the file watcher to prevent freezes on this machine
			ignored: [
				'**/node_portable/**',
				'**/supptracker-improved/**',
				'**/__pycache__/**',
				'**/data/**',
				'**/backend/**',
				'**/tests/**',
				'**/.git/**',
				'**/*.zip',
				'**/*.py',
				'**/*.csv',
				'**/*.pdf',
				'**/*.sh',
				'**/*.bat',
			]
		},
		proxy: {
			// proxy the API endpoints used by the frontend
			'/search': { target: 'http://localhost:8000', changeOrigin: true },
			'/interaction': { target: 'http://localhost:8000', changeOrigin: true },
			'/stack': { target: 'http://localhost:8000', changeOrigin: true },
			// fallback for any other API paths
			'/api': { target: 'http://localhost:8000', changeOrigin: true }
		}
	}
})
