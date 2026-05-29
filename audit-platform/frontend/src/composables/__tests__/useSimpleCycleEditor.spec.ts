/**
 * useSimpleCycleEditor 单测 — 验证 K/L/M/N generic 工厂行为
 *
 * 不变量：
 *  1. dialogs.{key}DialogVisible === cycleDialogs[key].visible（透传同一 ref）
 *  2. triggers.is{X}Cycle 在 wpCode 以 X 开头时 true
 *  3. triggers.show{Cap}Trigger === cycleDialogs[key].trigger（透传 computed）
 *  4. handlers.on{Cap}Applied(sheet) 调用 cycleDialogs[key].onApplied(sheet)
 *  5. K/L/M/N 4 个具体 CycleEditor 经包装后字段完全等价 generic 直调
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, computed, type Ref } from 'vue'

import { useSimpleCycleEditor } from '../useSimpleCycleEditor'
import { useKCycleEditor } from '../useKCycleEditor'
import { useLCycleEditor } from '../useLCycleEditor'
import { useMCycleEditor } from '../useMCycleEditor'
import { useNCycleEditor } from '../useNCycleEditor'

// ─── 模拟 cycleDialogs ────────────────────────────────────────────────────────

function makeCycleDialogsStub() {
  const onApplied = {
    expenseAnalysis: vi.fn(),
    impairmentSummary: vi.fn(),
    interestCalc: vi.fn(),
    bondAmortization: vi.fn(),
    equityMovement: vi.fn(),
    incomeTaxCalc: vi.fn(),
  }
  function entry(name: keyof typeof onApplied) {
    return {
      visible: ref(false),
      trigger: computed(() => false),
      onApplied: onApplied[name],
    }
  }
  // 仅创建 K/L/M/N 4 cycle 用到的 entry，其他 stub 占位
  const stub = {
    expenseAnalysis: entry('expenseAnalysis'),
    impairmentSummary: entry('impairmentSummary'),
    interestCalc: entry('interestCalc'),
    bondAmortization: entry('bondAmortization'),
    equityMovement: entry('equityMovement'),
    incomeTaxCalc: entry('incomeTaxCalc'),
  } as any
  return { stub, onApplied }
}

function makeWpDetail(code: string): Ref<{ wp_code: string }> {
  return ref({ wp_code: code }) as Ref<{ wp_code: string }>
}

// ─── 通用 generic 测试 ───────────────────────────────────────────────────────

describe('useSimpleCycleEditor — 字段生成与透传', () => {
  it('单 dialog key：M 循环只生成 equityMovement 三件套', () => {
    const { stub, onApplied } = makeCycleDialogsStub()
    const api = useSimpleCycleEditor(makeWpDetail('M6-1'), stub, {
      cycleLetter: 'M',
      dialogKeys: ['equityMovement'] as const,
    })

    expect(api.dialogs.equityMovementDialogVisible).toBe(stub.equityMovement.visible)
    expect(api.triggers.isMCycle.value).toBe(true)
    expect(api.triggers.showEquityMovementTrigger).toBe(stub.equityMovement.trigger)

    api.handlers.onEquityMovementApplied('sheet-1')
    expect(onApplied.equityMovement).toHaveBeenCalledWith('sheet-1')
  })

  it('多 dialog key：K 循环生成 2 套字段', () => {
    const { stub, onApplied } = makeCycleDialogsStub()
    const api = useSimpleCycleEditor(makeWpDetail('K8-2'), stub, {
      cycleLetter: 'K',
      dialogKeys: ['expenseAnalysis', 'impairmentSummary'] as const,
    })

    expect(api.dialogs.expenseAnalysisDialogVisible).toBe(stub.expenseAnalysis.visible)
    expect(api.dialogs.impairmentSummaryDialogVisible).toBe(stub.impairmentSummary.visible)
    expect(api.triggers.isKCycle.value).toBe(true)
    expect(api.triggers.showExpenseAnalysisTrigger).toBe(stub.expenseAnalysis.trigger)
    expect(api.triggers.showImpairmentSummaryTrigger).toBe(stub.impairmentSummary.trigger)

    api.handlers.onExpenseAnalysisApplied('s1')
    api.handlers.onImpairmentSummaryApplied('s2')
    expect(onApplied.expenseAnalysis).toHaveBeenCalledWith('s1')
    expect(onApplied.impairmentSummary).toHaveBeenCalledWith('s2')
  })

  it('isXCycle 在 wpCode 不以 X 开头时为 false', () => {
    const { stub } = makeCycleDialogsStub()
    const api = useSimpleCycleEditor(makeWpDetail('A1'), stub, {
      cycleLetter: 'K',
      dialogKeys: ['expenseAnalysis'] as const,
    })
    expect(api.triggers.isKCycle.value).toBe(false)
  })

  it('isXCycle 接受小写 cycleLetter（统一大写比较）', () => {
    const { stub } = makeCycleDialogsStub()
    const api = useSimpleCycleEditor(makeWpDetail('k8'), stub, {
      cycleLetter: 'k',
      dialogKeys: ['expenseAnalysis'] as const,
    })
    expect((api.triggers as any).isKCycle.value).toBe(true)
  })

  it('wpDetail 为 null 时 isXCycle false 但不抛', () => {
    const { stub } = makeCycleDialogsStub()
    const api = useSimpleCycleEditor(ref(null), stub, {
      cycleLetter: 'M',
      dialogKeys: ['equityMovement'] as const,
    })
    expect(api.triggers.isMCycle.value).toBe(false)
  })
})

// ─── 4 个具体 CycleEditor 的向后兼容测试 ───────────────────────────────────────

describe('useKCycleEditor — 向后兼容', () => {
  it('暴露 isKCycle / 2 dialog visible / 2 trigger / 2 handler', () => {
    const { stub, onApplied } = makeCycleDialogsStub()
    const k = useKCycleEditor(makeWpDetail('K8-1'), stub)

    expect(k.dialogs.expenseAnalysisDialogVisible).toBeDefined()
    expect(k.dialogs.impairmentSummaryDialogVisible).toBeDefined()
    expect(k.triggers.isKCycle.value).toBe(true)
    expect(k.triggers.showExpenseAnalysisTrigger).toBeDefined()
    expect(k.triggers.showImpairmentSummaryTrigger).toBeDefined()

    k.handlers.onExpenseAnalysisApplied('s')
    k.handlers.onImpairmentSummaryApplied('s2')
    expect(onApplied.expenseAnalysis).toHaveBeenCalledWith('s')
    expect(onApplied.impairmentSummary).toHaveBeenCalledWith('s2')
  })
})

describe('useLCycleEditor — 向后兼容', () => {
  it('暴露 isLCycle / 2 dialog visible / 2 trigger / 2 handler', () => {
    const { stub, onApplied } = makeCycleDialogsStub()
    const l = useLCycleEditor(makeWpDetail('L1-3'), stub)

    expect(l.dialogs.interestCalcDialogVisible).toBeDefined()
    expect(l.dialogs.bondAmortizationDialogVisible).toBeDefined()
    expect(l.triggers.isLCycle.value).toBe(true)

    l.handlers.onInterestCalcApplied('s')
    l.handlers.onBondAmortizationApplied('s2')
    expect(onApplied.interestCalc).toHaveBeenCalledWith('s')
    expect(onApplied.bondAmortization).toHaveBeenCalledWith('s2')
  })
})

describe('useMCycleEditor — 向后兼容', () => {
  it('暴露 isMCycle + equityMovement 三件套', () => {
    const { stub, onApplied } = makeCycleDialogsStub()
    const m = useMCycleEditor(makeWpDetail('M6'), stub)

    expect(m.dialogs.equityMovementDialogVisible).toBeDefined()
    expect(m.triggers.isMCycle.value).toBe(true)
    expect(m.triggers.showEquityMovementTrigger).toBeDefined()

    m.handlers.onEquityMovementApplied('s')
    expect(onApplied.equityMovement).toHaveBeenCalledWith('s')
  })
})

describe('useNCycleEditor — 向后兼容', () => {
  it('暴露 isNCycle + incomeTaxCalc 三件套', () => {
    const { stub, onApplied } = makeCycleDialogsStub()
    const n = useNCycleEditor(makeWpDetail('N5'), stub)

    expect(n.dialogs.incomeTaxCalcDialogVisible).toBeDefined()
    expect(n.triggers.isNCycle.value).toBe(true)
    expect(n.triggers.showIncomeTaxCalcTrigger).toBeDefined()

    n.handlers.onIncomeTaxCalcApplied('s')
    expect(onApplied.incomeTaxCalc).toHaveBeenCalledWith('s')
  })
})
