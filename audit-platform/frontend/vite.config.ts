import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3030,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://localhost:9980',
        changeOrigin: true,
      },
      '/wopi': {
        target: 'http://localhost:9980',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
