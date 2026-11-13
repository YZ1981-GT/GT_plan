/**
 * 离屏披露 Node 执行器构建（SSR 模式打包，Node 直接运行；spec note-disclosure-pull-regression-and-headless-backend
 * 任务 11 / 13，design §5.2 / §5.4）。
 *
 *   node node_modules/vite/bin/vite.js build --config tools/headless-disclosure/vite.config.ts
 *
 * 与前端同一份源码、同一套自动导入（vue / vue-router / pinia）；只把 `@/utils/http` 换成 `nodeHttp.ts`
 * （浏览器端的 axios 拦截器带提示框、进度条与登录态 store，Node 里用不上）。输出 dist/（不入库）。
 *
 * dist/source-manifest.json：打进包里的每个源文件（本前端目录内、不含 node_modules）的 sha256。`run.mjs` 运行前逐个核对，
 * 源码改了没重新构建 ⇒ 拒绝运行（退出码 3），不拿旧版 builder 算出的数写附注。
 */
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { isAbsolute, relative } from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url))
const FRONTEND_ROOT = here('../..')

/** 构建时记下打进包里的源文件与内容摘要（见文件头）。 */
function sourceManifest(): Plugin {
  return {
    name: 'headless-disclosure-source-manifest',
    apply: 'build',
    generateBundle() {
      const files = new Set<string>()
      for (const id of this.getModuleIds()) {
        if (id.startsWith('\0')) continue
        const file = id.split('?')[0]
        if (!isAbsolute(file) || /[\\/]node_modules[\\/]/.test(file)) continue
        const rel = relative(FRONTEND_ROOT, file)
        if (!rel || rel.startsWith('..') || isAbsolute(rel)) continue
        files.add(rel.replace(/\\/g, '/'))
      }
      const entries = [...files].sort().map((path) => ({
        path,
        sha256: createHash('sha256').update(readFileSync(`${FRONTEND_ROOT}/${path}`)).digest('hex'),
      }))
      if (entries.length === 0) this.error('离屏执行器构建清单为空：没有识别到打进包里的源文件')
      this.emitFile({
        type: 'asset',
        fileName: 'source-manifest.json',
        source: JSON.stringify({ schema: 'headless-disclosure-source-manifest/v1', files: entries }, null, 1),
      })
    },
  }
}

export default defineConfig({
  root: FRONTEND_ROOT,
  logLevel: 'warn',
  plugins: [
    vue(),
    AutoImport({ imports: ['vue', 'vue-router', 'pinia'], dts: false }),
    sourceManifest(),
  ],
  resolve: {
    alias: [
      { find: /^@\/utils\/http$/, replacement: here('./nodeHttp.ts') },
      { find: '@', replacement: here('../../src') },
    ],
  },
  build: {
    ssr: here('./entry.ts'),
    outDir: here('./dist'),
    emptyOutDir: true,
    target: 'node20',
    minify: false,
    rollupOptions: {
      output: {
        format: 'es',
        entryFileNames: 'entry.mjs',
        chunkFileNames: 'chunks/[name]-[hash].mjs',
      },
    },
  },
})
