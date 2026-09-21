/**
 * D4-12 合同检查表宿主接线守卫（spec d4-12-transposed-writeback / Task 14）
 * —— 转置表（一列=一份合同，一行=一个字段），走泛化通用引擎 + 注册表分派。
 * 参照 d4CustomerStructureSyncHostWiring（D4-9）/ d4ProductMarginSyncHostWiring（D4-8）。
 *
 * 2026-09-21 治本改造后更新：D4-12 的接桥不再直接调 `useWorkpaperSyncBridge`，而是通过
 * 共享 composable `useD4SyncMode`（entryId/capability/健康门禁/switchMode 已内聚到该
 * composable 内部，由 `useD4SyncMode.spec.ts` 单独守卫）。D4-12 destructure 时用了组件专属
 * 前缀命名（`d412Bridge`/`d412Descriptor`/`d412SyncStateTag`），sheetKey 为内联字面量；
 * flushHtml 内调用的是 `useD4ContractInspection` composable 导出的 `flushPendingSave`
 * （非本地函数声明，`await` 调用），断言据此调整但顺序判据不变。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const TAB = resolve(_dir, '..', 'd4', 'inspection', 'D4TabContract.vue')
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

describe('D4-12 合同检查表必须消费平台 sync bridge（转置表）', () => {
  const src = existsSync(TAB) ? stripComments(read(TAB)) : ''
  const args = extractBridgeCallArgs(src)

  it('tab 文件存在', () => { expect(existsSync(TAB)).toBe(true) })

  it('调用了共享 composable useD4SyncMode（禁自建同步 composable / 禁直连底层桥 / 不自造 ContentMutationService）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(src).not.toContain('useWorkpaperSyncBridge(')
    expect(src).not.toContain('ContentMutationService')
  })

  it('flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）', () => {
    expect(args).toContain('flushHtml')
    const f = args.indexOf('flushPendingSave')
    const r = args.indexOf('readStoreProjection')
    expect(f).toBeGreaterThanOrEqual(0)
    expect(r).toBeGreaterThan(f)
  })

  it('sheetKey 锁 d4-12-managed 身份', () => {
    expect(args).toMatch(/sheetKey:\s*['"]d4-12-managed['"]/)
  })

  it('挂 WorkpaperSyncEditorHost 且不挂 legacy GtOnlyOfficeSheet', () => {
    expect(src).toContain('<WorkpaperSyncEditorHost')
    expect(src).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(src).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })

  it('OO 描述子来自 composable（d412Descriptor），编辑器由 bridge 驱动', () => {
    expect(src).toMatch(/descriptor:\s*d412Descriptor/)
    expect(src).toMatch(/:descriptor="d412Descriptor"/)
    expect(src).toMatch(/:bridge="d412Bridge"/)
  })

  it('消费 composable 导出的同步态 tag（不自行重复 danger 文案）', () => {
    expect(src).toContain('d412SyncStateTag')
    expect(src).toMatch(/d412SyncStateTag\.type/)
    expect(src).toMatch(/d412SyncStateTag\.text/)
  })

  it('保留卡片视图 CRUD / OCR / AI / 导入导出能力（不回归）', () => {
    expect(src).toContain('useD4ContractInspection')
    expect(src).toContain('handleContractUpload')  // OCR
    expect(src).toContain('generateConclusion')     // AI
    expect(src).toContain('useD4ImportExport')       // 导入导出
    expect(src).toContain('addContract')             // CRUD
  })
})

describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useD4SyncMode({ sheetKey: 'd4-12-managed', flushHtml: async () => {} })"
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
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
