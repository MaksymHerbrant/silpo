import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // ngrok/cloudflared для локального тесту Mini App (Telegram вимагає https)
    allowedHosts: true,
  },
  build: { outDir: 'dist', sourcemap: false },
})
