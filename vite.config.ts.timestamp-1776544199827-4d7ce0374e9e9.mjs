// vite.config.ts
import { defineConfig } from "file:///C:/Users/Kalev/supptracker/node_modules/vite/dist/node/index.js";
import react from "file:///C:/Users/Kalev/supptracker/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // proxy the API endpoints used by the frontend
      "/search": { target: "http://localhost:8000", changeOrigin: true },
      "/interaction": { target: "http://localhost:8000", changeOrigin: true },
      "/stack": { target: "http://localhost:8000", changeOrigin: true },
      // fallback for any other API paths
      "/api": { target: "http://localhost:8000", changeOrigin: true }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJDOlxcXFxVc2Vyc1xcXFxLYWxldlxcXFxzdXBwdHJhY2tlclwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiQzpcXFxcVXNlcnNcXFxcS2FsZXZcXFxcc3VwcHRyYWNrZXJcXFxcdml0ZS5jb25maWcudHNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL0M6L1VzZXJzL0thbGV2L3N1cHB0cmFja2VyL3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcbmltcG9ydCByZWFjdCBmcm9tICdAdml0ZWpzL3BsdWdpbi1yZWFjdCdcblxuLy8gRHVyaW5nIGRldmVsb3BtZW50IHByb3h5IEFQSSBjYWxscyB0byB0aGUgRmFzdEFQSSBiYWNrZW5kIG9uIDo4MDAwXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuXHRwbHVnaW5zOiBbcmVhY3QoKV0sXG5cdHNlcnZlcjoge1xuXHRcdHBvcnQ6IDUxNzMsXG5cdFx0cHJveHk6IHtcblx0XHRcdC8vIHByb3h5IHRoZSBBUEkgZW5kcG9pbnRzIHVzZWQgYnkgdGhlIGZyb250ZW5kXG5cdFx0XHQnL3NlYXJjaCc6IHsgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJywgY2hhbmdlT3JpZ2luOiB0cnVlIH0sXG5cdFx0XHQnL2ludGVyYWN0aW9uJzogeyB0YXJnZXQ6ICdodHRwOi8vbG9jYWxob3N0OjgwMDAnLCBjaGFuZ2VPcmlnaW46IHRydWUgfSxcblx0XHRcdCcvc3RhY2snOiB7IHRhcmdldDogJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsIGNoYW5nZU9yaWdpbjogdHJ1ZSB9LFxuXHRcdFx0Ly8gZmFsbGJhY2sgZm9yIGFueSBvdGhlciBBUEkgcGF0aHNcblx0XHRcdCcvYXBpJzogeyB0YXJnZXQ6ICdodHRwOi8vbG9jYWxob3N0OjgwMDAnLCBjaGFuZ2VPcmlnaW46IHRydWUgfVxuXHRcdH1cblx0fVxufSlcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBd1EsU0FBUyxvQkFBb0I7QUFDclMsT0FBTyxXQUFXO0FBR2xCLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzNCLFNBQVMsQ0FBQyxNQUFNLENBQUM7QUFBQSxFQUNqQixRQUFRO0FBQUEsSUFDUCxNQUFNO0FBQUEsSUFDTixPQUFPO0FBQUE7QUFBQSxNQUVOLFdBQVcsRUFBRSxRQUFRLHlCQUF5QixjQUFjLEtBQUs7QUFBQSxNQUNqRSxnQkFBZ0IsRUFBRSxRQUFRLHlCQUF5QixjQUFjLEtBQUs7QUFBQSxNQUN0RSxVQUFVLEVBQUUsUUFBUSx5QkFBeUIsY0FBYyxLQUFLO0FBQUE7QUFBQSxNQUVoRSxRQUFRLEVBQUUsUUFBUSx5QkFBeUIsY0FBYyxLQUFLO0FBQUEsSUFDL0Q7QUFBQSxFQUNEO0FBQ0QsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
