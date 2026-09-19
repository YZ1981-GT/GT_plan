/**
 * Feature: platform-global-hardening, Property 5
 *
 * Property 5: 导出单位换算可还原（度量关系）
 * Validates: Requirements 1.6
 *
 * 对任意原始元值 rawYuan 与任意单位除数 divisor ∈ {1, 1000, 10000}：
 * - `applyExportUnit(rawYuan, divisor) * divisor` SHALL 在浮点误差内等于 rawYuan
 * - 导出表头 SHALL 标注与 divisor 对应的 unitSuffix（元/千元/万元）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { applyExportUnit, exportUnitHeaderNote } from '@/utils/exportUnit'

// ─── divisor → unitSuffix 映射（规范定义） ─────────────────────────────────────
const DIVISOR_SUFFIX_MAP: Record<number, string> = {
  1: '元',
  1000: '千元',
  10000: '万元',
}

describe('Property 5: 导出单位换算可还原（度量关系）', () => {
  it('applyExportUnit(rawYuan, divisor) * divisor ≈ rawYuan (浮点误差内)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e15, max: 1e15, noNaN: true, noDefaultInfinity: true }),
        fc.constantFrom(1, 1000, 10000),
        (rawYuan, divisor) => {
          const converted = applyExportUnit(rawYuan, divisor)
          const restored = converted * divisor
          // 浮点误差容忍：相对误差或绝对误差
          const absDiff = Math.abs(restored - rawYuan)
          const tolerance = Math.max(1e-10, Math.abs(rawYuan) * 1e-10)
          expect(absDiff).toBeLessThanOrEqual(tolerance)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('exportUnitHeaderNote 表头后缀与 divisor 对应（元/千元/万元）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(1, 1000, 10000),
        (divisor) => {
          const expectedSuffix = DIVISOR_SUFFIX_MAP[divisor]
          const headerNote = exportUnitHeaderNote(expectedSuffix)
          // 表头应包含 `（单位：{suffix}）` 格式
          expect(headerNote).toBe(`（单位：${expectedSuffix}）`)
        },
      ),
      { numRuns: 100 },
    )
  })
})
