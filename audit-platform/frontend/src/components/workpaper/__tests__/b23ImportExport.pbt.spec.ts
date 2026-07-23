/**
 * Property-Based Test — B23 导入导出往返不变式（Round Trip）
 *
 * Spec: .kiro/specs/b23-business-control-rework/
 * Task: 5.2
 *
 * **Validates: Requirements 14.1, 14.2, 14.4**
 *
 * 对任意有效的控制矩阵数据，执行 model→rows→model 后得到的数据与原始数据等价。
 * 即 `rowToControlPoint(controlPointToRow(cp), cp.index) ≡ cp`（纯函数往返）。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  controlPointToRow,
  rowToControlPoint,
  CONTROL_MATRIX_HEADERS,
  isControlMatrixHeader,
} from '../composables/useB23ImportExport'
import {
  ASSERTION_OPTIONS,
  FREQUENCY_OPTIONS,
  PREVENT_DETECT_OPTIONS,
  CTRL_TYPE_L1_OPTIONS,
  YES_NO_OPTIONS,
  type B23ControlPoint,
  type ControlFrequency,
} from '../composables/useB23ProcessControl'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 生成非空字符串（排除分隔符歧义字符「、」「,」「，」） */
const arbSafeString = fc.string({ minLength: 1, maxLength: 30 })
  .filter(s => !s.includes('、') && !s.includes(',') && !s.includes('，'))
  .map(s => s.trim())
  .filter(s => s.length > 0)

/** 简单安全字符串（可为空） */
const arbMaybeString = fc.oneof(fc.constant(''), arbSafeString)

/** 认定多选（从固定枚举中随机选 1~3 项） */
const arbAssertions = fc.subarray([...ASSERTION_OPTIONS], { minLength: 1, maxLength: 3 })
  .map(arr => arr.map(String))

/** 控制频率（枚举 or null） */
const arbFrequency = fc.oneof(
  fc.constant(null as ControlFrequency | null),
  fc.constantFrom(...FREQUENCY_OPTIONS),
)

/** 预防性/检查性（枚举 or null） */
const arbPreventDetect = fc.oneof(
  fc.constant(null as '预防性' | '检查性' | null),
  fc.constantFrom(...PREVENT_DETECT_OPTIONS),
)

/** 是/否/null */
const arbYesNo = fc.oneof(
  fc.constant(null as '是' | '否' | null),
  fc.constantFrom(...YES_NO_OPTIONS),
)

/** 控制类型一级（枚举 or null） */
const arbCtrlTypeL1 = fc.oneof(
  fc.constant(null as string | null),
  fc.constantFrom(...CTRL_TYPE_L1_OPTIONS),
)

/** 控制类型二级（自由文本 or null） */
const arbCtrlTypeL2 = fc.oneof(
  fc.constant(null as string | null),
  arbSafeString,
)

/** 生成完整的 B23ControlPoint */
const arbControlPoint: fc.Arbitrary<B23ControlPoint> = fc.record({
  index: fc.integer({ min: 1, max: 100 }),
  subProcess: arbSafeString,
  ctrlNo: arbSafeString,
  ctrlName: arbSafeString,
  ctrlDesc: arbMaybeString,
  affectedItems: arbMaybeString,
  assertion: arbAssertions,
  wcgwRef: arbMaybeString,
  wcgwDetail: arbMaybeString,
  ctrlAttr: arbMaybeString,
  frequency: arbFrequency,
  itApp: arbMaybeString,
  preventDetect: arbPreventDetect,
  designEffective: arbYesNo,
  ctrlTypeL1: arbCtrlTypeL1,
  ctrlTypeL2: arbCtrlTypeL2,
  executor: arbMaybeString,
  executorOrg: arbMaybeString,
  hasDoc: arbYesNo,
  isKeyControl: arbYesNo,
  doControlTest: arbYesNo,
})

// ─── Properties ──────────────────────────────────────────────────────────────

describe('Feature: b23-business-control-rework, Property 2: 导入导出往返不变式', () => {
  /**
   * **Validates: Requirements 14.1, 14.2, 14.4**
   *
   * 核心属性：对任意有效 B23ControlPoint，
   * export（controlPointToRow）→ import（rowToControlPoint）应得到等价数据。
   */
  it('controlPointToRow → rowToControlPoint 往返等价', () => {
    fc.assert(
      fc.property(arbControlPoint, (cp) => {
        const row = controlPointToRow(cp)
        const restored = rowToControlPoint(row, cp.index)

        // 逐字段比较
        expect(restored.index).toBe(cp.index)
        expect(restored.subProcess).toBe(cp.subProcess)
        expect(restored.ctrlNo).toBe(cp.ctrlNo)
        expect(restored.ctrlName).toBe(cp.ctrlName)
        expect(restored.ctrlDesc).toBe(cp.ctrlDesc)
        expect(restored.affectedItems).toBe(cp.affectedItems)

        // 认定：export 用 '、' 连接，import 用 split('、',',','，') 还原
        expect(restored.assertion).toEqual(cp.assertion)

        expect(restored.wcgwRef).toBe(cp.wcgwRef)
        expect(restored.wcgwDetail).toBe(cp.wcgwDetail)
        expect(restored.ctrlAttr).toBe(cp.ctrlAttr)

        // 枚举/null 字段：null 导出为空串，导入还原为 null
        expect(restored.frequency).toBe(cp.frequency)
        expect(restored.itApp).toBe(cp.itApp)
        expect(restored.preventDetect).toBe(cp.preventDetect)
        expect(restored.designEffective).toBe(cp.designEffective)
        expect(restored.ctrlTypeL1).toBe(cp.ctrlTypeL1)
        expect(restored.ctrlTypeL2).toBe(cp.ctrlTypeL2)
        expect(restored.executor).toBe(cp.executor)
        expect(restored.executorOrg).toBe(cp.executorOrg)
        expect(restored.hasDoc).toBe(cp.hasDoc)
        expect(restored.isKeyControl).toBe(cp.isKeyControl)
        expect(restored.doControlTest).toBe(cp.doControlTest)
      }),
      { numRuns: 20 },
    )
  })

  it('controlPointToRow 输出行长度恒等于 CONTROL_MATRIX_HEADERS 长度', () => {
    fc.assert(
      fc.property(arbControlPoint, (cp) => {
        const row = controlPointToRow(cp)
        expect(row.length).toBe(CONTROL_MATRIX_HEADERS.length)
      }),
      { numRuns: 20 },
    )
  })

  it('isControlMatrixHeader 对 CONTROL_MATRIX_HEADERS 恒返回 true', () => {
    // 非随机，但确认静态常量自洽
    expect(isControlMatrixHeader([...CONTROL_MATRIX_HEADERS])).toBe(true)
  })

  it('isControlMatrixHeader 对随机非表头行恒返回 false', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ maxLength: 10 }), { minLength: CONTROL_MATRIX_HEADERS.length, maxLength: CONTROL_MATRIX_HEADERS.length }),
        (row) => {
          // 只要有一列与标准表头不同就应返回 false
          const isDifferent = row.some((cell, i) => cell.trim() !== CONTROL_MATRIX_HEADERS[i])
          if (isDifferent) {
            expect(isControlMatrixHeader(row)).toBe(false)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('多控制点批量往返：export 全部 → import 全部等价', () => {
    fc.assert(
      fc.property(
        fc.array(arbControlPoint, { minLength: 1, maxLength: 5 }),
        (points) => {
          // 规范化 index 为连续
          const normalized = points.map((cp, i) => ({ ...cp, index: i + 1 }))
          const rows = normalized.map(cp => controlPointToRow(cp))
          const restored = rows.map((row, i) => rowToControlPoint(row, i + 1))

          expect(restored.length).toBe(normalized.length)
          for (let i = 0; i < normalized.length; i++) {
            expect(restored[i].subProcess).toBe(normalized[i].subProcess)
            expect(restored[i].ctrlNo).toBe(normalized[i].ctrlNo)
            expect(restored[i].assertion).toEqual(normalized[i].assertion)
            expect(restored[i].frequency).toBe(normalized[i].frequency)
            expect(restored[i].isKeyControl).toBe(normalized[i].isKeyControl)
            expect(restored[i].doControlTest).toBe(normalized[i].doControlTest)
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})
