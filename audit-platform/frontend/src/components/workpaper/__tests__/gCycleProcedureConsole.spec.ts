/**
 * G 循环 *A 程序表 — 统一对齐 D4A（CycleProgramConsoleTab，无抽凭/复核 toolbar）
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const WP_ROOT = path.resolve(__dirname, '..')

const D_PROCEDURE_FILES: { code: string; rel: string }[] = [
  { code: 'D1A', rel: 'd1/D1TabProcedure.vue' },
  { code: 'D2A', rel: 'd2/D2TabProcedure.vue' },
  { code: 'D3A', rel: 'd3/D3TabProcedure.vue' },
  { code: 'D4A', rel: 'd4/core/D4TabProcedure.vue' },
  { code: 'D5A', rel: 'd5/D5TabProcedure.vue' },
  { code: 'D6A', rel: 'd6/D6TabProcedure.vue' },
  { code: 'D7A', rel: 'd7/D7TabProcedure.vue' },
]

const G_PROCEDURE_FILES: { code: string; rel: string }[] = [
  { code: 'G1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'G2A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'G3A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'G4A', rel: 'g4-bond-investment-main/core/G4TabProcedure.vue' },
  { code: 'G5A', rel: 'g5-long-term-receivable/core/G5TabProcedure.vue' },
  { code: 'G6A', rel: 'g6-other-bond-investment-main/core/G6TabProcedure.vue' },
  { code: 'G7A', rel: 'g7-long-term-equity-main/core/G7TabProcedure.vue' },
  { code: 'G8A', rel: 'g8-other-equity-instruments/core/G8TabProcedure.vue' },
  { code: 'G9A', rel: 'g9-other-noncurrent-financial/core/G9TabProcedure.vue' },
  { code: 'G10A', rel: 'g10-trading-financial-liabilities/core/G10TabProcedure.vue' },
  { code: 'G11A', rel: 'g11-investment-income/core/G11TabProcedure.vue' },
  { code: 'G12A', rel: 'g12-net-hedge-gains/core/G12TabProcedure.vue' },
  { code: 'G13A', rel: 'g13-fair-value-changes/G13TabProcedure.vue' },
  { code: 'G14A', rel: 'g14-credit-impairment-loss/G14TabProcedure.vue' },
]

const FH_PROCEDURE_FILES: { code: string; rel: string }[] = [
  { code: 'F1A', rel: 'f1/F1TabProcedure.vue' },
  { code: 'F2A', rel: 'f2/core/F2TabProcedure.vue' },
  { code: 'F3A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'F4A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'F5A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'H10A', rel: 'h10/core/H10TabProcedure.vue' },
]

const E_PROCEDURE_FILES: { code: string; rel: string }[] = [
  { code: 'E1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'E26A', rel: 'shared/CycleTabProcedure.vue' },
]

const IN_PROCEDURE_FILES: { code: string; rel: string }[] = [
  { code: 'I1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'J1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'K1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'L1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'M1A', rel: 'shared/CycleTabProcedure.vue' },
  { code: 'N1A', rel: 'shared/CycleTabProcedure.vue' },
]

const MAIN_ENTRY_PROCEDURE_WIRING: { code: string; rel: string }[] = [
  { code: 'G1A', rel: 'GtG1TradingFinancialAssets.vue' },
  { code: 'G2A', rel: 'GtG2InterestReceivable.vue' },
  { code: 'G3A', rel: 'GtG3DividendReceivable.vue' },
  { code: 'F3A', rel: 'GtF3NotesPayable.vue' },
  { code: 'F4A', rel: 'GtF4AccountsPayable.vue' },
  { code: 'F5A', rel: 'GtF5CostOfSales.vue' },
  { code: 'E1A', rel: 'GtE1MonetaryFund.vue' },
  { code: 'L1A', rel: 'GtL1ShortTermLoans.vue' },
  { code: 'L2A', rel: 'GtL2InterestPayable.vue' },
]

describe('循环程序表对齐 D4A', () => {
  it.each([...D_PROCEDURE_FILES, ...G_PROCEDURE_FILES, ...FH_PROCEDURE_FILES])(
    '$code 使用 CycleProgramConsoleTab 且无抽凭模块',
    ({ rel }) => {
      const src = fs.readFileSync(path.join(WP_ROOT, rel), 'utf-8')
      expect(src.includes('CycleProgramConsoleTab') || src.includes('CycleTabProcedure')).toBe(true)
      expect(src).not.toContain('GtVoucherSamplingEngine')
      expect(src).not.toContain('GCycleProcedureCutoffPanel')
      expect(src).not.toContain('cutoff-sampling')
      expect(src).not.toContain('GtReviewTrigger')
    },
  )

  it('CycleProgramConsoleTab 壳层无复核按钮，并启用 cycleSheetMode', () => {
    const src = fs.readFileSync(
      path.join(WP_ROOT, 'shared/CycleProgramConsoleTab.vue'),
      'utf-8',
    )
    expect(src).not.toContain('GtReviewTrigger')
    expect(src).toContain('cycle-sheet-mode')
    expect(src).toContain('hide-categories')
  })

  it('D_CYCLE_PROCEDURE_SHEETS 覆盖 D1A~D7A', async () => {
    const { D_CYCLE_PROCEDURE_SHEETS } = await import('../composables/cycleProcedureSheets')
    for (const { code } of D_PROCEDURE_FILES) {
      expect(D_CYCLE_PROCEDURE_SHEETS[code]).toBeDefined()
      expect(D_CYCLE_PROCEDURE_SHEETS[code].sheetCode).toBe(code)
    }
  })

  it('G_CYCLE_PROCEDURE_SHEETS 覆盖 G1A~G14A', async () => {
    const { G_CYCLE_PROCEDURE_SHEETS } = await import('../composables/cycleProcedureSheets')
    const gCodes = G_PROCEDURE_FILES.map(f => f.code)
    for (const code of gCodes) {
      expect(G_CYCLE_PROCEDURE_SHEETS[code]).toBeDefined()
      expect(G_CYCLE_PROCEDURE_SHEETS[code].sheetCode).toBe(code)
    }
  })

  it('I~N 程序表配置覆盖代表性 *A', async () => {
    const {
      I_CYCLE_PROCEDURE_SHEETS,
      J_CYCLE_PROCEDURE_SHEETS,
      K_CYCLE_PROCEDURE_SHEETS,
      L_CYCLE_PROCEDURE_SHEETS,
      M_CYCLE_PROCEDURE_SHEETS,
      N_CYCLE_PROCEDURE_SHEETS,
      extractCycleProcedureSheetCode,
    } = await import('../composables/cycleProcedureSheets')
    expect(I_CYCLE_PROCEDURE_SHEETS.I1A.sheetLabel).toBe('无形资产实质性程序表I1A')
    expect(J_CYCLE_PROCEDURE_SHEETS.J1A.sheetLabel).toContain('J1A')
    expect(K_CYCLE_PROCEDURE_SHEETS.K13A.sheetCode).toBe('K13A')
    expect(L_CYCLE_PROCEDURE_SHEETS.L8A.sheetCode).toBe('L8A')
    expect(M_CYCLE_PROCEDURE_SHEETS.M10A.sheetCode).toBe('M10A')
    expect(N_CYCLE_PROCEDURE_SHEETS.N5A.sheetCode).toBe('N5A')
    expect(extractCycleProcedureSheetCode('其他应收款实质性程序表K1A')).toBe('K1A')
    expect(extractCycleProcedureSheetCode('B1A')).toBeNull()
  })

  it('a-program-console 经 GtCycleAProgramRouter 分发循环 *A', () => {
    const router = fs.readFileSync(path.join(WP_ROOT, 'GtCycleAProgramRouter.vue'), 'utf-8')
    const registry = fs.readFileSync(path.join(WP_ROOT, 'htmlRendererRegistry.ts'), 'utf-8')
    expect(router).toContain('CycleStandaloneProcedureShell')
    expect(router).toContain('GtAProgramConsole')
    expect(registry).toContain('GtCycleAProgramRouter')
  })

  it('FH/E 程序表配置覆盖 F1A~F5A 与 E1A/E26A', async () => {
    const { FH_CYCLE_PROCEDURE_SHEETS, E_CYCLE_PROCEDURE_SHEETS } =
      await import('../composables/cycleProcedureSheets')
    expect(FH_CYCLE_PROCEDURE_SHEETS.F1A.sheetLabel).toBe('预付账款实质性程序表F1A')
    expect(FH_CYCLE_PROCEDURE_SHEETS.F3A.sheetLabel).toBe('应付票据实质性程序表F3A')
    expect(FH_CYCLE_PROCEDURE_SHEETS.F4A.sheetLabel).toBe('应付账款实质性程序表F4A')
    expect(FH_CYCLE_PROCEDURE_SHEETS.F5A.sheetLabel).toBe('营业成本实质性程序表F5A')
    expect(E_CYCLE_PROCEDURE_SHEETS.E1A.sheetLabel).toBe('货币资金实质性程序表E1A')
    expect(E_CYCLE_PROCEDURE_SHEETS.E26A.sheetLabel).toBe('货币资金实质性程序表E26A')
  })

  it.each(MAIN_ENTRY_PROCEDURE_WIRING)(
    '$code 主入口已接线 CycleTabProcedure 且不再独占 OnlyOffice',
    ({ rel, code }) => {
      const src = fs.readFileSync(path.join(WP_ROOT, rel), 'utf-8')
      expect(src).toContain('CycleTabProcedure')
      expect(src).toContain(`sheet-code="${code}"`)
      expect(src).not.toMatch(new RegExp(`currentSheet === '${code}'[\\s\\S]{0,200}GtOnlyOfficeSheet`))
      expect(src).not.toMatch(new RegExp(`currentSheet === '${code}'[\\s\\S]{0,200}GtAProgramConsole`))
    },
  )

  it('FH_CYCLE_PROCEDURE_SHEETS 覆盖 F2A/H10A', async () => {
    const { FH_CYCLE_PROCEDURE_SHEETS } = await import('../composables/cycleProcedureSheets')
    expect(FH_CYCLE_PROCEDURE_SHEETS.F2A.sheetLabel).toBe('存货实质性程序表F2A')
    expect(FH_CYCLE_PROCEDURE_SHEETS.H10A.sheetLabel).toBe('资产处置损益实质性程序表H10A')
  })

  it('双模式页签文案统一为结构化视图/在线编辑', async () => {
    const { dualModeHtmlOoOptions, DUAL_MODE_LABEL_STRUCTURED, DUAL_MODE_LABEL_ONLINE } =
      await import('../composables/dualModeLabels')
    const opts = dualModeHtmlOoOptions()
    expect(opts[0].label).toBe(DUAL_MODE_LABEL_STRUCTURED)
    expect(opts[1].label).toBe(DUAL_MODE_LABEL_ONLINE)

    const g4 = fs.readFileSync(
      path.join(WP_ROOT, 'composables/useG4MainDualMode.ts'),
      'utf-8',
    )
    expect(g4).toContain('dualModeHtmlOoOptions')
    expect(g4).not.toContain("label: 'HTML'")
  })
})
