/**
 * D4-9 重要客户结构分析接桥 + 宿主登记守卫 —— 参照 d4AdjudicationSyncHostWiring.spec.ts。
 *
 * spec: d4-9-customer-structure-bidirectional-writeback · Task 12
 * Requirements: 7.1（双向链路走统一 sync bridge 而非 legacy 单向）, 7.4/7.5（fail-closed / 移除 legacy）, 8.4
 *
 * 架构（路 B）：D4-9 作为 gt-d4-operating-revenue 的 sibling sheet（sheetKey=d49-managed，
 * 后端 phase5_d4_customer_structure 并入 phase5_d4_revenue_detail），与 D4-1 同架构。
 *
 * 2026-09-21 治本改造后更新：D4-9 的接桥不再直接调 `useWorkpaperSyncBridge`，而是通过
 * 共享 composable `useD4SyncMode`（见 `d4/composables/useD4SyncMode.ts`）——entryId/
 * capability/健康门禁/switchMode/fail-visible tag 的**实现细节**已内聚到该 composable
 * 内部（并由 `useD4SyncMode.spec.ts` 单独守卫），组件源码里不再重复这些字面量。
 *
 * 判据落到源码结构：
 *  1. D4TabCustomerStructure.vue 消费 `useD4SyncMode`（禁自建/直连底层桥）。
 *  2. sheetKey 走具名常量 `d49-managed`（不得内联字面量，防漂移）。
 *  3. flushHtml 内 flush 先于 readStoreProjection（防投影旧值 / 顺序守卫）。
 *  4. 宿主 GtD4OperatingRevenue.vue 的 isD4DedicatedSyncSheet 含 'D4-9'。
 *  5. fail-visible：消费 composable 导出的 syncStateTag（danger 文案实现在
 *     useD4SyncMode 内聚，不在本组件重复）。
 *  6. 挂载 WorkpaperSyncEditorHost，不得再挂裸 GtOnlyOfficeSheet（legacy 单向已移除）。
 *  7. rowId 迁移：CustomerRow 带 rowId、有 backfillRowIds、createRowId（Req 3.1/3.2）。
 *
 * 反向自检（变异守卫）：若 'D4-9' 从 dedicated 列表移除、或 sheetKey 变成内联字面量、
 * 或 GtOnlyOfficeSheet 回潮、或 rowId 迁移缺失，则相应断言转红。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const CS_PATH = resolve(_dir, '..', 'd4', 'analysis', 'D4TabCustomerStructure.vue')
const HOST_PATH = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')

const D4_9_SHEET_KEY = 'd49-managed'

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}
/** 抽取 useD4SyncMode({...}) 的调用体（括号配平）。 */
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

const csSrc = existsSync(CS_PATH) ? stripComments(read(CS_PATH)) : ''
const hostSrc = existsSync(HOST_PATH) ? stripComments(read(HOST_PATH)) : ''
const bridgeArgs = extractBridgeCallArgs(csSrc)

// ── D4TabCustomerStructure 接桥守卫 ─────────────────────────────────────────
describe('D4-9 重要客户结构必须消费平台 sync bridge（Req 7.1）', () => {
  it('D4TabCustomerStructure.vue 存在', () => {
    expect(existsSync(CS_PATH)).toBe(true)
  })

  it('调用了共享 composable useD4SyncMode（禁自建同步 composable / 禁直连底层桥）', () => {
    expect(bridgeArgs.length).toBeGreaterThan(0)
    expect(csSrc).not.toContain('useWorkpaperSyncBridge(')
    expect(csSrc).not.toContain('ContentMutationService')
  })

  it('sheetKey 走具名常量（不得内联字面量，防漂移）', () => {
    expect(csSrc).toContain(`= '${D4_9_SHEET_KEY}'`)
    expect(bridgeArgs).toMatch(/sheetKey:\s*D4_9_SHEET_KEY\b/)
    expect(bridgeArgs).not.toMatch(new RegExp(`sheetKey:\\s*['"]${D4_9_SHEET_KEY}['"]`))
  })

  it('flushHtml 内 flush 先于 readStoreProjection（防投影旧值）', () => {
    expect(bridgeArgs).toContain('flushHtml')
    expect(bridgeArgs).toMatch(/flushSave\s*\(/)
    expect(bridgeArgs).toMatch(/readStoreProjection\s*\(/)
    const flushAt = bridgeArgs.indexOf('flushSave')
    const readAt = bridgeArgs.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })

  it('flushHtml 回投 sheetKey 锁本表 managed 身份', () => {
    expect(bridgeArgs).toMatch(/sheetKey:\s*D4_9_SHEET_KEY/)
  })

  it('模板挂载 WorkpaperSyncEditorHost，不得再挂裸 GtOnlyOfficeSheet（legacy 单向已移除）', () => {
    expect(csSrc).toContain('<WorkpaperSyncEditorHost')
    expect(csSrc).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(csSrc).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
})

// ── fail-visible 守卫（Req 7.4）─────────────────────────────────────────────
describe('D4-9 同步失败必须 fail-visible（消费共享 composable 的中文 danger tag）', () => {
  it('消费 composable 导出的 syncStateTag（不自行重复 danger 文案 —— 实现细节交 useD4SyncMode.spec.ts 守）', () => {
    expect(bridgeArgs.length).toBeGreaterThan(0)
    expect(csSrc).toMatch(/syncStateTag/)
    expect(csSrc).toMatch(/syncStateTag\.type/)
    expect(csSrc).toMatch(/syncStateTag\.text/)
  })

  it('不得绕过共享 composable 自行 markSynced 静默吞错', () => {
    expect(csSrc).not.toContain('markSynced')
  })
})

// ── rowId 迁移守卫（Req 3.1/3.2）────────────────────────────────────────────
describe('D4-9 行身份 rowId + 历史迁移（Req 3.1/3.2）', () => {
  it('CustomerRow 带 rowId 字段', () => {
    expect(csSrc).toMatch(/rowId\s*:\s*string/)
  })

  it('有稳定 id 生成器 createRowId', () => {
    expect(csSrc).toMatch(/function\s+createRowId/)
    expect(csSrc).toMatch(/randomUUID/)
  })

  it('有历史无 rowId 行的一次性补齐 backfillRowIds', () => {
    expect(csSrc).toMatch(/function\s+backfillRowIds/)
  })
})

// ── 宿主登记守卫：D4-9 必须进 isD4DedicatedSyncSheet ────────────────────────
describe('宿主 GtD4OperatingRevenue 必须把 D4-9 登记为 dedicated sync sheet', () => {
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
    expect(existsSync(HOST_PATH)).toBe(true)
    expect(hostSrc).toContain('isD4DedicatedSyncSheet')
  })

  it("dedicated 列表含 'D4-9'（防宿主叠加 legacy 双切换器）", () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).toContain("'D4-9'")
  })

  it('自检：抽取器真在承重（列表里没有的 code 抓不到）', () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).not.toContain("'D4-99'")
  })
})

// ── 反向自检：抽取器/剥注释真在承重（防恒真）────────────────────────────────
describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useD4SyncMode({ sheetKey: D4_9_SHEET_KEY, flushHtml: async () => {} })"
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
