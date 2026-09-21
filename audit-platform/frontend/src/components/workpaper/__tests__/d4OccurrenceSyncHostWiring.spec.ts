/**
 * D4-14 营业收入发生检查表（穿行测试）宿主接线守卫
 * —— 参照 d4MarginMonthlySyncHostWiring。D4-14 是单宽动态行 store（TransactionItem[]，行身份 id），
 *    在线编辑从 legacy GtOnlyOfficeSheet 升级为平台统一 sync bridge（sheetKey=d414-managed）。
 *
 * spec: d4-14-walkthrough-writeback · Task 11
 *
 * 2026-09-21 治本改造后更新：D4-14 的接桥不再直接调 `useWorkpaperSyncBridge`，而是通过
 * 共享 composable `useD4SyncMode`（entryId/capability/健康门禁/switchMode 已内聚到该
 * composable 内部，由 `useD4SyncMode.spec.ts` 单独守卫）。D4-14 sheetKey 为内联字面量
 * （未声明具名常量），且额外解构了 `ooHealthy`（模板 `v-if="!ooHealthy"` 直接消费，
 * fail-visible 判据据此断言，不要求 danger 文案字面量）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'inspection', 'D4TabOccurrence.vue')
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

describe('D4-14 穿行测试必须消费平台 sync bridge（单宽动态行 7 维嵌套）', () => {
  const raw = existsSync(TAB) ? read(TAB) : ''
  const src = stripComments(raw)
  const args = extractBridgeCallArgs(src)

  it('tab 文件存在', () => { expect(existsSync(TAB)).toBe(true) })

  it('调用了共享 composable useD4SyncMode（禁自建同步 composable / 禁直连底层桥）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('useWorkpaperSyncBridge(')
    expect(src).not.toContain('ContentMutationService')
  })

  it('flushHtml 内 flushSave 先于 readStoreProjection', () => {
    expect(args).toContain('flushHtml')
    const f = args.indexOf('flushSave')
    const r = args.indexOf('readStoreProjection')
    expect(f).toBeGreaterThanOrEqual(0)
    expect(r).toBeGreaterThan(f)
  })

  it('sheetKey 锁 d414-managed 身份', () => {
    expect(args).toMatch(/sheetKey:\s*['"]d414-managed['"]/)
  })

  it('挂 WorkpaperSyncEditorHost 且不再挂 legacy GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })

  it('OO 描述子来自 composable（syncOoDescriptor），编辑器由 bridge 驱动', () => {
    expect(src).toContain('syncOoDescriptor')
    expect(src).toMatch(/:bridge="syncBridge"/)
  })

  it('fail-visible：消费 composable 导出的 ooHealthy/syncStateTag（不自行重复 danger 文案）', () => {
    expect(src).toContain('syncStateTag')
    expect(src).toMatch(/OO\s*不可用|ooHealthy/)
  })

  it('行身份用前端稳定 id（TransactionItem.id，禁数组下标当身份）', () => {
    // composable 的 TransactionItem 以 id 为稳定行身份；后端 provider row_identity=/*/id
    expect(src).not.toMatch(/store_item_id/)  // 前端不应硬编码后端 stable key
  })
})

describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useD4SyncMode({ sheetKey: 'd414-managed', flushHtml: async () => {} })"
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

describe('宿主必须登记 D4-14 为 dedicated', () => {
  const hostSrc = existsSync(HOST) ? stripComments(read(HOST)) : ''
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker)
    if (start < 0) return ''
    const lb = src.indexOf('[', start)
    const rb = src.indexOf(']', lb)
    return lb < 0 || rb < 0 ? '' : src.slice(lb, rb + 1)
  }
  it('dedicated 列表含 D4-14（否则宿主叠加 legacy 双切换器 + 走整册 GtOnlyOfficeSheet）', () => {
    expect(extractDedicatedList(hostSrc)).toContain("'D4-14'")
  })
})
