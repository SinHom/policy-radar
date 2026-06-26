import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端 dev 端口；后端 FastAPI 在 8000
// 通过 vite proxy 把 /api/* 转发到 8000
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
      '/version': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
