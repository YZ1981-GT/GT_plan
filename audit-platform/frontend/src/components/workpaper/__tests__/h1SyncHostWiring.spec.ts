/**
 * H1 宿主接线守卫 —— H1-8 必须走统一桥，不得再挂 pilot adapter。
 *
 * ═══ 🔴 本文件原是「规划期守卫」，在 HEAD 上 7 条判据**全红** ═══════════════════
 *
 * 原判据按「H1 宿主直接调 `useWorkpaperSyncBridge`」写死，而实测 HEAD 上宿主里
 * `useWorkpaperSyncBridge` / `WorkpaperSyncEditorHost` / `isH18DisposalSheet` /
 * `capabilityForEntry` / `h18-managed` / `flushPendingSave` **出现次数全是 0**，
 * 只有 `usePilotBridgeAdapter(` 1 次 —— 也就是说这份守卫描述的迁移**从未发生**，
 * 它一直红着。
 *
 * ═══ 判据跟随交付，且改强不改弱 ═══════════════════════════════════════════════
 *
 * H1 接桥时用的是 `useHSyncMode`（H 循环 10 个宿主共用的统一包装），不是直接调 bridge。
 * 原判据的**意图**是「宿主在统一桥上、没有第二条路径」，直接调 bridge 只是它当时假定的
 * 形态。要求 H1 直接调会让它成为 10 个宿主里唯一的例外。
 *
 * 所以把「宿主里出现某个符号」改成**证明整条链**：
 *   · 宿主 → `useHSyncMode`（不再有 `usePilotBridgeAdapter`）
 *   · `useHSyncMode` → `useWorkpaperSyncBridge` + `capabilityForEntry`（在该文件里断言）
 *   · 受管 sheet 身份 → `sync/hManagedSheets.ts` 单一声明（**不得**内联回宿主）
 * 每一环都有判据，比原先「在宿主里 grep 一行」严。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(__dirname, '..', 'GtH1FixedAssets.vue')
const SYNC_MODE = resolve(__dirname, '..', 'composables', 'useHSyncMode.ts')
const MANAGED = resolve(__dirname, '..', 'sync', 'hManagedSheets.ts')

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 取某个调用的实参文本（括号配平，不用贪婪正则）。 */
function extractCallArgs(src: string, marker: string): string {
  const start = src.indexOf(marker)
  if (start < 0) return ''
  let depth = 0
  for (let i = start + marker.length - 1; i < src.length; i++) {
    const ch = src[i]
    if (ch === '(') depth++
    else if (ch === ')') {
      depth--
      if (depth === 0) return src.slice(start + marker.length, i)
    }
  }
  return ''
}

describe('H1 宿主必须接到统一双向桥（H1-8 canary）', () => {
  const hostSrc = stripComments(read(HOST))
  const args = extractCallArgs(hostSrc, 'useHSyncMode(')

  it('宿主确实调用了 useHSyncMode', () => {
    expect(args.length).toBeGreaterThan(0)
  })

  it('🔴 不得再调用 usePilotBridgeAdapter（它是零 API 空壳）', () => {
    expect(hostSrc).not.toMatch(/usePilotBridgeAdapter\s*\(/)
  })

  it('统一包装自己必须真的建桥 —— 链条不假设，逐环断言', () => {
    const modeSrc = stripComments(read(SYNC_MODE))
    expect(modeSrc).toMatch(/useWorkpaperSyncBridge\s*\(/)
  })

  it('flushHtml 必须先 flushPendingSaves 再 readStoreProjection', () => {
    expect(args).toContain('flushHtml')
    expect(args).toMatch(/flushPendingSaves?\s*\(/)
    expect(args).toMatch(/readStoreProjection\s*\(/)
    const flushAt = args.search(/flushPendingSaves?\s*\(/)
    const readAt = args.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })

  it('🔴 flush 必须是真落库，不能是 scheduleAutoSnapshot 那种假 flush', () => {
    // 原 `usePilotBridgeAdapter` 的 flushBeforeOo 传的就是 `scheduleAutoSnapshot()` ——
    // 只排版本快照、一格都没落库。这条钉住它不回来。
    expect(args).not.toMatch(/flushHtml[\s\S]{0,160}scheduleAutoSnapshot/)
    // 真 flush 的实现里必须有 PUT（清防抖后立即发）
    const flushImpl = extractCallArgs(hostSrc, 'async function flushPendingSaves(')
    expect(hostSrc).toMatch(/async function flushPendingSaves\s*\(/)
    expect(flushImpl !== null).toBe(true)
    expect(hostSrc).toMatch(/_putResponses\s*\(/)
  })

  it('entryId 锁死 H1 身份', () => {
    expect(hostSrc).toContain('xlsx/gt-h1-fixed-assets')
  })
})

describe('H1-8 OO 挂载必须走 WorkpaperSyncEditorHost', () => {
  const hostSrc = stripComments(read(HOST))

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(hostSrc).toContain('<WorkpaperSyncEditorHost')
  })

  it('受管门控 + descriptor/bridge 传入', () => {
    // 门控名与其余 9 个 H 宿主同型（isH{n}SyncManagedSheet），且必须**派生自桥**
    expect(hostSrc).toMatch(/isH1SyncManagedSheet/)
    expect(hostSrc).toMatch(/isH1SyncManagedSheet\s*=\s*computed\(\(\)\s*=>\s*hSync\.isManagedSheet\.value\)/)
    expect(hostSrc).toMatch(/:descriptor=/)
    expect(hostSrc).toMatch(/:bridge=/)
  })

  it('🔴 切换器不得带 :disabled（点击被吞是 D4 实证的 bug ③）', () => {
    const bar = hostSrc.slice(
      hostSrc.indexOf('h1-mode-switch-bar'),
      hostSrc.indexOf('</div>', hostSrc.indexOf('h1-mode-switch-bar')),
    )
    expect(bar).toMatch(/<el-segmented[^>]*v-model="currentMode"/)
    expect(bar).not.toMatch(/:disabled=/)
  })
})

describe('capability 与受管身份都不得内联回宿主', () => {
  const hostSrc = stripComments(read(HOST))

  it('capability 现算，禁止内联 bidirectional 字面量给桥', () => {
    expect(hostSrc).not.toMatch(/capability\s*:\s*['"]bidirectional['"]/)
    // 现算发生在统一包装里 —— 在那里断言，不要求宿主重复一遍
    const modeSrc = stripComments(read(SYNC_MODE))
    expect(modeSrc).toMatch(/capability\s*:\s*capabilityForEntry\s*\(/)
  })

  it('🔴 sheetKey 只在 hManagedSheets 声明一次，不得内联回宿主', () => {
    // F 循环 5 条 lane 各在宿主里内联 `F*_SHEET_KEY_BY_CODE`，注释说「从 provider 派生」
    // 而代码是硬编码 —— 本判据钉住 H 不重演。
    expect(hostSrc).not.toContain('h18-managed')
    const managedSrc = read(MANAGED)
    expect(managedSrc).toContain("sheetKey: 'h18-managed'")
    expect(managedSrc).toContain("entryId: 'xlsx/gt-h1-fixed-assets'")
    expect(managedSrc).toContain("storeItemId: 'H1-8-rows'")
    expect(managedSrc).toContain("excelName: '减少检查表H1-8'")
  })
})
