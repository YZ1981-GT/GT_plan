/**
 * D4-8 重要产品毛利分析表宿主接线守卫（spec workpaper-sync-static-cell-sheet-writeback）
 * —— 静态受管区（definedName 锚定 static cell）块矩阵，census 裁定 = 静态；参照 d4OtherMarginSyncHostWiring（D4-33）。
 * 受管 = 第 1 个产品（slot0→产品A 块）180 static cell；第 2+ 产品无模板块 → HTML-only。
 *
 * 2026-09-21 治本改造后更新：D4-8 的接桥不再直接调 `useWorkpaperSyncBridge`，而是通过
 * 共享 composable `useD4SyncMode`（entryId/capability/健康门禁/switchMode/fail-visible tag
 * 已内聚到该 composable 内部，由 `useD4SyncMode.spec.ts` 单独守卫）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'analysis', 'D4TabProductMargin.vue')
const HOST = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')

function read(p: string): string { return readFileSync(p, 'utf-8') }
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
    else if (ch === ')') { depth--; if (depth === 0) return src.slice(start + marker.length, i) }
  }
  return ''
}

describe('D4-8 产品毛利分析必须消费平台 sync bridge（静态受管区块矩阵）', () => {
  const src = existsSync(TAB) ? stripComments(read(TAB)) : ''
  const args = extractBridgeCallArgs(src)
  it('tab 文件存在', () => { expect(existsSync(TAB)).toBe(true) })
  it('调用了共享 composable useD4SyncMode（禁自建同步 composable / 禁直连底层桥）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('useWorkpaperSyncBridge(')
    expect(src).not.toContain('ContentMutationService')
  })
  it('flushHtml 内 flushPendingSave 先于 readStoreProjection', () => {
    expect(args).toContain('flushHtml')
    const f = args.indexOf('flushPendingSave'); const r = args.indexOf('readStoreProjection')
    expect(f).toBeGreaterThanOrEqual(0); expect(r).toBeGreaterThan(f)
  })
  it('sheetKey 锁 d48-managed 身份', () => {
    expect(args).toMatch(/sheetKey:\s*['"]d48-managed['"]/)
  })
  it('挂 WorkpaperSyncEditorHost 且不挂裸 GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
  it('OO 描述子来自 composable（syncOoDescriptor），编辑器由 bridge 驱动', () => {
    expect(src).toContain('syncOoDescriptor')
    expect(src).toMatch(/:bridge="syncBridge"/)
  })
  it('消费 composable 导出的 syncStateTag（不自行重复 danger 文案）', () => {
    expect(src).toMatch(/syncStateTag/)
    expect(src).toMatch(/syncStateTag\.type/)
    expect(src).toMatch(/syncStateTag\.text/)
  })
})

describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useD4SyncMode({ sheetKey: 'd48-managed', flushHtml: async () => {} })"
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

describe('宿主必须登记 D4-8 为 dedicated', () => {
  const hostSrc = existsSync(HOST) ? stripComments(read(HOST)) : ''
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker); if (start < 0) return ''
    const lb = src.indexOf('[', start); const rb = src.indexOf(']', lb)
    return lb < 0 || rb < 0 ? '' : src.slice(lb, rb + 1)
  }
  it('dedicated 列表含 D4-8', () => { expect(extractDedicatedList(hostSrc)).toContain("'D4-8'") })
})
