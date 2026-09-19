/**
 * useAlternativeK05Data — K0-5 其他应收款替代程序数据 composable
 *
 * confirmation-alternative-factory-convergence Task 10（K05 迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 K05 的 AltConfig + 调工厂 + 旁挂 K05 附加能力
 * （loading / importFromSummary / loadAll / persistAll / balanceSummary / getReconcileDiff）。
 *
 * 零回归约束：default export、两种构造重载签名 `(wpId, projectId)` 与 `(props)`、
 * 返回对象形状与类型（`UseAlternativeK05DataReturn`，buildPayload 返回
 * `AlternativeK05Payload`）、导出 `getSumFieldsK05` 逐字不变；K05 现有 characterization
 * spec 不改任何断言必须全绿。
 *
 * Master-Detail（公司→4 区块检查表）
 * 4区块：
 *   ① 期后收款检查
 *   ② 期末余额支持性证据
 *   ③ 本期发生额检查（借方+贷方合并）
 *   ④ 往来对账/协议证据
 *
 * K05 差异（经 AltConfig 声明）：
 * - format = 'alternative-k05-v1'
 * - getSumFields = getSumFieldsK05（本文件内 SUM_FIELDS 定义 + 导出函数，逐字保留）
 * - defaultBalance = () => ({ item_name: '其他应收款' })
 * - baseAmount = parseNum(c.balance?.closing_balance ?? 0)（期末余额）
 * - ratios：block1 post_receipt（receipt_amount）→ receipt_check_ratio；
 *           block4 reconcile（self_balance）→ reconcile_check_ratio
 * - metricRatioKeys：metrics.receipt_ratio←post_receipt、shipment_ratio←reconcile
 * - calcTotal/calcRatio/parseNum 注入 useK0FormulaEngine 的
 *   calcBlockTotal/calcCheckRatio/parseNum（保证与原实现逐字等价，含 balance≤0→0 语义）
 *
 * K05 附加能力（适配器旁挂，不进工厂）：
 * - loading ref、importFromSummary（K0-1 未回函带入，逐字保留原实现）、loadAll、persistAll、
 *   balanceSummary（closingBalance=opening+debit-credit）、getReconcileDiff
 *
 * Requirements: 2.1~2.10, 4.1
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import {
  calcBlockTotal,
  calcCheckRatio,
  calcReconcileDiff,
  parseNum,
} from './useK0FormulaEngine'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface AlternativeK05Payload {
  _format: 'alternative-k05-v1'
  companies: AlternativeCompany[]
}

export interface K01UnrepliedEntity {
  /** 被询证单位名称 */
  entity_name: string
  /** 函证索引号 */
  confirm_index?: string
  /** 函证金额 */
  confirm_amount?: number
  /** 未回函原因 */
  unreplied_reason?: string
}

export interface AlternativeK05Summary {
  /** 函证项目（其他应收款） */
  investmentType: string
  /** 年初余额 */
  openingBalance: number
  /** 借方发生额 */
  debitAmount: number
  /** 贷方发生额 */
  creditAmount: number
  /** 期末余额 = 年初 + 借方 - 贷方 */
  closingBalance: number
  /** 本期发生额 */
  currentAmount: number
  /** 期后收款检查比例 */
  postCheckRatio: number
  /** 往来对账比例 */
  reconcileRatio: number
}

export interface UseAlternativeK05DataProps {
  wpId: string
  projectId: string
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeK05DataReturn {
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
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: 'post_receipt' | 'reconcile') => number | null
  getReconcileDiff: (row: CheckRow) => number
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  balanceSummary: ComputedRef<AlternativeK05Summary>
  loadAll: () => void
  persistAll: () => AlternativeK05Payload
  buildPayload: () => AlternativeK05Payload
}

// ─── 4 区块列配置（Sum字段定义）───────────────────────────────────────────────

/** 各区块需要合计的数值字段 */
const SUM_FIELDS: Record<string, string[]> = {
  block1: ['voucher_amount', 'receipt_amount'],
  block2: ['voucher_amount', 'agreement_amount'],
  block3: ['voucher_amount', 'approval_amount'],
  block4: ['voucher_amount', 'other_balance', 'self_balance'],
}

export function getSumFieldsK05(blockType: string): string[] {
  return SUM_FIELDS[blockType] || []
}

/** 精确小数（避免浮点漂移，balanceSummary 旁挂复用） */
function precise(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Composable（工厂适配器） ────────────────────────────────────────────────

export default function useAlternativeK05Data(wpId: string, projectId: string): UseAlternativeK05DataReturn
export default function useAlternativeK05Data(props: UseAlternativeK05DataProps): UseAlternativeK05DataReturn
export default function useAlternativeK05Data(
  wpIdOrProps: string | UseAlternativeK05DataProps,
  projectId?: string,
): UseAlternativeK05DataReturn {
  // Normalize props（构造重载归一，逐字保留原实现）
  const props: UseAlternativeK05DataProps =
    typeof wpIdOrProps === 'string'
      ? { wpId: wpIdOrProps, projectId: projectId!, htmlData: () => null, readonly: false }
      : wpIdOrProps

  const core = createAlternativeConfirmationData({
    format: 'alternative-k05-v1',
    getSumFields: getSumFieldsK05,
    // K05 默认 balance 带 item_name='其他应收款'
    defaultBalance: () => ({ item_name: '其他应收款' }),
    // 比例分母基数：期末余额（closing_balance 缺失/0 → emptyBase='null'）
    baseAmount: (c: AlternativeCompany) => parseNum(c.balance?.closing_balance ?? 0),
    ratios: [
      { key: 'post_receipt', block: 'block1', fields: ['receipt_amount'], payloadKey: 'receipt_check_ratio' },
      { key: 'reconcile', block: 'block4', fields: ['self_balance'], payloadKey: 'reconcile_check_ratio' },
    ],
    emptyBase: 'null',
    // metrics receipt_ratio←post_receipt、shipment_ratio←reconcile
    metricRatioKeys: { receipt: 'post_receipt', shipment: 'reconcile' },
    // 注入 useK0FormulaEngine 纯函数，保证与原实现逐字等价
    calcTotal: calcBlockTotal,
    calcRatio: calcCheckRatio,
    parseNum,
    htmlData: props.htmlData,
  })

  // ─── K05 附加能力（旁挂，不进工厂） ───────────────────────────────────────

  const loading = ref(false)

  function loadAll() {
    core._initFromHtmlData(props.htmlData())
  }

  function persistAll(): AlternativeK05Payload {
    return core.buildPayload() as AlternativeK05Payload
  }

  /**
   * getCheckRatio 是 K05 对通用 getRatio 的命名别名（type 'post_receipt'|'reconcile'）
   * - post_receipt: 区块①期后收款合计(receipt_amount) / 期末余额
   * - reconcile: 区块④对账覆盖合计(self_balance) / 期末余额
   */
  function getCheckRatio(company: AlternativeCompany, type: 'post_receipt' | 'reconcile'): number | null {
    return core.getRatio(company, type)
  }

  /**
   * 计算对账差异（区块④每行：本方余额 - 对方余额）
   * 逐字保留原实现。
   */
  function getReconcileDiff(row: CheckRow): number {
    return calcReconcileDiff(parseNum(row.self_balance), parseNum(row.other_balance))
  }

  /**
   * 从 K0-1 函证汇总表带入未回函公司（反向联动，对标 D0-1→D0-5 模式）
   * 调用后端 API 获取 K0-1 未回函列表，按 confirm_index 去重后插入
   * @returns 新增公司数量
   *
   * 逐字保留原实现：直接 push 带 closing_balance 的公司（core.importCompanies
   * 不带 closing_balance 语义，故此处保留原内联 push + core._generateId 以零回归）。
   */
  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get<K01UnrepliedEntity[]>(
        `/api/workpapers/${props.wpId}/k0/unreplied-entities`,
        { params: { sheet: 'K0-5' } },
      )
      const entities: K01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
      if (!entities.length) return 0

      const existingIndexes = new Set(
        core.companies.value.map((c) => c.confirm_index).filter(Boolean),
      )
      const newItems = entities.filter(
        (e) => !e.confirm_index || !existingIndexes.has(e.confirm_index),
      )
      if (!newItems.length) return 0

      const maxSeq = core.companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
      newItems.forEach((item, i) => {
        core.companies.value.push({
          _company_id: core._generateId(),
          seq: maxSeq + i + 1,
          entity_name: item.entity_name || '',
          confirm_index: item.confirm_index,
          _source: 'auto',
          sampling: {},
          balance: {
            item_name: '其他应收款',
            closing_balance: item.confirm_amount ?? 0,
          },
          block1_rows: [],
          block2_rows: [],
          block3_rows: [],
          block4_rows: [],
          conclusion: {},
        })
      })
      core.isDirty.value = true
      return newItems.length
    } finally {
      loading.value = false
    }
  }

  // ─── Balance Summary (余额汇总区 computed，K05 独有，逐字保留原实现) ──────

  const balanceSummary = computed<AlternativeK05Summary>(() => {
    // 汇总所有公司余额
    let openingBalance = 0
    let debitAmount = 0
    let creditAmount = 0
    let postReceiptTotal = 0
    let reconcileTotal = 0

    for (const company of core.companies.value) {
      openingBalance += parseNum(company.balance?.opening_balance)
      debitAmount += parseNum(company.balance?.debit_amount)
      creditAmount += parseNum(company.balance?.credit_amount)
      // 期后收款合计（block1 receipt_amount）
      const b1Totals = core.getBlockTotal(company, 'block1')
      postReceiptTotal += b1Totals.receipt_amount ?? 0
      // 往来对账合计（block4 self_balance）
      const b4Totals = core.getBlockTotal(company, 'block4')
      reconcileTotal += b4Totals.self_balance ?? 0
    }

    const closingBalance = precise(openingBalance + debitAmount - creditAmount)
    const currentAmount = precise(debitAmount + creditAmount)
    const postCheckRatio = closingBalance > 0 ? precise(calcCheckRatio(postReceiptTotal, closingBalance) * 100) : 0
    const reconcileRatio = closingBalance > 0 ? precise(calcCheckRatio(reconcileTotal, closingBalance) * 100) : 0

    return {
      investmentType: '其他应收款',
      openingBalance: precise(openingBalance),
      debitAmount: precise(debitAmount),
      creditAmount: precise(creditAmount),
      closingBalance,
      currentAmount,
      postCheckRatio,
      reconcileRatio,
    }
  })

  return {
    ...core,
    loading,
    getCheckRatio,
    getReconcileDiff,
    balanceSummary,
    importFromSummary,
    loadAll,
    persistAll,
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeK05Payload
    buildPayload: () => core.buildPayload() as AlternativeK05Payload,
  }
}
