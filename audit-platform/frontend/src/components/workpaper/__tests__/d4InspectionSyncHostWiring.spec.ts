/**
 * D4-15/16 检查表宿主接线守卫（B2）—— 参照 d4IpoSyncHostWiring.spec.ts。
 *
 * spec: d4-inspection-writeback-formula-io · B2
 *
 * 判据落到源码结构：宿主必须消费平台 useWorkpaperSyncBridge + WorkpaperSyncEditorHost +
 * capabilityForEntry(父级 entry) 现算 + readStoreProjection；禁裸 GtOnlyOfficeSheet；
 * flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）；sheetKey 锁本表。
 *
 * D4-13(纯文本)/D4-14(七维+计算footer,超范式)不在本组 —— 见 evidence/b1-provider-geometry.md。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const INSPECT_DIR = resolve(_dir, '..', 'd4', 'inspection')
const PARENT_ENTRY = 'xlsx/gt-d4-operating-revenue'

const TABS: Record<string, { file: string; sheetKey: string }> = {
  'D4-15': { file: 'D4TabCompleteness.vue', sheetKey: 'd4-15-managed' },
  'D4-16': { file: 'D4TabExport.vue', sheetKey: 'd4-16-managed' },
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

describe.each(Object.entries(TABS))('%s 检查表必须消费平台 sync bridge', (code, { file, sheetKey }) => {
  const path = resolve(INSPECT_DIR, file)
  const src = existsSync(path) ? stripComments(read(path)) : ''
  const args = extractBridgeCallArgs(src)

  it('tab 文件存在', () => {
    expect(existsSync(path)).toBe(true)
  })

  it('调用了平台 useWorkpaperSyncBridge（禁自建同步 composable）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('ContentMutationService') // spec 草案臆想名，禁引用
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

  it('不得再挂裸 GtOnlyOfficeSheet（旧反模式）', () => {
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
})

// ── 宿主登记守卫：D4-15/16 必须进 isD4DedicatedSyncSheet ──────────────────────
// 否则宿主对它们仍渲染 legacy 通知（「两侧数据未互通」）+ 走 legacy dualMode，
// 与子组件自管的 sync 切换器叠加（IPO D4-25~28 曾踩的坑）。
describe('宿主 GtD4OperatingRevenue 必须把 D4-15/16 登记为 dedicated sync sheet', () => {
  const hostPath = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')
  const hostSrc = existsSync(hostPath) ? stripComments(read(hostPath)) : ''

  function extractDedicatedList(src: string): string {
    // 锚定到定义处（computed），而非模板里的 v-if 引用
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

  it('dedicated 列表含 D4-15 与 D4-16', () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).toContain("'D4-15'")
    expect(list).toContain("'D4-16'")
  })

  // D4-35（D4TabOtherCheck 已接 d435SyncBridge）同理必须登记，否则宿主叠加 legacy 双切换器
  // （2026-09-19 e2e 验收实测：漏登记时点「在线编辑」命中 legacy 切换器，统一路径 store-projection 不触发）。
  it('dedicated 列表含 D4-35（防宿主漏登记叠加 legacy 双切换器）', () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).toContain("'D4-35'")
  })

  it('自检：抽取器真在承重（列表里没有的 code 抓不到）', () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).not.toContain("'D4-99'")
  })
})

// ── 反向自检：抽取器/剥注释真在承重 ──────────────────────────────────────────
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
