import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
  // The built interface is served by FastAPI.
  build: { outDir: '../backend/src/binder/static', emptyOutDir: true, chunkSizeWarningLimit: 800 },
})
