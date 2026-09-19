/**
 * useC1SampleEngineOcr.pbt.spec.ts — C1-4-4 附件 OCR merge 非破坏性属性测试（Task 7.2）
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 7.2
 *
 * Feature: c1-entity-level-control, Property P8: OCR merge 非破坏性
 *   For any OCR 结果与既有样本行，merge 后仅填充空字段或经用户确认字段，
 *   未确认的非空字段不被覆盖。
 * **Validates: Requirements 10.3**
 *
 * 纯函数 PBT：直接验证 useC1SampleEngine.mergeSampleRow / mapOcrToSampleCells，
 * 无组件挂载、无网络。numRuns: 25。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  mergeSampleRow,
  mapOcrToSampleCells,
  SAMPLE_MERGE_COLS,
  type SampleCellMap,
} from '../composables/useC1SampleEngine'

// ─── 生成器 ───────────────────────────────────────────────────────────────────

/** 单元值：空白（'' / 空格）或非空字符串，覆盖 merge 判空分支 */
const cellArb = fc.oneof(
  fc.constant(''),
  fc.constant('   '),
  fc.string({ minLength: 1, maxLength: 12 }).map((s) => s.trim() === '' ? 'x' : s),
)

/** 样本行单元映射：随机覆盖若干列（含缺列场景） */
const cellMapArb: fc.Arbitrary<SampleCellMap> = fc.dictionary(
  fc.constantFrom(...SAMPLE_MERGE_COLS),
  cellArb,
)

const isBlank = (v: string | undefined): boolean =>
  v === undefined || v === null || String(v).trim() === ''

// ══════════════════════════════════════════════════════════════════════════════
// Property P8: OCR merge 非破坏性（未确认的非空字段永不被覆盖）
// ══════════════════════════════════════════════════════════════════════════════

describe('Feature: c1-entity-level-control, Property P8: OCR merge 非破坏性', () => {
  it('未确认的非空既有字段在 merge 后保持原值不变', () => {
    fc.assert(
      fc.property(cellMapArb, cellMapArb, (existing, incoming) => {
        // confirmedCols 为空 → 模拟「仅填空字段」的默认非破坏性行为（组件默认路径）
        const { merged, filledCols, skippedCols } = mergeSampleRow(existing, incoming)

        for (const col of SAMPLE_MERGE_COLS) {
          const existedNonBlank = !isBlank(existing[col])
          if (existedNonBlank) {
            // 铁律：非空既有值绝不被覆盖
            expect(merged[col]).toBe(existing[col])
            expect(filledCols).not.toContain(col)
          }
        }
        // filledCols 与 skippedCols 互斥
        for (const c of filledCols) expect(skippedCols).not.toContain(c)
        // 被填充列：既有为空 + incoming 非空
        for (const c of filledCols) {
          expect(isBlank(existing[c])).toBe(true)
          expect(isBlank(incoming[c])).toBe(false)
        }
        // 被跳过列：既有非空 + incoming 非空（保护）
        for (const c of skippedCols) {
          expect(isBlank(existing[c])).toBe(false)
          expect(isBlank(incoming[c])).toBe(false)
        }
      }),
      { numRuns: 25 },
    )
  })

  it('在 confirmedCols 中的列允许覆盖既有非空值；其余非空列仍受保护', () => {
    fc.assert(
      fc.property(
        cellMapArb,
        cellMapArb,
        fc.subarray([...SAMPLE_MERGE_COLS]),
        (existing, incoming, confirmed) => {
          const { merged } = mergeSampleRow(existing, incoming, confirmed)
          for (const col of SAMPLE_MERGE_COLS) {
            const existedNonBlank = !isBlank(existing[col])
            const incomingNonBlank = !isBlank(incoming[col])
            if (existedNonBlank && !confirmed.includes(col)) {
              // 未确认的非空字段 → 保留原值
              expect(merged[col]).toBe(existing[col])
            } else if (existedNonBlank && confirmed.includes(col) && incomingNonBlank) {
              // 已确认 + incoming 非空 → 允许覆盖为 incoming（trim 后）
              expect(merged[col]).toBe(String(incoming[col]).trim())
            }
          }
        },
      ),
      { numRuns: 25 },
    )
  })

  it('mergeSampleRow 为纯函数：不修改入参对象', () => {
    fc.assert(
      fc.property(cellMapArb, cellMapArb, (existing, incoming) => {
        const existingSnap = JSON.stringify(existing)
        const incomingSnap = JSON.stringify(incoming)
        mergeSampleRow(existing, incoming)
        expect(JSON.stringify(existing)).toBe(existingSnap)
        expect(JSON.stringify(incoming)).toBe(incomingSnap)
      }),
      { numRuns: 25 },
    )
  })

  it('mapOcrToSampleCells 仅产出非空值（不污染既有单元）', () => {
    fc.assert(
      fc.property(
        fc.dictionary(fc.string({ maxLength: 10 }), fc.oneof(fc.string(), fc.integer(), fc.constant(''))),
        (fields) => {
          const out = mapOcrToSampleCells(fields as any)
          for (const k of Object.keys(out)) {
            expect(isBlank(out[k])).toBe(false)
            // 只输出合法样本列
            expect(SAMPLE_MERGE_COLS).toContain(k as any)
          }
        },
      ),
      { numRuns: 25 },
    )
  })
})
