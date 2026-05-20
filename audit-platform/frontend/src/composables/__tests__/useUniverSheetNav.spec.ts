/**
 * useUniverSheetNav.spec.ts — Sprint 2 Task 2.43
 *
 * has_foreign_currency 切换 → setRowVisible 调用断言
 * scenarioFilter 过滤 IPO 应对 / 修订前 sheet
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useUniverSheetNav, type ScenarioFilter } from '../useUniverSheetNav'

function buildMockSheet(name: string, id: string, hidden = false) {
  return {
    getSheetId: () => id,
    getSheetName: () => name,
    isSheetHidden: () => hidden,
    setRowVisible: vi.fn(),
    activate: vi.fn(),
  }
}

function buildMockApi(sheetNames: string[]) {
  const sheets = sheetNames.map((n, idx) => buildMockSheet(n, `s${idx}`))
  const wb = {
    getSheets: () => sheets,
    getActiveSheet: () => sheets[0],
    setActiveSheet: vi.fn(),
    getId: () => 'wb1',
  }
  return {
    getActiveWorkbook: () => wb,
    executeCommand: vi.fn(),
    _sheets: sheets,
    _wb: wb,
  }
}

describe('useUniverSheetNav — scenarioFilter', () => {
  it('normal 场景过滤 IPO 应对/舞弊应对相关 sheet', () => {
    const api = ref(buildMockApi([
      '货币资金审定表E1-1',
      '货币资金现金明细表E1-2',
      'IPO 应对程序E1-26',
      '反舞弊检查E1-31',
      '银行存款明细表E1-3',
    ]))
    const filter = ref<ScenarioFilter>({ scenario: 'normal', hasForeignCurrency: true })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).toContain('货币资金审定表E1-1')
    expect(names).toContain('货币资金现金明细表E1-2')
    expect(names).toContain('银行存款明细表E1-3')
    expect(names).not.toContain('IPO 应对程序E1-26')
    expect(names).not.toContain('反舞弊检查E1-31')
  })

  it('ipo 场景保留 IPO 应对/舞弊应对相关 sheet', () => {
    const api = ref(buildMockApi([
      '货币资金审定表E1-1',
      'IPO 应对程序E1-26',
      '反舞弊检查E1-31',
    ]))
    const filter = ref<ScenarioFilter>({ scenario: 'ipo', hasForeignCurrency: false })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).toContain('IPO 应对程序E1-26')
    expect(names).toContain('反舞弊检查E1-31')
  })

  it('修订前/示例/提示 sheet 永远过滤', () => {
    const api = ref(buildMockApi([
      'F1-6 现金分析表（修订前）',
      'E1-1 货币资金审定表（示例）',
      'B23-2 控制了解（提示）',
      '货币资金现金明细表E1-2',
    ]))
    const filter = ref<ScenarioFilter>({ scenario: 'ipo', hasForeignCurrency: true })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('F1-6 现金分析表（修订前）')
    expect(names).not.toContain('E1-1 货币资金审定表（示例）')
    expect(names).not.toContain('B23-2 控制了解（提示）')
    expect(names).toContain('货币资金现金明细表E1-2')
  })

  it('hasForeignCurrency=false 过滤外币相关 sheet', () => {
    const api = ref(buildMockApi([
      '货币资金审定表E1-1',
      '外币现金盘点E1-8',
      '银行存款明细表E1-3',
    ]))
    const filter = ref<ScenarioFilter>({ scenario: 'normal', hasForeignCurrency: false })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('外币现金盘点E1-8')
    expect(names).toContain('银行存款明细表E1-3')
  })
})

describe('useUniverSheetNav — setRowsVisible / E1-1 双区显隐', () => {
  it('setRowsVisible 调用 sheet.setRowVisible API', () => {
    const api = ref(buildMockApi(['货币资金审定表E1-1']))
    const filter = ref<ScenarioFilter>({ scenario: 'normal', hasForeignCurrency: false })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    const ok = nav.setRowsVisible('货币资金审定表E1-1', [6, 7, 8], false)
    expect(ok).toBe(true)
    const sheet = (api.value as any)._sheets[0]
    expect(sheet.setRowVisible).toHaveBeenCalledWith([6, 7, 8], false)
  })

  it('applyForeignCurrencyVisibility 切换 has_foreign_currency=false 隐藏 R7-R21', () => {
    const api = ref(buildMockApi(['货币资金审定表E1-1']))
    const filter = ref<ScenarioFilter>({ scenario: 'normal', hasForeignCurrency: false })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    nav.applyForeignCurrencyVisibility()
    const sheet = (api.value as any)._sheets[0]
    expect(sheet.setRowVisible).toHaveBeenCalledWith(nav.E1_FOREIGN_REGION_ROWS, false)
    // E1_FOREIGN_REGION_ROWS = [6,7,...,20] 共 15 行
    expect(nav.E1_FOREIGN_REGION_ROWS.length).toBe(15)
    expect(nav.E1_FOREIGN_REGION_ROWS[0]).toBe(6)
  })

  it('applyForeignCurrencyVisibility 切换 has_foreign_currency=true 显示 R7-R21', () => {
    const api = ref(buildMockApi(['货币资金审定表E1-1']))
    const filter = ref<ScenarioFilter>({ scenario: 'normal', hasForeignCurrency: true })
    const nav = useUniverSheetNav(api, filter)
    nav.refresh()
    nav.applyForeignCurrencyVisibility()
    const sheet = (api.value as any)._sheets[0]
    expect(sheet.setRowVisible).toHaveBeenCalledWith(nav.E1_FOREIGN_REGION_ROWS, true)
  })
})

describe('useUniverSheetNav — 无 scenarioFilter 时不过滤', () => {
  it('未传 scenarioFilter 全部 sheet 都显示', () => {
    const api = ref(buildMockApi([
      '货币资金审定表E1-1',
      'IPO 应对程序E1-26',
      'F1-6 现金分析表（修订前）',
    ]))
    const nav = useUniverSheetNav(api)
    nav.refresh()
    const names = nav.sheets.value.map((s) => s.name)
    // legacy 修订前永远过滤
    expect(names).not.toContain('F1-6 现金分析表（修订前）')
    // 但无 filter 不过滤 IPO
    expect(names).toContain('IPO 应对程序E1-26')
    expect(names).toContain('货币资金审定表E1-1')
  })
})
