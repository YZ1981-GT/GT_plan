import { readFileSync } from 'node:fs'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterAll, beforeEach, expect, vi } from 'vitest'
import {
  INVENTORY_PATH,
  beginFile,
  decideNetworkVerdict,
  installNetworkGuard,
  trackXhrRequests,
  type NetworkLeakInventory,
} from './networkGuard'

/**
 * 全局测试夹具。
 *
 * vitest 在**每个测试文件**执行前都会重新执行本文件（隔离与共享两种模式都如此），
 * 所以这里的顶层代码就是「文件边界」，beforeEach 才是「用例边界」。
 *
 * ── 文件边界：补做 vitest 隔离模式的重置（只在共享模块图模式下有实际作用）──
 * 默认 isolate:true 时每个测试文件跑在新 worker 里，模块缓存、全局 stub、计时器天然清零。
 * 用 --no-isolate（或 poolOptions.*.isolate=false）把多个文件放进同一个 worker 后，这些都会
 * 跨文件存活。其中最致命的是模块缓存：被测组件（如 FormulaManagerDialog.vue）第一次被某个
 * 文件 import 时，它对 vi.mock 依赖的绑定就固定成那个文件的 mock；之后的文件再 vi.mock
 * 也到不了组件，组件拿着上一个文件早已还原的 mock 运行，读出 undefined
 * （"Cannot read properties of undefined (reading 'value')"）或请求断言 0 次调用。
 * vitest 的 mock 注册表本来就按测试文件分开（MockerRegistry 以 filepath 为键），
 * 所以这里清模块缓存即可，与隔离模式 runBaseTests 的 resetModules 同口径。
 * 隔离模式下进入本文件时缓存本就是空的，下面四步都是空操作。
 */
vi.resetModules()
vi.useRealTimers()
vi.unstubAllGlobals()
vi.unstubAllEnvs()

/**
 * ── 文件边界：单测禁止真实网络连接（spec: frontend-test-network-isolation-and-load-dedup）──
 * 下面只短路了 fetch，而 axios 在 jsdom 里走 XHR：此前有 25 个测试文件在打 localhost:3000
 * （本机是 Metabase，CI 上无服务），同一用例本机和 CI 走不同分支。拦截装在
 * `net.Socket.prototype.connect`，被拦的连接以连接失败结束（与 CI 同语义），细节见 networkGuard.ts。
 * 隔离模式下（本 worker 的第一个文件）跑完后判定：不在清单里却连了网 → 常规运行告警、
 * GT_TEST_NETWORK_AUDIT=1 时失败；审计模式下清单里的文件不再连网 → 失败（提示删条目）。
 * 共享模式第二个起只拦不判。
 */
const networkGuard = installNetworkGuard()
beginFile(networkGuard)
trackXhrRequests(networkGuard)
// 不用 new URL(字面量, import.meta.url)：Vite 的资源插件会把它改写成非 file 协议的地址。
const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const networkInventory = JSON.parse(readFileSync(resolve(FRONTEND_ROOT, INVENTORY_PATH), 'utf-8')) as {
  files: NetworkLeakInventory
  intermittent: Record<string, string>
}
afterAll(() => {
  const testPath = expect.getState().testPath
  if (!testPath) return
  const audit = process.env.GT_TEST_NETWORK_AUDIT === '1'
  const verdict = decideNetworkVerdict({
    relFile: relative(FRONTEND_ROOT, testPath).split(sep).join('/'),
    attempts: networkGuard.attempts.length,
    requests: networkGuard.requests,
    inventory: networkInventory.files,
    intermittent: new Set(Object.keys(networkInventory.intermittent)),
    isolated: networkGuard.fileOrdinal === 1,
    audit,
  })
  if (verdict.kind === 'ok') return
  // 泄漏可能是间歇性的（判据不确定），常规运行不能当硬门禁，只告警；审计模式才失败。
  if (audit) throw new Error(verdict.message)
  console.warn(`[测试基座·网络] ${verdict.message}`)
})

// 重置之后再取模块实例，保证与本测试文件随后 import 到的是同一份
// （静态 import 会先于上面的重置求值，拿到的是上一个文件留下的旧实例）。
const { createPinia, setActivePinia } = await import('pinia')
const { useDisplayPrefsStore } = await import('@/stores/displayPrefs')

/**
 * 用例边界：
 * - 激活 Pinia（对话框/审定表依赖 useDisplayPrefsStore）
 * - 金额单位默认「元」、showZero=true，避免默认「万元」/零值隐藏导致断言漂移
 */
beforeEach(() => {
  try {
    localStorage.removeItem('gt_display_prefs')
  } catch { /* ignore */ }
  setActivePinia(createPinia())
  try {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setShowZero(true)
    prefs.setDecimals(2)
  } catch {
    // store 未加载时忽略（纯逻辑单测）
  }
})

/** 短路 fetch，减少全量并行时的真实网络/ECONNRESET 噪音 */
vi.stubGlobal(
  'fetch',
  vi.fn(async () =>
    new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  ),
)
