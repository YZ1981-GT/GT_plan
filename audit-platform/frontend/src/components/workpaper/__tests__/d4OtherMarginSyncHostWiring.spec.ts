/**
 * D4-33 其他业务毛利率分析表宿主接线守卫（spec workpaper-sync-static-cell-sheet-writeback）
 * —— 静态受管区（definedName 锚定 static cell）dict store，参照 d4OtherContractSyncHostWiring。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'other', 'D4TabOtherMargin.vue')
const HOST = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')
const PARENT_ENTRY = 'xlsx/gt-d4-operating-revenue'

function read(p: string): string { return readFileSync(p, 'utf-8') }
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
    else if (ch === ')') { depth--; if (depth === 0) return src.slice(start + marker.length, i) }
  }
  return ''
}

describe('D4-33 毛利率分析必须消费平台 sync bridge（静态受管区 dict store）', () => {
  const src = existsSync(TAB) ? stripComments(read(TAB)) : ''
  const args = extractBridgeCallArgs(src)
  it('tab 文件存在', () => { expect(existsSync(TAB)).toBe(true) })
  it('调用了平台 useWorkpaperSyncBridge', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('ContentMutationService')
  })
  it('flushHtml 内 flushPendingSave 先于 readStoreProjection', () => {
    expect(args).toContain('flushHtml')
    const f = args.indexOf('flushPendingSave'); const r = args.indexOf('readStoreProjection')
    expect(f).toBeGreaterThanOrEqual(0); expect(r).toBeGreaterThan(f)
  })
  it('capability 现算 + 父 entry，禁内联 bidirectional 字面量', () => {
    expect(src).toMatch(/capabilityForEntry\s*\(/)
    expect(src).toContain(PARENT_ENTRY)
    expect(args).not.toMatch(/capability:\s*['"]bidirectional['"]/)
  })
  it('sheetKey 锁 d433-managed', () => { expect(src).toContain('d433-managed') })
  it('挂 WorkpaperSyncEditorHost 且不再挂裸 GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
  it('OO 描述子来自 bridge（syncOoDescriptor），编辑器由 bridge 驱动', () => {
    expect(src).toContain('syncOoDescriptor')
    expect(src).toMatch(/:bridge="syncBridge"/)
  })
  it('fail-visible 同步态 tag（syncStateTag，非静默）', () => {
    expect(src).toContain('syncStateTag')
    expect(src).toMatch(/同步失败/)
  })
})

describe('宿主必须登记 D4-33 为 dedicated', () => {
  const hostSrc = existsSync(HOST) ? stripComments(read(HOST)) : ''
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker); if (start < 0) return ''
    const lb = src.indexOf('[', start); const rb = src.indexOf(']', lb)
    return lb < 0 || rb < 0 ? '' : src.slice(lb, rb + 1)
  }
  it('dedicated 列表含 D4-33', () => { expect(extractDedicatedList(hostSrc)).toContain("'D4-33'") })
})
