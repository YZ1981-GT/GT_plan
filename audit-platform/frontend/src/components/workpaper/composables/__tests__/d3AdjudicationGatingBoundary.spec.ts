/**
 * D3-1 审定表「第二套 gating」边界守卫（Task 14 引入，Task 16 迁移为「派生 + kind 分桥」形态）。
 *
 * spec: d3-sync-coverage-via-row-table-engine · Task 14/16 · Requirements 4.4 / 6.6 / 需求 9.5 / 9.6
 *
 * ═══ 这条判据钉的是什么 ═══
 *
 * D3-2（行表 rows kind / d32-managed）与 D3-1（AdjudicationSheetSpec 逐格 mask kind /
 * d31-managed）entry_id/store 形态完全不同。evidence task1 §3.2 实测登记：`renderMode`
 * computed 的 get/set 是**互斥二选一**（`if isD3DetailSheet then syncBridge else dualMode`），
 * 若把 `D3-1` 并进 `isD3DetailSheet`（rows 桥），会让两张 sheet 共用同一套 syncBridge/
 * switchRenderMode → 切 OO 走错桥 + 工具条叠加冲突（D4-35/D4-13 踩过）。
 *
 * 🔴 Task 16 迁移：宿主 gating 从**单张写死**（`currentSheet === 'D3-2'`/`=== 'D3-1'`）改为
 * 从单一来源清单 `d3ManagedSheets` **派生**（`isD3OoWiredRowsSheet`/`isD3ManagedAdjudicationSheet`）。
 * 故本守卫从「钉源码字面量」迁移为：
 *   ① 源码级：`isD3DetailSheet` 用 rows 桥判定、`isD3AdjudicationSyncSheet` 用 adjudication
 *      判定，且 `isD3DetailSheet` 的判断里**绝不**出现 adjudication 判定（不合并两套桥）；
 *   ② 行为级：单一来源清单里 D3-2（rows）与 D3-1（adjudication）确实分属不同 kind，两个派生
 *      判定对彼此的 sheet 互斥 —— 这比源码正则更能证明「不会切错桥」。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  isD3OoWiredRowsSheet,
  isD3ManagedRowsSheet,
  isD3ManagedAdjudicationSheet,
  d3ManagedSheetOf,
} from '../../sync/d3ManagedSheets'

const HOST_SRC = readFileSync(
  resolve(__dirname, '../../GtD3PrepaidAccounts.vue'),
  'utf-8',
)

describe('D3-1 第二套 gating 边界守卫（派生 + kind 分桥）', () => {
  it('isD3AdjudicationSyncSheet 用 adjudication 判定派生（独立第二套 gating）', () => {
    expect(HOST_SRC).toMatch(
      /const\s+isD3AdjudicationSyncSheet\s*=\s*computed\(\s*\(\)\s*=>\s*isD3ManagedAdjudicationSheet\(currentSheet\.value\)\s*\)/,
    )
  })

  it('isD3DetailSheet 用 rows 桥判定派生，判断里绝不出现 adjudication 判定', () => {
    const m = HOST_SRC.match(/const\s+isD3DetailSheet\s*=\s*computed\(([^\n]*)\)/)
    expect(m, '未找到 isD3DetailSheet 声明').not.toBeNull()
    const decl = m![1]
    // rows 桥判定（真正接了 OO 直写宿主的受管行表）。
    expect(decl).toContain('isD3OoWiredRowsSheet')
    // 🔴 绝不把审定表判定并进 rows 桥（否则两 sheet 共用 D3-2 的 syncBridge）。
    expect(decl).not.toContain('isD3ManagedAdjudicationSheet')
    expect(decl).not.toContain("'D3-1'")
  })

  it('第二套 gating 变量被真实消费（renderModeOptions 里用于门控在线编辑）', () => {
    expect(HOST_SRC).toMatch(/isD3AdjudicationSyncSheet\.value/)
  })

  it('行为级：D3-2 属 rows 桥、D3-1 属 adjudication 桥，两判定互斥（不会切错桥）', () => {
    // D3-2：受管行表且已接 OO 直写桥。
    expect(isD3OoWiredRowsSheet('D3-2')).toBe(true)
    expect(isD3ManagedAdjudicationSheet('D3-2')).toBe(false)
    // D3-1：受管审定表（adjudication kind），绝不落入 rows 桥。
    expect(isD3ManagedAdjudicationSheet('D3-1')).toBe(true)
    expect(isD3ManagedRowsSheet('D3-1')).toBe(false)
    expect(isD3OoWiredRowsSheet('D3-1')).toBe(false)
    // kind 逐字确认。
    expect(d3ManagedSheetOf('D3-2')?.kind).toBe('rows')
    expect(d3ManagedSheetOf('D3-1')?.kind).toBe('adjudication')
  })
})
