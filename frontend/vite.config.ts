import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 5173/5174 are taken by other projects on this machine. strictPort makes Vite fail loudly
    // instead of silently drifting to the next free port and serving someone else's app.
    port: 5180,
    strictPort: true,
    // Any /api call is forwarded to FastAPI, so the browser never deals with CORS in dev.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
