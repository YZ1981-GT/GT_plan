import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    /** 全量并行时易出现动态 import/挂载超时；提高默认超时并限制并发 */
    testTimeout: 15000,
    hookTimeout: 15000,
    fileParallelism: true,
    maxWorkers: 4,
    include: ['**/*.{test,spec}.?(c|m)[jt]s?(x)', '**/*.pbt.spec.?(c|m)[jt]s?(x)'],
    exclude: ['e2e/**', 'e2e-uat/**', 'tests/**', 'node_modules/**', 'eslint-rules/**', '**/*.e2e.spec.ts'],
    /** 让 Vite 转译 element-plus（而非交给 Node 原生 ESM）。inline 后测试环境与生产用同一套模块解析逻辑，校验真实生效。 */
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@fixtures': resolve(__dirname, '../../backend/tests/fixtures'),
    },
  },
})
