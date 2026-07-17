/**
 * useAlternativeH05Data — H0-5 固定资产循环替代程序数据 composable
 *
 * confirmation-alternative-factory-convergence Task 9（H05 迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 H05 的 AltConfig + 调工厂 + 旁挂 H05 附加能力
 * （loading / importFromSummary / loadAll / persistAll）。
 *
 * 零回归约束：导出名 `useAlternativeH05Data`、props 签名 `{wpId, projectId, htmlData,
 * readonly}`、返回对象形状与类型（`UseAlternativeH05DataReturn`，buildPayload 返回
 * `AlternativeH05Payload`）逐字不变；H05 现有 characterization spec 不改任何断言必须全绿。
 *
 * H05 差异（经 AltConfig 声明）：
 * - format = 'alternative-h05-v1'
 * - getSumFields = getSumFieldsH05
 * - defaultBalance = () => ({ item_name: '固定资产' })
 * - baseAmount = parseNum(c.balance?.closing_balance ?? c.balance?.ending_balance ?? 0)（期末余额）
 * - ratios：block2 ownership（contract_amount ?? invoice_amount ?? payment_amount）→ ownership_check_ratio；
 *           block1 acceptance（voucher_amount）→ post_acceptance_ratio
 * - metricRatioKeys：metrics.receipt_ratio←acceptance、shipment_ratio←ownership
 * - calcTotal/calcRatio/parseNum 注入 useH0FormulaEngine 的
 *   calcBlockTotal/calcCheckRatio/parseNum（保证与原实现逐字等价，含 Infinity→0 语义）
 *
 * H05 附加能力（适配器旁挂，不进工厂）：
 * - loading ref、importFromSummary（H0-1 未回函带入，逐字保留原实现）、loadAll、persistAll
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import type { AlternativeH05Payload, H01UnrepliedEntity } from '../alternativeH05Types'
import { getSumFieldsH05 } from '../blockColumnConfigsH05'
import { calcCheckRatio, calcBlockTotal, parseNum } from './useH0FormulaEngine'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'
import http from '@/utils/http'

export interface UseAlternativeH05DataProps {
  wpId: string
  projectId: string
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeH05DataReturn {
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
  getCheckRatio: (company: AlternativeCompany, type: 'ownership' | 'acceptance') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  loadAll: () => void
  persistAll: () => AlternativeH05Payload
  buildPayload: () => AlternativeH05Payload
}

export function useAlternativeH05Data(props: UseAlternativeH05DataProps): UseAlternativeH05DataReturn {
  const core = createAlternativeConfirmationData({
    format: 'alternative-h05-v1',
    getSumFields: getSumFieldsH05,
    // H05 默认 balance 带 item_name='固定资产'
    defaultBalance: () => ({ item_name: '固定资产' }),
    // 比例分母基数：期末余额（closing_balance 缺失回退 ending_balance，再缺失/0 → emptyBase='null'）
    baseAmount: (c: AlternativeCompany) =>
      parseNum(c.balance?.closing_balance ?? c.balance?.ending_balance ?? 0),
    ratios: [
      { key: 'ownership', block: 'block2', fields: ['contract_amount', 'invoice_amount', 'payment_amount'], payloadKey: 'ownership_check_ratio' },
      { key: 'acceptance', block: 'block1', fields: ['voucher_amount'], payloadKey: 'post_acceptance_ratio' },
    ],
    emptyBase: 'null',
    // metrics receipt_ratio←acceptance、shipment_ratio←ownership
    metricRatioKeys: { receipt: 'acceptance', shipment: 'ownership' },
    // 注入 useH0FormulaEngine 纯函数，保证与原实现逐字等价
    calcTotal: calcBlockTotal,
    calcRatio: calcCheckRatio,
    parseNum,
    htmlData: props.htmlData,
  })

  // ─── H05 附加能力（旁挂，不进工厂） ───────────────────────────────────────

  const loading = ref(false)

  function loadAll() {
    core._initFromHtmlData(props.htmlData())
  }

  function persistAll(): AlternativeH05Payload {
    return core.buildPayload() as AlternativeH05Payload
  }

  /**
   * 从 H0-1 函证汇总表带入未回函公司（对标 D0-1→D0-5 模式）
   * 调用后端 API 获取 H0-1 未回函列表，按 confirm_index 去重后插入
   * @returns 新增公司数量
   *
   * 逐字保留原实现：直接 push 带 closing_balance 的公司（core.importCompanies
   * 不带 closing_balance 语义，故此处保留原内联 push + core._generateId 以零回归）。
   */
  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get<H01UnrepliedEntity[]>(
        `/api/workpapers/${props.wpId}/h0/unreplied-entities`,
        { params: { sheet: 'H0-5' } },
      )
      const entities: H01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
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
            item_name: '固定资产',
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

  return {
    ...core,
    loading,
    // getCheckRatio 是 H05 对通用 getRatio 的命名别名（type 'ownership'|'acceptance'）
    getCheckRatio: (c: AlternativeCompany, type: 'ownership' | 'acceptance') => core.getRatio(c, type),
    importFromSummary,
    loadAll,
    persistAll,
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeH05Payload
    buildPayload: () => core.buildPayload() as AlternativeH05Payload,
  }
}
