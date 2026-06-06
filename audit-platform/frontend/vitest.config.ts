import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    exclude: ['e2e/**', 'e2e-uat/**', 'node_modules/**', 'eslint-rules/**'],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@fixtures': resolve(__dirname, '../../backend/tests/fixtures'),
    },
  },
})
