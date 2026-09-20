/**
 * D4-12 合同检查表宿主接线守卫（spec d4-12-transposed-writeback / Task 14）
 * —— 转置表（一列=一份合同，一行=一个字段），走泛化通用引擎 + 注册表分派。
 * 参照 d4CustomerStructureSyncHostWiring（D4-9）/ d4ProductMarginSyncHostWiring（D4-8）。
 * 断言：D4TabContract 接平台 useWorkpaperSyncBridge + WorkpaperSyncEditorHost + 宿主登记 dedicated。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'inspection', 'D4TabContract.vue')
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

describe('D4-12 合同检查表必须消费平台 sync bridge（转置表）', () => {
  const src = existsSync(TAB) ? stripComments(read(TAB)) : ''
  const args = extractBridgeCallArgs(src)

  it('tab 文件存在', () => { expect(existsSync(TAB)).toBe(true) })

  it('调用了平台 useWorkpaperSyncBridge（不自造 ContentMutationService）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('ContentMutationService')
  })

  it('flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）', () => {
    expect(args).toContain('flushHtml')
    const f = args.indexOf('flushPendingSave')
    const r = args.indexOf('readStoreProjection')
    expect(f).toBeGreaterThanOrEqual(0)
    expect(r).toBeGreaterThan(f)
  })

  it('capability 现算 + 父 entry，禁内联 bidirectional 字面量', () => {
    expect(src).toMatch(/capabilityForEntry\s*\(/)
    expect(src).toContain(PARENT_ENTRY)
    expect(args).not.toMatch(/capability:\s*['"]bidirectional['"]/)
  })

  it('sheetKey 锁 d4-12-managed', () => {
    expect(src).toContain('d4-12-managed')
  })

  it('挂 WorkpaperSyncEditorHost 且不挂 legacy GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })

  it('OO 描述子来自 bridge（descriptor），编辑器由 bridge 驱动', () => {
    expect(src).toMatch(/d412Bridge\.descriptor/)
    expect(src).toMatch(/:bridge="d412Bridge"/)
  })

  it('fail-visible 同步态三态中文 tag（非静默）', () => {
    expect(src).toContain('d412SyncStateTag')
    expect(src).toMatch(/同步失败/)
    expect(src).toMatch(/同步中/)
  })

  it('保留卡片视图 CRUD / OCR / AI / 导入导出能力（不回归）', () => {
    expect(src).toContain('useD4ContractInspection')
    expect(src).toContain('handleContractUpload')  // OCR
    expect(src).toContain('generateConclusion')     // AI
    expect(src).toContain('useD4ImportExport')       // 导入导出
    expect(src).toContain('addContract')             // CRUD
  })
})

describe('宿主必须登记 D4-12 为 dedicated（子组件自管切换器，宿主不叠加 legacy）', () => {
  const hostSrc = existsSync(HOST) ? stripComments(read(HOST)) : ''
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker)
    if (start < 0) return ''
    const lb = src.indexOf('[', start)
    const rb = src.indexOf(']', lb)
    return lb < 0 || rb < 0 ? '' : src.slice(lb, rb + 1)
  }
  it('dedicated 列表含 D4-12', () => {
    expect(extractDedicatedList(hostSrc)).toContain("'D4-12'")
  })
})
