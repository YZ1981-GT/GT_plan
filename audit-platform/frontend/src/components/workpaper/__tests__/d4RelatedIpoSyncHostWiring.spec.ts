/**
 * D4-21/22/23/24 宿主接线守卫（批次A：半接入→真接桥）—— 参照 d4InspectionSyncHostWiring.spec.ts。
 *
 * spec: d4-21-24-oo-bidirectional-and-cross-sheet-formula
 *
 * 背景（inventory 记的「半接入」）：D4-21/22/23/24 后端契约 d421~d424-managed 早已就绪，
 * 但前端此前仍是 legacy GtOnlyOfficeSheet + 本地 editorMode ref（OO→HTML 统一路径未消费，
 * 即主控 §6.4 的假双向）。批次A 迁到子组件自管 useWorkpaperSyncBridge + WorkpaperSyncEditorHost。
 *
 * 判据落到源码结构：宿主必须消费平台 useWorkpaperSyncBridge + WorkpaperSyncEditorHost +
 * capabilityForEntry(父级 entry) 现算 + readStoreProjection；禁裸 GtOnlyOfficeSheet；
 * flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）；sheetKey 锁本表。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const D4_DIR = resolve(_dir, '..', 'd4')
const PARENT_ENTRY = 'xlsx/gt-d4-operating-revenue'

const TABS: Record<string, { file: string; sheetKey: string }> = {
  'D4-21': { file: 'related/D4TabRelatedPrice.vue', sheetKey: 'd421-managed' },
  'D4-22': { file: 'ipo/D4TabIpoIndicator.vue', sheetKey: 'd422-managed' },
  'D4-23': { file: 'ipo/D4TabInvoiceCompare.vue', sheetKey: 'd423-managed' },
  'D4-24': { file: 'ipo/D4TabThirdParty.vue', sheetKey: 'd424-managed' },
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

describe.each(Object.entries(TABS))('%s 必须消费平台 sync bridge（批次A 半接入迁移）', (code, { file, sheetKey }) => {
  const path = resolve(D4_DIR, file)
  const src = existsSync(path) ? stripComments(read(path)) : ''
  const args = extractBridgeCallArgs(src)

  it('tab 文件存在', () => {
    expect(existsSync(path)).toBe(true)
  })

  it('调用了平台 useWorkpaperSyncBridge（禁自建同步 composable）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('ContentMutationService')
  })

  it('flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）', () => {
    expect(args).toContain('flushHtml')
    expect(args).toMatch(/flushPendingSave\s*\(/)
    expect(args).toMatch(/readStoreProjection\s*\(/)
    const flushAt = args.indexOf('flushPendingSave')
    const readAt = args.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })

  it('capability 现算：capabilityForEntry(父级 entry)，禁内联 bidirectional 字面量', () => {
    expect(src).toMatch(/capabilityForEntry\s*\(/)
    expect(src).toContain(PARENT_ENTRY)
    expect(args).not.toMatch(/capability:\s*['"]bidirectional['"]/)
  })

  it('sheetKey 锁本表 managed 身份', () => {
    expect(src).toContain(sheetKey)
  })

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
  })

  it('不得再挂裸 GtOnlyOfficeSheet（旧反模式/半接入痕迹）', () => {
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
})

// ── 宿主登记守卫：D4-21/22/23/24 必须进 isD4DedicatedSyncSheet ──────────────────
describe('宿主 GtD4OperatingRevenue 必须把 D4-21~24 登记为 dedicated sync sheet', () => {
  const hostPath = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')
  const hostSrc = existsSync(hostPath) ? stripComments(read(hostPath)) : ''

  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker)
    if (start < 0) return ''
    const lb = src.indexOf('[', start)
    const rb = src.indexOf(']', lb)
    if (lb < 0 || rb < 0) return ''
    return src.slice(lb, rb + 1)
  }

  it('宿主文件存在且定义了 isD4DedicatedSyncSheet', () => {
    expect(existsSync(hostPath)).toBe(true)
    expect(hostSrc).toContain('isD4DedicatedSyncSheet')
  })

  it.each(['D4-21', 'D4-22', 'D4-23', 'D4-24'])('dedicated 列表含 %s', (code) => {
    const list = extractDedicatedList(hostSrc)
    expect(list).toContain(`'${code}'`)
  })

  it('自检：抽取器真在承重（列表里没有的 code 抓不到）', () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).not.toContain("'D4-99'")
  })
})

describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = 'const b = useWorkpaperSyncBridge({ entryId: x, flushHtml: async () => {} })'
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
  })
  it('stripComments 剥掉注释里的反例', () => {
    const stub = 'const x = 1 // <GtOnlyOfficeSheet />\n/* ContentMutationService */'
    const out = stripComments(stub)
    expect(out).not.toContain('GtOnlyOfficeSheet')
    expect(out).not.toContain('ContentMutationService')
  })
})
