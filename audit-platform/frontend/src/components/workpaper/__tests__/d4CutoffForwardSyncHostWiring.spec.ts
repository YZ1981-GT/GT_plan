/**
 * D4-17 截止测试（账到单据）宿主接线守卫（批次B 第二张）—— 参照 d4IndicatorSyncHostWiring.spec.ts。
 *
 * 2026-09-21 治本改造后更新：D4-17 的接桥不再直接调 `useWorkpaperSyncBridge`，而是通过
 * 共享 composable `useD4SyncMode`（entryId/capability/健康门禁/switchMode/fail-visible tag
 * 已内聚到该 composable 内部，由 `useD4SyncMode.spec.ts` 单独守卫）。判据落到源码结构：
 * D4TabCutoffForward.vue 消费 useD4SyncMode + WorkpaperSyncEditorHost；禁裸 GtOnlyOfficeSheet；
 * flushHtml 内 flushPendingSave 先于 readStoreProjection；sheetKey 走具名常量 D4_17_SHEET_KEY；
 * 宿主 GtD4OperatingRevenue.isD4DedicatedSyncSheet 含 'D4-17'。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'inspection', 'D4TabCutoffForward.vue')
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

describe('D4-17 截止测试必须消费平台 sync bridge（批次B 从零）', () => {
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
    const flushAt = args.indexOf('flushPendingSave')
    const readAt = args.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })
  it('sheetKey 走具名常量（不得内联字面量，防漂移）', () => {
    expect(src).toContain(`= 'd417-managed'`)
    expect(args).toMatch(/sheetKey:\s*D4_17_SHEET_KEY\b/)
    expect(args).not.toMatch(/sheetKey:\s*['"]d417-managed['"]/)
  })
  it('挂 WorkpaperSyncEditorHost 且不再挂裸 GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
  it('消费 composable 导出的 syncStateTag（不自行重复 danger 文案）', () => {
    expect(src).toMatch(/syncStateTag/)
  })
})

describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useD4SyncMode({ sheetKey: D4_17_SHEET_KEY, flushHtml: async () => {} })"
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
  })
})

describe('宿主 GtD4OperatingRevenue 必须登记 D4-17 为 dedicated', () => {
  const hostSrc = existsSync(HOST) ? stripComments(read(HOST)) : ''
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker)
    if (start < 0) return ''
    const lb = src.indexOf('[', start)
    const rb = src.indexOf(']', lb)
    return lb < 0 || rb < 0 ? '' : src.slice(lb, rb + 1)
  }
  it('dedicated 列表含 D4-17', () => { expect(extractDedicatedList(hostSrc)).toContain("'D4-17'") })
})
