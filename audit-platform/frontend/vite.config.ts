import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_BASE_URL || 'http://localhost:9980'
  const devPort = parseInt(env.VITE_DEV_PORT || '3030', 10)

  return {
    plugins: [
      vue(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
        dts: 'src/auto-imports.d.ts',
      }),
      Components({
        resolvers: [ElementPlusResolver()],
        dts: 'src/components.d.ts',
      }),
    ],
    server: {
      port: devPort,
      strictPort: false,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // 修复 FastAPI trailing-slash 307 重定向绕过代理导致 CORS 的问题：
          // 拦截后端返回的 Location header 中的绝对 URL，重写为相对路径
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              const location = proxyRes.headers['location']
              if (location && location.startsWith(apiTarget)) {
                proxyRes.headers['location'] = location.replace(apiTarget, '')
              }
            })
          },
        },
        '/wopi': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        'opentype.js/dist/opentype.module.js': 'opentype.js/dist/opentype.mjs',
      },
    },
  }
})
