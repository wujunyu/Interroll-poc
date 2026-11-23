import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // 绑定所有网卡：容器/局域网内其他机器用 http://<宿主IP>:5174 访问
    host: '0.0.0.0',
    port: 5174,
    // 端口被占时直接失败，不要静默换到 5175
    strictPort: true,
    proxy: {
      // 开发时后端在 8090（本机 8080/8088 已被占）
      '/api': 'http://127.0.0.1:8090',
      '/healthz': 'http://127.0.0.1:8090',
      '/ws': { target: 'ws://127.0.0.1:8090', ws: true },
    },
  },
  preview: {
    host: '0.0.0.0',
  },
})
