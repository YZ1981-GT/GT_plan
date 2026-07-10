/**
 * Property-Based Tests — D6-8 ECL 减值测算 账龄配置联动
 *
 * Spec: .kiro/specs/aging-config-enhancement/
 * Task: 13.2
 *
 * 使用 fast-check + vitest 验证 Property 14（ECL 分组与账龄配置同步）。
 * 被测纯函数：
 *   - createAgingRowsFromSegments(segments) — 按段初始化 ECL 分组行
 *   - syncAgingGroupRows(existingRows, newSegments) — 配置变更时同步
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  createAgingRowsFromSegments,
  syncAgingGroupRows,
  type EclAgingRow,
} from '../composables/useD6EclCalculation'
import type { AgingSegment } from '@/composables/useAgingConfig'

// ─── Generators ──────────────────────────────────────────────────────────────

/**
 * 构建一个 key↔label 一一对应的账龄段候选池，
 * key = `k{i}`，label = `账龄{i}`（保证 key 与 label 均唯一，
 * syncAgingGroupRows 的 key 匹配与 label 兜底匹配结果一致）。
 */
function makeSegmentPool(size: number): AgingSegment[] {
  return Array.from({ length: size }, (_, i) => ({
    key: `k${i}`,
    label: `账龄${i}`,
    dayFrom: i * 30,
    dayTo: i === size - 1 ? null : (i + 1) * 30 - 1,
  }))
}

/** 单纯的段列表生成器（2..10 段） */
const arbSegments = fc
  .integer({ min: 2, max: 10 })
  .map((n) => makeSegmentPool(n))

/**
 * 配置变更场景生成器：
 * - 从一个共享候选池中挑选 old / new 两个非空子集（可部分重叠 / 全增 / 全删）
 * - 为每个池成员生成随机数值（lossRate/bookBalance/auditedBalance）
 */
const arbChangeScenario = fc.integer({ min: 3, max: 8 }).chain((poolSize) => {
  const pool = makeSegmentPool(poolSize)
  const idxArb = fc.uniqueArray(fc.integer({ min: 0, max: poolSize - 1 }), {
    minLength: 2,
    maxLength: poolSize,
  })
  return fc
    .record({
      oldIdx: idxArb,
      newIdx: idxArb,
      data: fc.array(
        fc.record({
          lossRate: fc.double({ min: 0, max: 1, noNaN: true }),
          bookBalance: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
          auditedBalance: fc.double({ min: 0, max: 1e9, noNaN: true }),
        }),
        { minLength: poolSize, maxLength: poolSize },
      ),
    })
    .map(({ oldIdx, newIdx, data }) => {
      const oldSegs = oldIdx.map((i) => pool[i])
      const newSegs = newIdx.map((i) => pool[i])
      const existingRows: EclAgingRow[] = oldIdx.map((i) => ({
        rowId: `r-${pool[i].key}`,
        segmentKey: pool[i].key,
        agingBand: pool[i].label,
        auditedBalance: data[i].auditedBalance,
        lossRate: data[i].lossRate,
        expectedProvision: 0,
        bookBalance: data[i].bookBalance,
        difference: 0,
      }))
      return { oldSegs, newSegs, existingRows }
    })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 14: ECL group syncs with aging config
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: aging-config-enhancement, Property 14: ECL group syncs with aging config', () => {
  /**
   * **Validates: Requirements 9.1**
   *
   * 对任意含 N 段的有效账龄配置，创建 D6 ECL 账龄分组应产生恰好 N 个子行，
   * 且行标签（agingBand）与段标签（label）逐一对应；数值字段全部零初始化。
   */
  it('creating an ECL aging group produces exactly N rows with labels matching the segments', () => {
    fc.assert(
      fc.property(arbSegments, (segments) => {
        const rows = createAgingRowsFromSegments(segments)

        expect(rows).toHaveLength(segments.length)
        rows.forEach((row, i) => {
          expect(row.segmentKey).toBe(segments[i].key)
          expect(row.agingBand).toBe(segments[i].label)
          expect(row.auditedBalance).toBe(0)
          expect(row.lossRate).toBe(0)
          expect(row.bookBalance).toBe(0)
          expect(row.expectedProvision).toBe(0)
          expect(row.difference).toBe(0)
          expect(row.archived).toBeUndefined()
        })
      }),
      { numRuns: 200 },
    )
  })

  /**
   * **Validates: Requirements 9.2, 9.3**
   *
   * 配置从 M 段变为 N 段时：
   * (a) 新旧配置共有的段保留 lossRate/bookBalance（及 auditedBalance）
   * (b) 新增段以零值加入
   * (c) 被移除且含真实数据的段标记为归档（archived: true），全零段直接丢弃
   */
  it('config change preserves shared segments, zero-inits new segments, and archives removed segments with data', () => {
    fc.assert(
      fc.property(arbChangeScenario, ({ oldSegs, newSegs, existingRows }) => {
        const oldKeys = new Set(oldSegs.map((s) => s.key))
        const newKeys = new Set(newSegs.map((s) => s.key))
        const existingByKey = new Map(existingRows.map((r) => [r.segmentKey, r]))

        const result = syncAgingGroupRows(existingRows, newSegs)

        const activeRows = result.filter((r) => !r.archived)
        const archivedRows = result.filter((r) => r.archived)

        // 活跃行数量 == 新配置段数，且顺序 / 标签逐一对应新段
        expect(activeRows).toHaveLength(newSegs.length)
        activeRows.forEach((row, i) => {
          expect(row.segmentKey).toBe(newSegs[i].key)
          expect(row.agingBand).toBe(newSegs[i].label)
          expect(row.archived).toBeUndefined()

          if (oldKeys.has(newSegs[i].key)) {
            // (a) 共有段：保留原数值
            const prev = existingByKey.get(newSegs[i].key)!
            expect(row.lossRate).toBe(prev.lossRate)
            expect(row.bookBalance).toBe(prev.bookBalance)
            expect(row.auditedBalance).toBe(prev.auditedBalance)
          } else {
            // (b) 新增段：零初始化
            expect(row.lossRate).toBe(0)
            expect(row.bookBalance).toBe(0)
            expect(row.auditedBalance).toBe(0)
          }
        })

        // (c) 被移除段：含数据→归档保留；全零→丢弃
        for (const seg of oldSegs) {
          if (newKeys.has(seg.key)) continue
          const prev = existingByKey.get(seg.key)!
          const hasData =
            prev.lossRate !== 0 || prev.bookBalance !== 0 || prev.auditedBalance !== 0
          const archived = archivedRows.filter((r) => r.segmentKey === seg.key)
          if (hasData) {
            expect(archived).toHaveLength(1)
            expect(archived[0].archived).toBe(true)
            expect(archived[0].lossRate).toBe(prev.lossRate)
            expect(archived[0].bookBalance).toBe(prev.bookBalance)
          } else {
            expect(archived).toHaveLength(0)
          }
        }
      }),
      { numRuns: 300 },
    )
  })
})
