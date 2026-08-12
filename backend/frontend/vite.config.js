import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期把 /admin 与 /v1 代理到后端（默认 8000 端口），避免跨域。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/admin': 'http://127.0.0.1:8000',
      '/v1': 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist' },
})
