import { fileURLToPath, URL } from 'node:url'
import { execFileSync } from 'node:child_process'
import { defineConfig, loadEnv, type Plugin, type ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

/**
 * 表格单元格编辑器适配（spec excel-style-table-editing ADR-1）：模板里的这几个组件解析到
 * `@/components/grid/adapters` 的同名导出（类型声明为原组件类型）。表格外透传原组件；
 * 表体单元格里平时只渲染文本，双击 / F2 / 直接输入才挂原组件。名单与 adapters.ts 的
 * GRID_ADAPTED_COMPONENTS 一致（守卫 gridAdapterResolver.spec.ts 核对）。
 */
export const GRID_ADAPTED_COMPONENTS = ['ElInput', 'ElInputNumber', 'ElSelect', 'ElDatePicker', 'ElCheckbox', 'ElSwitch', 'ElRadioGroup']
export function GridCellAdapterResolver() {
  return {
    type: 'component' as const,
    resolve: (name: string) => (GRID_ADAPTED_COMPONENTS.includes(name) ? { name, from: '@/components/grid/adapters' } : undefined),
  }
}

export function heavyFeatureChunk(id: string): string | undefined {
  const moduleId = id.replace(/\\/g, '/')
  // CJS 互操作辅助（getDefaultExportFromCjs 等）被 vendor-core 里的 CJS 依赖使用，
  // 留在入口会让 vendor-core 反向 import index。
  if (moduleId.includes('commonjsHelpers')) return 'vendor-core'
  if (!moduleId.includes('/node_modules/')) return undefined

  // 先固定全站共享运行时。Vue 与 Element Plus 必须放在同一个 vendor-core；
  // 拆成 core/ui 会形成 Element Plus → Vue 与自动组件注册 → Element Plus 的循环 chunk。
  // 若只给重功能命名，Rollup 又会把公共运行时吸进 heavy-*，首屏为取得 Vue
  // 反而静态加载整个 Univer/Office 重块。
  if (/\/node_modules\/(?:vue|vue-router|pinia)\//.test(moduleId)
    || moduleId.includes('/node_modules/@vue/')
    || moduleId.includes('/node_modules/element-plus/')
    || moduleId.includes('/node_modules/@element-plus/')) return 'vendor-core'

  // element-plus 的传递依赖必须同属 vendor-core。onlyExplicitManualChunks 下它们不会被自动吸入，
  // 会落进入口 index，而 vendor-core 又反向 import index、index 静态 import vendor-core，
  // 形成循环 chunk，生产白屏 `Cannot access 'Rt' before initialization`
  // （spec frontend-prod-build-white-screen-closure；由 scripts/check-chunk-cycles.mjs 守卫）。
  if (/\/node_modules\/(?:lodash-es|lodash-unified|dayjs|async-validator|memoize-one|normalize-wheel-es|escape-html|vue-demi)\//.test(moduleId)
    || moduleId.includes('/node_modules/@vueuse/')
    || /\/node_modules\/@floating-ui\/(?:core|dom|utils|vue)\//.test(moduleId) // 不含 react-dom，否则 vendor-core 反向依赖 React
    || moduleId.includes('/node_modules/@popperjs/')
    || moduleId.includes('/node_modules/@ctrl/tinycolor/')
    || moduleId.includes('/node_modules/@sxzz/')) return 'vendor-core'

  // Univer 的第三方依赖（rxjs / numfmt / React 全家 / radix 等；应用源码不直接引用）。
  // onlyExplicitManualChunks 下它们不会跟着 @univerjs 走，会落进 WorkpaperEditor 块，
  // 而 heavy-univer 反向 import 该块（108 个名字），形成 WorkpaperEditor ↔ heavy-univer 环，
  // 生产构建打开底稿编辑器报 `Cannot access 'Kp' before initialization`
  // （spec frontend-prod-build-white-screen-closure 任务 6；由 check-chunk-cycles --strict 守卫）。
  if (/\/node_modules\/(?:@wendellhu|@radix-ui|@flatten-js|@babel\/runtime|rxjs|numfmt|react|react-dom|scheduler|react-remove-scroll|react-remove-scroll-bar|react-style-singleton|react-transition-group|dom-helpers|use-callback-ref|use-sidecar|aria-hidden|get-nonce|ot-json1|ot-text-unicode|franc-min|async-lock|cjk-regex|collapse-white-space|fast-diff|kdbush|quickselect|rbush|n-gram|opentype\.js|regexp-util|trigram-utils|unicode-regex|unicount|clsx|class-variance-authority|tailwind-merge|localforage|sonner)\//.test(moduleId)
    || /\/node_modules\/@floating-ui\/react-dom\//.test(moduleId)) return 'heavy-univer'
  if (moduleId.includes('/@univerjs/')) return 'heavy-univer'
  if (moduleId.includes('/@vue-office/') || moduleId.includes('/pdfjs-dist/') || moduleId.includes('/mammoth/')) {
    return 'heavy-office'
  }
  if (/\/node_modules\/(?:xlsx|xlsx-js-style|exceljs)\//.test(moduleId)) return 'heavy-excel'
  return undefined
}

export interface CandidateFrontendIdentity {
  expected: string
  actual: string
}

const TREE_OID = /^[0-9a-f]{40}$/

/** 候选模式只在 defineConfig 回调内读 git；普通开发模式不调用 git。 */
export function resolveCandidateFrontendIdentity(
  env: Record<string, string | undefined> = process.env,
  argv: string[] = process.argv.slice(2),
  cwd = process.cwd(),
): CandidateFrontendIdentity | null {
  const expected = env.GT_EXPECTED_CANDIDATE_TREE_OID
  if (!expected) return null
  if (!TREE_OID.test(expected)) throw new Error('GT_EXPECTED_CANDIDATE_TREE_OID 必须是 40 位小写十六进制')
  const devPort = Number(env.VITE_DEV_PORT)
  if (!Number.isInteger(devPort) || devPort <= 0 || devPort === 3030) {
    throw new Error('候选前端要求 VITE_DEV_PORT 为非 3030 的有效端口')
  }
  const apiBase = env.VITE_API_BASE_URL
  if (!apiBase) throw new Error('候选前端要求显式设置 VITE_API_BASE_URL')
  let apiPort: string
  try {
    const parsed = new URL(apiBase)
    apiPort = parsed.port || (parsed.protocol === 'https:' ? '443' : '80')
  } catch {
    throw new Error('候选前端的 VITE_API_BASE_URL 不是有效 URL')
  }
  if (apiPort === '9980') throw new Error('候选前端不得代理到共享后端 9980')
  const forbidden = argv.map((arg) => arg.split('=', 1)[0]).filter((arg) => arg === '--port' || arg === '--host')
  if (forbidden.length) throw new Error(`候选前端端口/地址只经环境变量传入，不允许参数：${[...new Set(forbidden)].join('、')}`)
  const actual = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { cwd, encoding: 'utf8' }).trim()
  if (!TREE_OID.test(actual)) throw new Error(`无法解析候选前端 HEAD^{tree}：${actual}`)
  const dirty = execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd, encoding: 'utf8' }).trim()
  if (dirty) throw new Error(`候选前端 worktree 有受跟踪改动：\n${dirty}`)
  if (actual !== expected) throw new Error(`候选前端树身份不符：期望 ${expected}，实际 ${actual}`)
  return { expected, actual }
}

export function candidatePortGuard(expectedPort: number): Plugin {
  return {
    name: 'gt-candidate-port-guard',
    configureServer(server) {
      server.httpServer?.once('listening', () => {
        const address = server.httpServer?.address()
        const actual = typeof address === 'object' && address ? address.port : null
        if (actual !== expectedPort || actual === 3030) {
          console.error(`候选前端监听端口不符：期望 ${expectedPort}，实际 ${actual}`)
          process.exit(1)
        }
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const candidate = resolveCandidateFrontendIdentity({ ...env, ...process.env })
  // 用 127.0.0.1 而非 localhost：后端 uvicorn 仅监听 IPv4（0.0.0.0），
  // Windows 上 localhost 先解析 ::1 → 连接失败回退，每个代理请求固定 +2s
  const apiTarget = process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL || 'http://127.0.0.1:9980'
  const devPort = parseInt(process.env.VITE_DEV_PORT || env.VITE_DEV_PORT || '3030', 10)
  const outDir = process.env.GT_FRONTEND_OUT_DIR || 'dist'
  const proxy: Record<string, ProxyOptions> = {
    '/api': {
      target: apiTarget,
      changeOrigin: true,
      // FastAPI trailing-slash 307 must stay behind the frontend origin.
      configure: (server) => {
        server.on('proxyRes', (proxyRes) => {
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
  }

  return {
    // 依赖预构建缓存放前端根目录 .vite/（.gitignore 已忽略），不放 node_modules/.vite：
    // 临时 worktree 常以联接（junction）共用 node_modules，删 worktree 时顺着联接把 .vite/deps 一起删掉，
    // 开发服务器内存里的依赖还能用、懒加载分块（如 @univerjs/engine-render 的 en-gb）就 504 Outdated Optimize Dep。
    // spec post-push-residual-defect-closure R5
    cacheDir: '.vite',
    plugins: [
      vue(),
      ...(candidate ? [candidatePortGuard(devPort)] : []),
      // 不在 AutoImport 中挂 ElementPlusResolver：
      // 与显式 `import { ElMessage } from 'element-plus'` 冲突时会生成不存在的 ElMessage2。
      // 候选 worktree 关闭 dts，避免开发服务器改写受跟踪的声明文件而破坏树身份。
      AutoImport({
        imports: ['vue', 'vue-router', 'pinia'],
        dts: candidate ? false : 'src/auto-imports.d.ts',
      }),
      Components({
        // 先于 ElementPlusResolver：第一个返回结果的解析器生效
        resolvers: [GridCellAdapterResolver(), ElementPlusResolver({ importStyle: false })],
        dts: candidate ? false : 'src/components.d.ts',
      }),
    ],
    define: candidate ? {
      __GT_CANDIDATE_TREE_EXPECTED__: JSON.stringify(candidate.expected),
      __GT_CANDIDATE_TREE_ACTUAL__: JSON.stringify(candidate.actual),
    } : {},
    build: {
      // manifest 是包体预算、built smoke 和 verified snapshot 的共同事实源。
      outDir,
      manifest: true,
      sourcemap: false,
      rollupOptions: {
        output: {
          manualChunks: heavyFeatureChunk,
          // 只把命中的包本身放进指定 chunk；否则 Rollup 会递归吸入 lodash 等共享依赖，
          // 入口为取得一个共享函数又反向静态加载整个 heavy-univer。
          onlyExplicitManualChunks: true,
        },
      },
    },
    server: {
      // Windows IPv6 loopback 在部分开发机上会出现“显示 LISTENING 但连接被拒绝”。
      // 显式监听 IPv4 全接口，start-dev / Playwright / transform probe 统一走 127.0.0.1。
      host: '0.0.0.0',
      port: devPort,
      // 🔴 必须 true：strictPort=false 时 vite 在 3030 被占用时会**静默漂移**到 3031
      //    （只在 stdout 打一行 "Port 3030 is in use, trying another one..."，退出码 0）。
      //    而 start-dev.bat 的 [5/5] 只探测 http://localhost:3030，用户也只会打开 3030 —— 
      //    于是「前端其实在 3031 跑得很好」被呈现为「[WARN] Frontend not responding /
      //    前端未能启动」，排查方向被彻底带偏（后端日志正常，前端窗口也没有报错）。
      //    3030 还是后端 CORS_ORIGINS 白名单里的固定值，漂移端口属于约定被破坏。
      //    改成 true 后端口冲突会明确失败并打印占用信息，失败可见 > 静默降级。
      strictPort: true,
      proxy,
    },
    // Stable runtime serves the immutable production snapshot while retaining
    // the same-origin API/WOPI contract used by the development server.
    preview: {
      host: '0.0.0.0',
      port: devPort,
      strictPort: true,
      proxy,
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        'opentype.js/dist/opentype.module.js': 'opentype.js/dist/opentype.mjs',
      },
    },
  }
})
