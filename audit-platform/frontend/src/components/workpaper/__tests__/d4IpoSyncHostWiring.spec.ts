/**
 * D4 IPO 四张检查表（D4-25/26/27/28）宿主接线守卫 —— 参照 D2-2 / D4-5 canary。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 1 · Task 2
 *
 * 2026-09-21 治本改造后更新：四张 IPO 检查表的接桥不再直接调 `useWorkpaperSyncBridge`，
 * 而是通过共享 composable `useD4SyncMode`（entryId/capability/健康门禁/switchMode/
 * fail-visible tag 已内聚到该 composable 内部，由 `useD4SyncMode.spec.ts` 单独守卫）。
 * sheetKey 四张表均走具名常量（`D4_2X_SHEET_KEY`），源码注释明确标注这是跨语言契约守卫要求
 * （后端 test_d4_ipo_checklist_cross_lang_contract.py 靠正则抓常量声明反查 sheet_key 漂移）。
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

// 四张 IPO 检查表共用父级 D4 workbook 的统一同步入口，各自一个 managed sheet key + 具名常量。
const MANAGED_KEY_BY_CODE: Record<string, string> = {
  'D4-25': 'd4-25-managed',
  'D4-26': 'd4-26-managed',
  'D4-27': 'd4-27-managed',
  'D4-28': 'd4-28-managed',
}
const NAMED_CONST_BY_CODE: Record<string, string> = {
  'D4-25': 'D4_25_SHEET_KEY',
  'D4-26': 'D4_26_SHEET_KEY',
  'D4-27': 'D4_27_SHEET_KEY',
  'D4-28': 'D4_28_SHEET_KEY',
}

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function extractBridgeCallArgs(src: string): string {
  const marker = 'useD4SyncMode('
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
  const sheetKey = MANAGED_KEY_BY_CODE[code]
  const namedConst = NAMED_CONST_BY_CODE[code]

  it('tab 文件存在', () => {
    expect(existsSync(path)).toBe(true)
  })

  it('调用了共享 composable useD4SyncMode（禁自建同步 composable / 禁直连底层桥）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('useWorkpaperSyncBridge(')
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

  it('sheetKey 走具名常量（不得内联字面量，跨语言契约守卫要求）', () => {
    expect(src).toContain(`= '${sheetKey}'`)
    expect(args).toMatch(new RegExp(`sheetKey:\\s*${namedConst}\\b`))
    expect(args).not.toMatch(new RegExp(`sheetKey:\\s*['"]${sheetKey}['"]`))
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
    const stub = 'const b = useD4SyncMode({ sheetKey: D4_25_SHEET_KEY, flushHtml: async () => {} })'
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
