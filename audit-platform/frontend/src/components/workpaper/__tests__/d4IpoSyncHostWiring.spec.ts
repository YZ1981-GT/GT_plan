/**
 * D4 IPO 四张检查表（D4-25/26/27/28）宿主接线守卫 —— 参照 D2-2 / D4-5 canary。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 1 · Task 2
 *
 * 判据落到「源码结构」（宿主必须消费平台既有 useWorkpaperSyncBridge +
 * WorkpaperSyncEditorHost + capabilityForEntry(...) 现算 + readStoreProjection），
 * 禁止自建同步 composable、禁止内联 capability 字面量、禁止再挂裸 GtOnlyOfficeSheet。
 *
 * 🔴 Wave 1 阶段本守卫必须先红：四个 IPO tab 目前仍是「rows JSON 塞 remark + 裸
 *    GtOnlyOfficeSheet」的旧反模式（见 D4TabDealer.vue）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

const IPO_DIR = resolve(__dirname, '..', 'd4', 'ipo')
const TABS: Record<string, string> = {
  'D4-25': resolve(IPO_DIR, 'D4TabDealer.vue'),
  'D4-26': resolve(IPO_DIR, 'D4TabOverseas.vue'),
  'D4-27': resolve(IPO_DIR, 'D4TabUndisclosedRp.vue'),
  'D4-28': resolve(IPO_DIR, 'D4TabCustomerChecklist.vue'),
}

// 四张 IPO 检查表共用父级 D4 workbook 的 bidirectional 入口，各自一个 managed sheet key。
const PARENT_ENTRY = 'xlsx/gt-d4-operating-revenue'
const MANAGED_KEY_BY_CODE: Record<string, string> = {
  'D4-25': 'd4-25-managed',
  'D4-26': 'd4-26-managed',
  'D4-27': 'd4-27-managed',
  'D4-28': 'd4-28-managed',
}

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function extractBridgeCallArgs(src: string): string {
  const marker = 'useWorkpaperSyncBridge('
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

describe.each(Object.entries(TABS))('%s IPO 检查表必须消费平台 sync bridge', (code, path) => {
  const src = existsSync(path) ? stripComments(read(path)) : ''
  const args = extractBridgeCallArgs(src)

  it('tab 文件存在', () => {
    expect(existsSync(path)).toBe(true)
  })

  it('调用了平台 useWorkpaperSyncBridge（禁止自建同步 composable）', () => {
    expect(args.length).toBeGreaterThan(0)
    // 禁止本 spec 早期草案里的自建桥
    expect(src).not.toContain('useIpoChecklistSyncBridge')
  })

  it('flushHtml 必须先 flushPendingSave 再 readStoreProjection（防投影旧值）', () => {
    expect(args).toContain('flushHtml')
    expect(args).toMatch(/flushPendingSave\s*\(/)
    expect(args).toMatch(/readStoreProjection\s*\(/)
    const flushAt = args.indexOf('flushPendingSave')
    const readAt = args.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })

  it('capability 现算：capabilityForEntry(父级入口)，禁止内联 bidirectional 字面量', () => {
    expect(src).toMatch(/capabilityForEntry\s*\(/)
    expect(src).toContain(PARENT_ENTRY)
    // 不得像 legacy d2_sync_status.bidirectional 那样硬编码给桥
    expect(args).not.toMatch(/capability:\s*['"]bidirectional['"]/)
  })

  it('entryId / sheetKey 锁死本表 managed 身份', () => {
    expect(src).toContain(MANAGED_KEY_BY_CODE[code])
  })

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
  })

  it('不得再挂裸 GtOnlyOfficeSheet（旧反模式）', () => {
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
  })

  it('不再把整份 rows 数组 JSON.stringify 塞进 remark（旧反模式）', () => {
    // 旧代码：props.allResponses.set('D4-25-rows', { ..., remark: JSON.stringify(rows.value) })
    expect(src).not.toMatch(/remark:\s*JSON\.stringify\(\s*rows/)
  })

  it('导入成功后调用 reloadHost（AC 4.2：表格视图立即显示导入的行）', () => {
    // 从 useIpoChecklistTab 解构 reloadHost，且 handleImportFile 里调用它。
    expect(src).toMatch(/reloadHost/)
    const m = src.match(/async function handleImportFile[\s\S]*?\n\}/)
    expect(m, '未找到 handleImportFile').toBeTruthy()
    expect(m![0]).toMatch(/reloadHost\s*\(\s*\)/)
  })
})

// ── 反向自检：extractBridgeCallArgs / stripComments 真在承重 ──────────────────
describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 能抓到真实调用体', () => {
    const stub = 'const b = useWorkpaperSyncBridge({ entryId: x, flushHtml: async () => {} })'
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
  })

  it('stripComments 剥掉注释里的反例', () => {
    const stub = "const x = 1 // <GtOnlyOfficeSheet />\n/* useIpoChecklistSyncBridge */"
    const out = stripComments(stub)
    expect(out).not.toContain('GtOnlyOfficeSheet')
    expect(out).not.toContain('useIpoChecklistSyncBridge')
  })
})
