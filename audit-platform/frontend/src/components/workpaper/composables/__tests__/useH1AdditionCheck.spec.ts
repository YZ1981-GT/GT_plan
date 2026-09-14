/**
 * H1-7 增加检查 — 追查 / 专项清单 / H1-12 联动 单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  isCipTransferMethod,
  resolveDepStartDate,
  useH1AdditionCheck,
} from '../useH1AdditionCheck'
import {
  getMethodChecklist,
  calcChecklistProgress,
} from '../h1AdditionMethodChecklist'
import { calcNetValue } from '../useH1FormulaEngine'
import type { ChecklistItem } from '../useH1FormData'

function makeMap(entries: Record<string, any> = {}): Map<string, ChecklistItem> {
  const m = new Map<string, ChecklistItem>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, remark: typeof v === 'string' ? v : JSON.stringify(v) } as ChecklistItem)
  }
  return m
}

describe('isCipTransferMethod', () => {
  it('识别在建转入类增加方式', () => {
    expect(isCipTransferMethod('在建工程转入')).toBe(true)
    expect(isCipTransferMethod('外购')).toBe(false)
  })
})

describe('resolveDepStartDate', () => {
  it('优先级：折旧起算日 > 验收日 > 增加日', () => {
    expect(resolveDepStartDate({
      depStartDate: '2025-02-01',
      acceptanceDate: '2025-01-15',
      acquisitionDate: '2025-01-01',
    })).toBe('2025-02-01')
    expect(resolveDepStartDate({
      depStartDate: '',
      acceptanceDate: '2025-01-15',
      acquisitionDate: '2025-01-01',
    })).toBe('2025-01-15')
    expect(resolveDepStartDate({
      depStartDate: '',
      acceptanceDate: '',
      acquisitionDate: '2025-01-01',
    })).toBe('2025-01-01')
  })
})

describe('专项清单', () => {
  it('外购/在建有对应程序项', () => {
    expect(getMethodChecklist('外购').length).toBeGreaterThan(3)
    expect(getMethodChecklist('在建工程转入').some((i) => i.key === 'depStart')).toBe(true)
    expect(getMethodChecklist('未知方式X').length).toBeGreaterThan(0)
  })

  it('完成度计算', () => {
    const items = getMethodChecklist('外购')
    const p0 = calcChecklistProgress({}, items)
    expect(p0.done).toBe(0)
    expect(p0.incomplete).toBe(true)
    const checks: Record<string, string> = {}
    for (const it of items) checks[it.key] = 'Y'
    expect(calcChecklistProgress(checks, items).incomplete).toBe(false)
  })
})

describe('净值勾稽', () => {
  it('净值=原值−累计折旧−减值', () => {
    expect(calcNetValue(100_000, 10_000, 5_000)).toBe(85_000)
  })
})

describe('useH1AdditionCheck', () => {
  it('兼容旧字段并计算检查比例', () => {
    const allResponses = ref(makeMap({
      'H1-7-rows': [{
        rowId: 'a1',
        name: '旧版行',
        amount: 80_000,
        entryDate: '2025-03-01',
        invoiceNo: 'INV-1',
        checkResult: '异常',
      }],
      'H1-7-sampling-params': { totalPopulation: 200_000, samplingMethod: '货币单元抽样' },
    }))
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses)
    expect(state.rows.value[0].originalCost).toBe(80_000)
    expect(state.rows.value[0].checkResult).toBe('ERR')
    expect(state.summary.value.coverageRate).toBeCloseTo(40, 5)
  })

  it('cipTransferInTotal 汇总在建工程转入原值；cashPaidTotal 汇总实付现金', () => {
    const allResponses = ref(makeMap({
      'H1-7-rows': [
        { rowId: 'c', name: '厂房', additionMethod: '在建工程转入', originalCost: 600_000, paymentAmount: 0 },
        { rowId: 'p', name: '设备', additionMethod: '外购', originalCost: 200_000, paymentAmount: 180_000 },
        { rowId: 'c2', name: '管线', additionMethod: '在建转入', originalCost: 100_000, paymentAmount: 50_000 },
      ],
    }))
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses)
    // 仅「在建工程转入」类计入 CIP 合计（含别名「在建转入」）
    expect(state.cipTransferInTotal.value).toBeCloseTo(700_000)
    // 全部行实付现金合计
    expect(state.cashPaidTotal.value).toBeCloseTo(230_000)
  })

  it('证→账追查：未入账计入异常，差额公式', () => {
    const onSave = vi.fn()
    const allResponses = ref(makeMap())
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses, { onSave })
    state.addTraceRow('FP-1')
    const id = state.traceRows.value[0].rowId
    state.updateTraceCell(id, 'sourceAmount', 10_000)
    state.updateTraceCell(id, 'bookAmount', 8_000)
    state.updateTraceCell(id, 'recordedInBooks', 'N')
    expect(state.traceRows.value[0].amountDiff).toBe(2_000)
    expect(state.traceRows.value[0].checkResult).toBe('ERR')
    expect(state.summary.value.traceUnrecordedCount).toBe(1)
    expect(onSave).toHaveBeenCalledWith('H1-7-trace-rows', expect.any(Array))
  })

  it('从账→证样本生成追查行', () => {
    const allResponses = ref(makeMap({
      'H1-7-rows': [{
        rowId: 'v1',
        name: '设备A',
        invoiceRef: 'INV-9',
        invoiceAmount: 50_000,
        originalCost: 50_000,
        voucherNo: '记-1',
      }],
    }))
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses)
    expect(state.seedTraceFromVouchRows()).toBe(1)
    expect(state.seedTraceFromVouchRows()).toBe(0) // 去重
    expect(state.traceRows.value[0].sourceRef).toBe('INV-9')
    expect(state.traceRows.value[0].recordedInBooks).toBe('Y')
  })

  it('专项清单未完成预警 + 暂估缺起算预警', () => {
    const allResponses = ref(makeMap({
      'H1-7-rows': [
        {
          rowId: 'c1',
          name: '外购未勾选',
          additionMethod: '外购',
          originalCost: 1,
          methodChecks: {},
        },
        {
          rowId: 'p1',
          name: '暂估无起算',
          isProvisional: 'Y',
          originalCost: 1,
          depStartDate: '',
          acceptanceDate: '',
          acquisitionDate: '',
        },
      ],
      'H1-7-sampling-params': { totalPopulation: 2 },
    }))
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses)
    expect(state.needsChecklistIncompleteWarning(state.rows.value[0])).toBe(true)
    expect(state.needsProvisionalDepWarning(state.rows.value[1])).toBe(true)
    expect(state.summary.value.checklistIncompleteCount).toBe(1)
    expect(state.summary.value.provisionalNoDepStartCount).toBe(1)
  })

  it('推送折旧起算至 H1-12', () => {
    const saves: Array<{ id: string; val: any }> = []
    const allResponses = ref(makeMap({
      'H1-7-rows': [{
        rowId: 'a1',
        name: '数控机床',
        assetNo: 'FA-001',
        depStartDate: '2025-04-01',
        isProvisional: 'Y',
        originalCost: 100,
      }],
      'H1-12-rows': [{
        rowId: 'd1',
        assetNo: 'FA-001',
        assetName: '数控机床',
        startDate: '2024-01-01',
        remark: '',
      }],
    }))
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses, {
      onSave: (id, val) => saves.push({ id, val }),
    })
    const r = state.pushDepStartToH12()
    expect(r.linked).toBe(1)
    const h12Save = saves.find((s) => s.id === 'H1-12-A-rows')
      || saves.find((s) => s.id === 'H1-12-rows')
    expect(h12Save).toBeTruthy()
    expect(h12Save!.val[0].startDate).toBe('2025-04-01')
    expect(h12Save!.val[0].linkedFromH17).toBe(true)
    expect(saves.some((s) => s.id === 'H1-12-A-rows')).toBe(true)
    expect(saves.some((s) => s.id === 'H1-12-rows')).toBe(true)
  })

  it('推送折旧起算尊重 B 分支键', () => {
    const saves: Array<{ id: string; val: any }> = []
    const allResponses = ref(makeMap({
      'H1-12-branch': 'B',
      'H1-7-rows': [{
        rowId: 'a1',
        name: '机床B',
        assetNo: 'FA-B',
        depStartDate: '2025-06-01',
        originalCost: 50,
      }],
      'H1-12-B-rows': [{
        rowId: 'd1',
        assetNo: 'FA-B',
        assetName: '机床B',
        startDate: '2024-01-01',
        remark: '',
      }],
      'H1-12-rows': [{
        rowId: 'legacy',
        assetNo: 'OTHER',
        assetName: '不应匹配',
        startDate: '2020-01-01',
      }],
    }))
    const state = useH1AdditionCheck(ref('wp1'), ref('p1'), allResponses, {
      onSave: (id, val) => saves.push({ id, val }),
    })
    const r = state.pushDepStartToH12()
    expect(r.linked).toBe(1)
    const bSave = saves.find((s) => s.id === 'H1-12-B-rows')
    expect(bSave!.val[0].startDate).toBe('2025-06-01')
  })
})
