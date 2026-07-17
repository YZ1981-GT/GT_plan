/**
 * useAlternativeL05Data — L0-5 债务循环替代程序 composable
 *
 * confirmation-alternative-factory-convergence Task 11（L05 迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 L05 的 AltConfig + 调工厂 + 组装原返回签名，并旁挂 L05 独有面
 * （命名比例别名、balanceSummary、loading/importFromSummary/loadAll/persistAll）。
 *
 * 零回归约束：命名导出 `useAlternativeL05Data` + default export + `FORMAT_VERSION` 导出、
 * props 签名 `{wpId, projectId, htmlData, readonly}`、返回类型 `UseAlternativeL05DataReturn`、
 * buildPayload 返回 `AlternativeL05Payload` 逐字不变；L05 characterization spec 不改断言必须全绿。
 *
 * L05 差异（经 AltConfig 声明）：
 * - _format: alternative-l05-v1；默认 balance.item_name = '长期应付款/借款'
 * - baseAmount = c.balance?.closing_balance（期末余额）
 * - 🔴 emptyBase='zero'（空基数返回 0 而非 null，与 D/F/H/K 相反）
 * - 两比例算法不同源：repayment 用 FormulaEngine 的 calcRepaymentRatio（per-rule 注入，
 *   语义 = balance===0?0:num/den，空基数已由 emptyBase='zero' 兜底故等价 num/den）；
 *   mortgage 用默认 num/den
 * - calcTotal 注入 FormulaEngine 的 calcBlockTotal
 * - metricRatioKeys: receipt←repayment、shipment←mortgage
 *
 * Master-Detail 结构：公司列表 → 选中公司 → 4 区块检查表
 * 4 区块：①期后付款/还款检查 ②期末余额支持性证据(借款合同/银行对账单)
 *         ③本期借款检查 ④抵质押/担保证据
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  BlockType,
  CheckRow,
  BalanceSummary,
  AlternativeD05Metrics,
} from '../../alternativeD05/alternativeD05Types'
import { calcBlockTotal, calcRepaymentRatio } from './useL0FormulaEngine'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

export const FORMAT_VERSION = 'alternative-l05-v1' as const

export interface AlternativeL05Payload {
  _format: typeof FORMAT_VERSION
  companies: AlternativeCompany[]
}

export interface AlternativeL05Summary {
  investmentType: string
  openingBalance: number
  debitAmount: number
  creditAmount: number
  closingBalance: number
  currentLoan: number
  repaymentCheckRatio: number
  mortgageCheckRatio: number
}

export interface L01UnrepliedEntity {
  entity_name: string
  confirm_index?: string
  confirm_amount?: number
  unreplied_reason?: string
}

export interface UseAlternativeL05DataProps {
  wpId: string
  projectId: string
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeL05DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>
  loading: Ref<boolean>
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void
  importFromSummary: () => Promise<number>
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void
  getBlockRows: (company: AlternativeCompany, blockType: BlockType) => CheckRow[]
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getClosingBalance: (company: AlternativeCompany) => number
  getRepaymentRatio: (company: AlternativeCompany) => number
  getMortgageRatio: (company: AlternativeCompany) => number
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  balanceSummary: ComputedRef<AlternativeL05Summary>
  loadAll: () => void
  persistAll: () => AlternativeL05Payload
  buildPayload: () => AlternativeL05Payload
}

// ─── 4 区块金额 Sum 字段 ───────────────────────────────────────────────────

const SUM_FIELDS: Record<BlockType, string[]> = {
  block1: ['voucher_amount', 'repayment_principal', 'repayment_interest'],
  block2: ['voucher_amount', 'contract_amount', 'book_balance'],
  block3: ['voucher_amount', 'arrival_amount'],
  block4: ['voucher_amount', 'mortgage_amount', 'guarantee_amount'],
}

/** 对齐原 getBlockTotal 的 fallback：SUM_FIELDS[blockType] || ['voucher_amount'] */
function getSumFields(blockType: string): string[] {
  return SUM_FIELDS[blockType as BlockType] || ['voucher_amount']
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function precise(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Composable 主体（工厂适配器） ───────────────────────────────────────────

export function useAlternativeL05Data(props: UseAlternativeL05DataProps): UseAlternativeL05DataReturn {
  const loading = ref(false)

  const core = createAlternativeConfirmationData({
    format: FORMAT_VERSION,
    getSumFields,
    // L05 默认 balance 带负债科目名
    defaultBalance: () => ({ item_name: '长期应付款/借款' }),
    // 比例分母基数：期末余额（缺失/0 → emptyBase='zero' 交给工厂处理）
    baseAmount: (c: AlternativeCompany) => Number(c.balance?.closing_balance ?? 0),
    // 🔴 L05 空基数返回 0（与 D/F/H/K 相反）
    emptyBase: 'zero',
    ratios: [
      // repayment：block1 分子优先 repayment_principal → 回退 voucher_amount；per-rule 注入 calcRepaymentRatio（原样保险）
      {
        key: 'repayment',
        block: 'block1',
        fields: ['repayment_principal', 'voucher_amount'],
        payloadKey: 'receipt_check_ratio',
        calcRatio: calcRepaymentRatio,
      },
      // mortgage：block4 分子优先 mortgage_amount → 回退 voucher_amount；默认 num/den
      {
        key: 'mortgage',
        block: 'block4',
        fields: ['mortgage_amount', 'voucher_amount'],
        payloadKey: 'shipment_check_ratio',
      },
    ],
    metricRatioKeys: { receipt: 'repayment', shipment: 'mortgage' },
    calcTotal: calcBlockTotal,
    htmlData: props.htmlData,
  })

  // ─── 命名比例别名（L05 对通用 getRatio 的命名别名，emptyBase='zero' 保证非 null）──

  const getRepaymentRatio = (c: AlternativeCompany): number => core.getRatio(c, 'repayment') as number
  const getMortgageRatio = (c: AlternativeCompany): number => core.getRatio(c, 'mortgage') as number

  // ─── getBlockRows / getClosingBalance 导出（旁挂，逐字保留）────────────────

  const getBlockRows = core._getBlockRows
  const getClosingBalance = (c: AlternativeCompany): number => Number(c.balance?.closing_balance ?? 0)

  // ─── balanceSummary（L05 独有，逐字保留）──────────────────────────────────

  const balanceSummary = computed<AlternativeL05Summary>(() => {
    let opening = 0, debit = 0, credit = 0, closing = 0, currentLoan = 0
    for (const c of core.companies.value) {
      opening += Number(c.balance?.opening_balance ?? 0)
      debit += Number(c.balance?.debit_amount ?? 0)
      credit += Number(c.balance?.credit_amount ?? 0)
      closing += getClosingBalance(c)
      const block3Total = core.getBlockTotal(c, 'block3')
      currentLoan += block3Total.voucher_amount ?? 0
    }
    const avgRepayment = core.companies.value.length > 0
      ? core.companies.value.reduce((s, c) => s + getRepaymentRatio(c), 0) / core.companies.value.length
      : 0
    const avgMortgage = core.companies.value.length > 0
      ? core.companies.value.reduce((s, c) => s + getMortgageRatio(c), 0) / core.companies.value.length
      : 0
    return {
      investmentType: '长期应付款/借款',
      openingBalance: precise(opening),
      debitAmount: precise(debit),
      creditAmount: precise(credit),
      closingBalance: precise(closing),
      currentLoan: precise(currentLoan),
      repaymentCheckRatio: precise(avgRepayment),
      mortgageCheckRatio: precise(avgMortgage),
    }
  })

  // ─── importFromSummary（旁挂，逐字保留；内部调 core.importCompanies）───────

  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get(`/api/workpapers/${props.wpId}/l0/unreplied-entities`, {
        params: { sheet: 'L0-5' },
      })
      const entities: L01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
      if (!entities.length) return 0
      core.importCompanies(
        entities.map((e) => ({
          entity_name: e.entity_name,
          confirm_index: e.confirm_index,
          _source: 'auto',
          balance: { item_name: '长期应付款/借款', closing_balance: e.confirm_amount } as BalanceSummary,
        })),
      )
      return entities.length
    } catch {
      return 0
    } finally {
      loading.value = false
    }
  }

  // ─── loadAll / persistAll（旁挂，逐字保留）────────────────────────────────

  function loadAll() {
    core._initFromHtmlData(props.htmlData())
  }

  function persistAll(): AlternativeL05Payload {
    core.isDirty.value = false
    return core.buildPayload() as AlternativeL05Payload
  }

  return {
    companies: core.companies,
    isDirty: core.isDirty,
    selectedCompanyId: core.selectedCompanyId,
    loading,
    addCompany: core.addCompany,
    deleteCompany: core.deleteCompany,
    updateCompany: core.updateCompany,
    importCompanies: core.importCompanies,
    importFromSummary,
    addBlockRow: core.addBlockRow,
    deleteBlockRow: core.deleteBlockRow,
    updateBlockField: core.updateBlockField,
    getBlockRows,
    getBlockTotal: core.getBlockTotal,
    getClosingBalance,
    getRepaymentRatio,
    getMortgageRatio,
    getCompletionStatus: core.getCompletionStatus,
    hasAbnormal: core.hasAbnormal,
    metrics: core.metrics,
    balanceSummary,
    loadAll,
    persistAll,
    buildPayload: () => core.buildPayload() as AlternativeL05Payload,
  }
}

export default useAlternativeL05Data
