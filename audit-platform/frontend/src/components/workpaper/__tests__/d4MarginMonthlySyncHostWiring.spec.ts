/**
 * D4-7 毛利率分析表宿主接线守卫（同 sheet 1 dynamic 产品区 + 1 static 月度区）
 * —— 参照 d4OtherContractSyncHostWiring。额外钉住 products 补了 rowId（双向回写行身份前置）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'analysis', 'D4TabMarginMonthly.vue')
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

describe('D4-7 毛利率分析必须消费平台 sync bridge（动态产品区 + 静态月度区）', () => {
  const raw = existsSync(TAB) ? read(TAB) : ''
  const src = stripComments(raw)
  const args = extractBridgeCallArgs(src)
  it('tab 文件存在', () => { expect(existsSync(TAB)).toBe(true) })
  it('调用了平台 useWorkpaperSyncBridge', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('ContentMutationService')
  })
  it('flushHtml 内 flushSave 先于 readStoreProjection', () => {
    expect(args).toContain('flushHtml')
    const f = args.indexOf('flushSave'); const r = args.indexOf('readStoreProjection')
    expect(f).toBeGreaterThanOrEqual(0); expect(r).toBeGreaterThan(f)
  })
  it('capability 现算 + 父 entry，禁内联 bidirectional 字面量', () => {
    expect(src).toMatch(/capabilityForEntry\s*\(/)
    expect(src).toContain(PARENT_ENTRY)
    expect(args).not.toMatch(/capability:\s*['"]bidirectional['"]/)
  })
  it('sheetKey 锁 d47-managed', () => { expect(src).toContain('d47-managed') })
  it('挂 WorkpaperSyncEditorHost 且不再挂裸 GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
  it('OO 描述子来自 bridge（syncOoDescriptor），编辑器由 bridge 驱动', () => {
    expect(src).toContain('syncOoDescriptor')
    expect(src).toMatch(/:bridge="syncBridge"/)
  })
  it('products 有稳定 rowId（双向回写行身份前置，禁数组下标当身份）', () => {
    // 接口声明 rowId + addProduct/backfill 现场铸造
    expect(src).toMatch(/rowId:\s*string/)
    expect(src).toContain('newRowId')
    // addProduct 推入的新行带 rowId
    expect(src).toMatch(/products\.value\.push\(\{\s*rowId:/)
  })
})

describe('宿主必须登记 D4-7 为 dedicated', () => {
  const hostSrc = existsSync(HOST) ? stripComments(read(HOST)) : ''
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker); if (start < 0) return ''
    const lb = src.indexOf('[', start); const rb = src.indexOf(']', lb)
    return lb < 0 || rb < 0 ? '' : src.slice(lb, rb + 1)
  }
  it('dedicated 列表含 D4-7', () => { expect(extractDedicatedList(hostSrc)).toContain("'D4-7'") })
})
