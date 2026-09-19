import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 用 127.0.0.1 而非 localhost：后端 uvicorn 仅监听 IPv4（0.0.0.0），
  // Windows 上 localhost 先解析 ::1 → 连接失败回退，每个代理请求固定 +2s
  const apiTarget = env.VITE_API_BASE_URL || 'http://127.0.0.1:9980'
  const devPort = parseInt(env.VITE_DEV_PORT || '3030', 10)

  return {
    plugins: [
      vue(),
      // 不在 AutoImport 中挂 ElementPlusResolver：
      // 与显式 `import { ElMessage } from 'element-plus'` 冲突时会生成不存在的 ElMessage2。
      // ElMessage / ElMessageBox 由业务代码显式导入；样式已在 main.ts 全量引入。
      AutoImport({
        imports: ['vue', 'vue-router', 'pinia'],
        dts: 'src/auto-imports.d.ts',
      }),
      Components({
        resolvers: [ElementPlusResolver({ importStyle: false })],
        dts: 'src/components.d.ts',
      }),
    ],
    server: {
      port: devPort,
      // 🔴 必须 true：strictPort=false 时 vite 在 3030 被占用时会**静默漂移**到 3031
      //    （只在 stdout 打一行 "Port 3030 is in use, trying another one..."，退出码 0）。
      //    而 start-dev.bat 的 [5/5] 只探测 http://localhost:3030，用户也只会打开 3030 —— 
      //    于是「前端其实在 3031 跑得很好」被呈现为「[WARN] Frontend not responding /
      //    前端未能启动」，排查方向被彻底带偏（后端日志正常，前端窗口也没有报错）。
      //    3030 还是后端 CORS_ORIGINS 白名单里的固定值，漂移端口属于约定被破坏。
      //    改成 true 后端口冲突会明确失败并打印占用信息，失败可见 > 静默降级。
      strictPort: true,
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
