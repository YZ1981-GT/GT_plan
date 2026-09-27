/**
 * G14 信用减值损失 — 集成测试
 *
 * Spec: .kiro/specs/g14-credit-impairment-loss/ Task 8.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const { mockGet, mockPut, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn().mockResolvedValue({}),
  mockPost: vi.fn().mockResolvedValue({}),
}))

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onBeforeUnmount: vi.fn(), onMounted: vi.fn() }
})

vi.mock('../composables/workpaperAuditYear', () => ({
  useWorkpaperAuditYear: () => ({ value: 2025 }),
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: mockGet,
    put: mockPut,
    post: mockPost,
  },
}))

import {
  calcAdjustedAmount,
  calcNetImpairmentLoss,
  calcProvisionRollForward,
  calcChangeRate,
  isDebitCreditBalanced,
  isRollForwardBalanced,
  isReconciled,
  calcSubtotal,
} from '../composables/useG14FormulaEngine'
import { G14_LINE_ITEMS, G14_CHANGE_RATE_THRESHOLD, G14_ECL_CROSS_REF } from '../composables/g14Constants'
// G14 的导入导出 sheet 清单真源 = registry（原 `useG14ImportExport.ts` 只是
// 一份重复常量，已随孤儿处置删除 —— spec: workpaper-import-export-lifecycle-closure Task 16）
import { CYCLE_IMPORT_EXPORT } from '../shared/cycleImportExportRegistry'

function extractSheet(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G14A|G14-\d+)/)
  return m ? m[1] : ''
}

function isHtmlSheet(code: string): boolean {
  return ['G14A', 'G14-1', 'G14-2', 'G14-3', '底稿目录'].includes(code) || code.startsWith('附注')
}

describe('G14 集成 — sheetName 分发', () => {
  it('6个有效 sheet 正确分发', () => {
    expect(extractSheet('信用减值损失审计程序表G14A')).toBe('G14A')
    expect(extractSheet('审定表G14-1')).toBe('G14-1')
    expect(extractSheet('明细表G14-2')).toBe('G14-2')
    expect(extractSheet('调整分录汇总G14-3')).toBe('G14-3')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('底稿目录')).toBe('底稿目录')
  })

  it('未匹配走 OO 兜底', () => {
    expect(extractSheet('')).toBe('')
  })

  it('HTML sheet 判定', () => {
    expect(isHtmlSheet('G14-1')).toBe(true)
    expect(isHtmlSheet('附注上市')).toBe(true)
    expect(isHtmlSheet('底稿目录')).toBe(true)
    expect(isHtmlSheet('')).toBe(false)
  })
})

describe('G14 集成 — 损益类公式链', () => {
  it('TB→未审+调整=审定→EventBus payload', () => {
    const unadjusted = 500_000
    const adjustment = 20_000
    const audited = calcAdjustedAmount(unadjusted, adjustment)
    expect(audited).toBe(520_000)

    const detail = { accountCode: '6702', adjudicatedAmount: audited }
    expect(detail.accountCode).toBe('6702')
    expect(detail.adjudicatedAmount).toBe(520_000)
  })

  it('G14-2 合计与 G14-1 合计一致（同步模型）', () => {
    const rows = G14_LINE_ITEMS.map((def, i) => ({
      unadjusted: (i + 1) * 1000,
      adjustment: i * 100,
    }))
    const totalUnadjusted = calcSubtotal(rows.map((r) => r.unadjusted))
    const totalAdjustment = calcSubtotal(rows.map((r) => r.adjustment))
    const totalAudited = calcAdjustedAmount(totalUnadjusted, totalAdjustment)
    const sumLineAudited = rows.reduce(
      (s, r) => s + calcAdjustedAmount(r.unadjusted, r.adjustment),
      0,
    )
    expect(totalAudited).toBe(sumLineAudited)
  })
})

describe('G14 集成 — 坏账准备滚动验证', () => {
  it('期初+计提-转回-转销+其他=期末 → 平衡', () => {
    const opening = 100_000
    const provision = 30_000
    const reversal = 5_000
    const writeoff = 2_000
    const other = 0
    const closing = calcProvisionRollForward(opening, provision, reversal, writeoff, other)
    expect(isRollForwardBalanced(opening, provision, reversal, writeoff, closing, other)).toBe(true)
  })

  it('不平衡时检测失败', () => {
    expect(isRollForwardBalanced(100, 30, 5, 2, 200)).toBe(false)
  })

  it('净减值=计提-转回', () => {
    expect(calcNetImpairmentLoss(30_000, 5_000)).toBe(25_000)
  })

  it('核对列：审定=计入损益', () => {
    const audited = 110
    const profitLoss = 110
    expect(isReconciled(audited, profitLoss)).toBe(true)
  })
})

describe('G14 集成 — 变动率', () => {
  it('方向性正确', () => {
    expect(calcChangeRate(100, 150)).toBeGreaterThan(0)
    expect(calcChangeRate(100, 50)).toBeLessThan(0)
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  it('|变动率|>30% 触发原因必填阈值', () => {
    const rate = calcChangeRate(100, 140)
    expect(rate).not.toBeNull()
    expect(Math.abs(rate!)).toBeGreaterThan(G14_CHANGE_RATE_THRESHOLD)
  })
})

describe('G14 集成 — 调整分录借贷平衡', () => {
  it('账项调整净额可汇总', () => {
    const rows = [
      { category: '账项调整', debitAmount: 10000, creditAmount: 0 },
      { category: '账项调整', debitAmount: 0, creditAmount: 2000 },
      { category: '报表调整', debitAmount: 5000, creditAmount: 5000 },
    ]
    const net = rows
      .filter((r) => r.category === '账项调整')
      .reduce((s, r) => s + r.debitAmount - r.creditAmount, 0)
    expect(net).toBe(8000)
    expect(isDebitCreditBalanced([10000], [10000])).toBe(true)
  })
})

// 🔴 C-9（spec g-cycle-single-region-detail-lanes）：行集改为权威模板的固定 **9 行**。
//    原第 10 行 `ca`（合同资产减值损失）是自研的 —— 模板 `明细表G14-2` R11-R19 没有该专行，
//    10 行数据落进 9 行区会扩行、把 footer R20 挤下去。合同资产 ECL 已并入「其他」行。
describe('G14 集成 — 固定 9 类行（对齐权威模板）', () => {
  it('G14_LINE_ITEMS 逐项等于模板 A 列固定行序', async () => {
    const { G14_TEMPLATE_ROW_LABELS } = await import('../composables/g14Constants')
    expect(G14_LINE_ITEMS).toHaveLength(9)
    expect(G14_LINE_ITEMS.map((r) => r.label)).toEqual([...G14_TEMPLATE_ROW_LABELS])
    expect(G14_LINE_ITEMS.find((r) => r.rowKey === 'othdebt')?.counterpartKind).toBe('oci')
  })

  it('🔴 无「合同资产减值损失」专行，其 1142 取数并入「其他」行', () => {
    expect(G14_LINE_ITEMS.map((r) => r.rowKey)).not.toContain('ca')
    expect(G14_LINE_ITEMS.map((r) => r.label)).not.toContain('合同资产减值损失')
    const other = G14_LINE_ITEMS.find((r) => r.rowKey === 'other')!
    expect(other.tbPrefixes).toContain('1142')
    expect(other.tbNameHints.join('')).toContain('合同资产')
  })

  it('🔴 应收款项融资的 label 逐字取模板（坏账损失，不是减值损失）', () => {
    expect(G14_LINE_ITEMS.find((r) => r.rowKey === 'rfin')?.label).toBe('应收款项融资坏账损失')
  })
})

describe('G14 集成 — 导入导出', () => {
  it('G14_IMPORT_EXPORT_SHEETS 包含 G14-2 和 G14-3', () => {
    expect(CYCLE_IMPORT_EXPORT.g14.sheets).toContain('G14-2')
    expect(CYCLE_IMPORT_EXPORT.g14.sheets).toContain('G14-3')
  })
})

describe('G14 集成 — useG14Detail 持久化', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('updateCell 触发滚动与核对重算', async () => {
    const { useG14Detail } = await import('../composables/useG14Detail')
    const saved: Array<{ id: string; data: unknown }> = []
    const allResponses = ref(new Map())
    const detail = useG14Detail({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (itemId, data) => { saved.push({ id: itemId, data }) },
    })

    detail.updateCell('ar', 'currentProvision', 100)
    detail.updateCell('ar', 'currentReversal', 20)
    detail.updateCell('ar', 'openingProvision', 500)
    detail.updateCell('ar', 'currentWriteoff', 10)

    const ar = detail.rows.value.find((r) => r.rowKey === 'ar')
    expect(ar?.profitLoss).toBe(80)
    // 🔴 C-9：期末余额 J 是模板公式 =F+G-H-I，不再是录入列（原判据先 updateCell
    //    写 570 再断言 rollForwardBalanced —— 那套「录入期末 vs 推算期末」是双源）
    expect(ar?.closingProvision).toBe(570)
    expect(ar?.reconciled).toBe(ar?.currentAudited === ar?.profitLoss)
    expect(saved.some((s) => s.id === 'G14-detail-rows')).toBe(true)
    // 公式列不入 store（由 enrichRow 重算）
    const payload = JSON.parse(String(saved.at(-1)!.data.remark))
    expect(Object.keys(payload[0])).not.toContain('closingProvision')
    expect(Object.keys(payload[0])).not.toContain('profitLoss')
  })

  it('旧版负数转回自动迁移为正数', async () => {
    const { useG14Detail } = await import('../composables/useG14Detail')
    const allResponses = ref(new Map([
      ['G14-detail-rows', {
        item_id: 'G14-detail-rows',
        remark: JSON.stringify([{
          rowKey: 'ar',
          currentProvision: 100,
          currentReversal: -20,
          openingProvision: 500,
          currentWriteoff: 10,
        }]),
      }],
    ]))
    const detail = useG14Detail({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    const ar = detail.rows.value.find((r) => r.rowKey === 'ar')
    expect(ar?.currentReversal).toBe(20)
    expect(ar?.profitLoss).toBe(80)
    expect(ar?.closingProvision).toBe(570)
  })

  it('回填未审（期末余额由模板公式恒算，不再有「推算期末」按钮）', async () => {
    const { useG14Detail } = await import('../composables/useG14Detail')
    const allResponses = ref(new Map())
    const detail = useG14Detail({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    detail.updateCell('ar', 'currentProvision', 100)
    detail.updateCell('ar', 'currentReversal', 20)
    detail.updateCell('ar', 'openingProvision', 500)
    detail.updateCell('ar', 'currentWriteoff', 10)
    detail.fillUnauditedFromProfitLoss()
    const ar = detail.rows.value.find((r) => r.rowKey === 'ar')
    expect(ar?.closingProvision).toBe(570)
    expect(ar?.currentUnadjusted).toBe(80)
    expect(ar?.reconciled).toBe(true)
    expect((detail as Record<string, unknown>).fillClosingFromRollForward).toBeUndefined()
  })

  it('🔴 按试算倒推期初：令 期末=试算期末（期初 = 试算 − 计提 + 转回 + 转销）', async () => {
    const { useG14Detail } = await import('../composables/useG14Detail')
    const allResponses = ref(new Map([
      ['G14-detail-provision-tb', {
        item_id: 'G14-detail-provision-tb',
        remark: JSON.stringify({ ar: 600 }),
      }],
    ]))
    const detail = useG14Detail({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    detail.updateCell('ar', 'currentProvision', 100)
    detail.updateCell('ar', 'currentReversal', 20)
    detail.updateCell('ar', 'currentWriteoff', 10)
    detail.applyTbClosingToOpening()
    const ar = detail.rows.value.find((r) => r.rowKey === 'ar')
    expect(ar?.openingProvision).toBe(530)
    expect(ar?.closingProvision).toBe(600)
    expect(ar?.tbClosingMatched).toBe(true)
  })
})

describe('G14 集成 — useG14Adjustment 同步', () => {
  it('syncToDetail 将账项调整净额按回写行回写', async () => {
    const { useG14Adjustment } = await import('../composables/useG14Adjustment')
    const allResponses = ref(new Map())
    let applied: Record<string, number> | null = null
    const adj = useG14Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
      applyAdjustmentToDetail: (byRow) => { applied = byRow },
    })

    adj.addRow()
    const rowId = adj.rows.value[0].rowId
    adj.updateRow(rowId, {
      category: '账项调整',
      accountCode: '6702',
      adjudicationRowKey: 'other',
      debitAmount: 5000,
      creditAmount: 1000,
    })
    adj.syncToDetail()

    expect(applied?.other).toBe(4000)
  })
})

describe('G14 集成 — ECL 交叉索引', () => {
  it('各行默认跳转 D/G 循环底稿', () => {
    expect(G14_ECL_CROSS_REF.ar).toBe('wp:D2-1')
    expect(G14_ECL_CROSS_REF.debt).toBe('wp:G4-1')
    expect(G14_ECL_CROSS_REF.ltar).toBe('wp:G5-1')
  })
})

describe('G14 集成 — EventBus 审定发布', () => {
  it('substantive:adjudicated 可被监听', () => {
    const handler = vi.fn()
    window.addEventListener('substantive:adjudicated', handler)
    window.dispatchEvent(
      new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: '6702', adjudicatedAmount: 12345 },
      }),
    )
    expect(handler).toHaveBeenCalled()
    window.removeEventListener('substantive:adjudicated', handler)
  })
})
