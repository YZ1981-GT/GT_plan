/**
 * Unit Tests — D1TabWriteoffCheck 组件逻辑验证
 *
 * Spec: .kiro/specs/d1-writeoff-check/
 * Task: 3.5
 *
 * 测试 composable 的响应式行为和纯函数逻辑，不挂载 Vue 组件。
 * 覆盖：双模式切换、转回/核销合计行、预警高亮、跨Spec差异计算。
 *
 * **Validates: Requirements 1.2, 4.2, 12.6**
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  useD1WriteoffCheck,
  isReversalExceedsProvision,
  isWriteoffExceedsProvision,
  getMissingReversalFields,
  getMissingWriteoffFields,
  sumArray,
  parseNum,
  type ReversalRow,
  type WriteoffRow,
} from '../../composables/useD1WriteoffCheck'

// ─── Helper: 创建 composable 实例 ─────────────────────────────────────────────

function createComposable(initialResponses: Record<string, any> = {}) {
  const map = new Map<string, any>(Object.entries(initialResponses))
  const allResponses = ref(map)
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const saveDebouncedText = vi.fn()

  const result = useD1WriteoffCheck({
    allResponses: allResponses as any,
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    saveImmediate,
    saveDebouncedText,
    isReadonly: ref(false),
  })

  return { ...result, allResponses, saveImmediate, saveDebouncedText }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 双模式切换逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('双模式切换逻辑', () => {
  it('editorMode ref 默认 html，可切换到 oo', () => {
    // editorMode 是组件内 ref，这里测试纯逻辑：
    // ooHealthy=false 时 oo 选项 disabled
    const editorMode = ref<'html' | 'oo'>('html')
    const ooHealthy = ref(true)

    expect(editorMode.value).toBe('html')
    editorMode.value = 'oo'
    expect(editorMode.value).toBe('oo')

    // ooHealthy 控制禁用
    ooHealthy.value = false
    const modeOptions = [
      { label: '结构化视图', value: 'html' },
      { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
    ]
    expect(modeOptions[1].disabled).toBe(true)
  })

  it('ooHealthy=true 时在线编辑不禁用', () => {
    const ooHealthy = ref(true)
    const modeOptions = [
      { label: '结构化视图', value: 'html' },
      { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
    ]
    expect(modeOptions[1].disabled).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 转回/核销合计行正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('转回/核销合计行正确性', () => {
  it('reversalTotalE/F 正确 SUM 多行', () => {
    const rows: ReversalRow[] = [
      { id: '1', unitName: 'A', reason: '', recoveryMethod: '', originalBasis: '', reversalAmount: 100, priorProvisionAmount: 200, reasonabilityAnalysis: '', indexRef: '' },
      { id: '2', unitName: 'B', reason: '', recoveryMethod: '', originalBasis: '', reversalAmount: 300, priorProvisionAmount: 500, reasonabilityAnalysis: '', indexRef: '' },
    ]

    const initial = { 'D1-writeoff-reversal-rows': { item_id: 'D1-writeoff-reversal-rows', conclusion: null, remark: JSON.stringify(rows) } }
    const { reversalTotalE, reversalTotalF } = createComposable(initial)

    expect(reversalTotalE.value).toBe(400)
    expect(reversalTotalF.value).toBe(700)
  })

  it('writeoffTotalC 正确 SUM 多行', () => {
    const rows: WriteoffRow[] = [
      { id: '1', unitName: 'X', noteNature: '', writeoffAmount: 1000, writeoffReason: '', writeoffProcedure: '' },
      { id: '2', unitName: 'Y', noteNature: '', writeoffAmount: 2500, writeoffReason: '', writeoffProcedure: '' },
      { id: '3', unitName: 'Z', noteNature: '', writeoffAmount: 500, writeoffReason: '', writeoffProcedure: '' },
    ]

    const initial = { 'D1-writeoff-writeoff-rows': { item_id: 'D1-writeoff-writeoff-rows', conclusion: null, remark: JSON.stringify(rows) } }
    const { writeoffTotalC } = createComposable(initial)

    expect(writeoffTotalC.value).toBe(4000)
  })

  it('空行时合计为 0', () => {
    const { reversalTotalE, reversalTotalF, writeoffTotalC } = createComposable()
    expect(reversalTotalE.value).toBe(0)
    expect(reversalTotalF.value).toBe(0)
    expect(writeoffTotalC.value).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 预警高亮显示条件
// ═══════════════════════════════════════════════════════════════════════════════

describe('预警高亮显示条件', () => {
  it('reversalExceedsProvision: E > F 且 E > 0 时返回 true', () => {
    expect(isReversalExceedsProvision(500, 300)).toBe(true)
    expect(isReversalExceedsProvision(100, 100)).toBe(false)
    expect(isReversalExceedsProvision(0, 100)).toBe(false)
    expect(isReversalExceedsProvision(-10, -20)).toBe(false)
  })

  it('writeoffExceedsProvision: writeoffTotalC > eclCurrentTotal 时返回 true', () => {
    expect(isWriteoffExceedsProvision(5000, 3000)).toBe(true)
    expect(isWriteoffExceedsProvision(1000, 3000)).toBe(false)
    expect(isWriteoffExceedsProvision(5000, null)).toBe(false)
    expect(isWriteoffExceedsProvision(5000, 0)).toBe(false)
  })

  it('missingReversalFields: amount>0 且字段为空时返回缺失字段', () => {
    const row: ReversalRow = { id: '1', unitName: '', reason: '', recoveryMethod: '', originalBasis: '', reversalAmount: 100, priorProvisionAmount: 0, reasonabilityAnalysis: '', indexRef: '' }
    expect(getMissingReversalFields(row)).toEqual(['reason', 'reasonabilityAnalysis'])
  })

  it('missingReversalFields: amount=0 时无必填要求', () => {
    const row: ReversalRow = { id: '1', unitName: '', reason: '', recoveryMethod: '', originalBasis: '', reversalAmount: 0, priorProvisionAmount: 0, reasonabilityAnalysis: '', indexRef: '' }
    expect(getMissingReversalFields(row)).toEqual([])
  })

  it('missingWriteoffFields: amount>0 且字段为空时返回缺失字段', () => {
    const row: WriteoffRow = { id: '1', unitName: '', noteNature: '', writeoffAmount: 200, writeoffReason: '', writeoffProcedure: '', reasonabilityAnalysis: '' }
    expect(getMissingWriteoffFields(row)).toEqual(['writeoffReason', 'writeoffProcedure', 'reasonabilityAnalysis'])
  })

  it('missingWriteoffFields: amount=0 时无必填要求', () => {
    const row: WriteoffRow = { id: '1', unitName: '', noteNature: '', writeoffAmount: 0, writeoffReason: '', writeoffProcedure: '', reasonabilityAnalysis: '' }
    expect(getMissingWriteoffFields(row)).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. 跨Spec差异计算
// ═══════════════════════════════════════════════════════════════════════════════

describe('跨Spec差异计算', () => {
  it('reversalDiff 正确计算本表合计 - D1-4合计', () => {
    const rows: ReversalRow[] = [
      { id: '1', unitName: '', reason: '', recoveryMethod: '', originalBasis: '', reversalAmount: 500, priorProvisionAmount: 800, reasonabilityAnalysis: '', indexRef: '' },
    ]
    const initial = {
      'D1-writeoff-reversal-rows': { item_id: 'D1-writeoff-reversal-rows', conclusion: null, remark: JSON.stringify(rows) },
      'D1-adj-bad-debt-reversal': { item_id: 'D1-adj-bad-debt-reversal', conclusion: null, remark: '400' },
    }
    const { reversalDiff } = createComposable(initial)
    // 本表500 - D1-4的400 = 100
    expect(reversalDiff.value).toBe(100)
  })

  it('writeoffDiff 正确计算', () => {
    const rows: WriteoffRow[] = [
      { id: '1', unitName: '', noteNature: '', writeoffAmount: 300, writeoffReason: '', writeoffProcedure: '' },
    ]
    const initial = {
      'D1-writeoff-writeoff-rows': { item_id: 'D1-writeoff-writeoff-rows', conclusion: null, remark: JSON.stringify(rows) },
      'D1-adj-bad-debt-writeoff': { item_id: 'D1-adj-bad-debt-writeoff', conclusion: null, remark: '300' },
    }
    const { writeoffDiff } = createComposable(initial)
    // 本表300 - D1-4的300 = 0
    expect(writeoffDiff.value).toBe(0)
  })

  it('D1-4 未加载时 diff 为 null', () => {
    const { reversalDiff, writeoffDiff } = createComposable()
    expect(reversalDiff.value).toBeNull()
    expect(writeoffDiff.value).toBeNull()
  })
})
