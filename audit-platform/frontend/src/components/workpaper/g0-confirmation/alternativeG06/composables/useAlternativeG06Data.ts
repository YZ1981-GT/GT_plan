/**
 * useAlternativeG06Data — G0-6 投资循环替代程序数据 composable
 *
 * confirmation-alternative-structure-alignment Task 4.1（G06 纳入工厂 + 区块对齐源三区）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的薄适配器——
 * 构造 G06 的 AltConfig + 调工厂 + 旁挂 G06 附加能力：
 *   - getCheckRatio（对通用 getRatio 的命名别名，type 'payment'|'inbound'）
 *   - updateBlockField 包装（block3 处置损益 disposal_gain / block4 股利差异 dividend_diff 公式重算）
 *   - migrateLegacyBlocks（旧四并列区块 → 源三区 + 源外增强 的一次性数据迁移）
 *   - getBlockTotalByDirection（借贷拆表小计，透传工厂）
 *
 * 区块结构（重构后，对齐源模板 G0-6）：
 *   block1 = ①初始投资协议检查
 *   block2 = ②本期发生额检查（借贷拆表）
 *   block3 = ③期后出售/赎回检查（复用 trade_amount/disposal_gain）
 *   block4 = ④源外增强（合并原持仓/股利/公允价值）
 *
 * 零回归约束：format = 'alternative-g06-v1'（不 bump），UseAlternativeG06DataReturn 原有签名不变，
 * buildPayload 返回 AlternativeG06Payload，balance 附 inbound_check_ratio/payment_check_ratio。
 *
 * 【数据零丢失红线】：migrateLegacyBlocks 仅以 block1 持仓字段 / block2 股利字段作为旧结构判据
 * （新结构 block1=investment_amount、block2=trade_amount 不含这些字段），**不**以 block4 的
 * quote_source/valuation_model 作触发条件——因新结构 block4 合法持有这些字段，若据此触发会误清空
 * 新公司的 block1/block2 数据。旧结构仅 block4（公允价值）有数据、block1/block2 空的公司无需迁移
 * （其 block4 数据在新结构下已正确，block1/block2 空保持不变）。
 */
import { watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../../confirmation/alternativeD05/alternativeD05Types'
import type { AlternativeG06Payload } from '../alternativeG06Types'
import { getSumFieldsG06 } from '../blockColumnConfigsG06'
import { calcDisposalGain, calcDividendDiff } from '../../composables/useG0FormulaEngine'
import { createAlternativeConfirmationData } from '../../../confirmation/coordination/createAlternativeConfirmationData'

function toNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 旧结构 block1 持仓字段（新结构 block1=初始投资协议，不含这些） */
const LEGACY_HOLDING_FIELDS = ['holding_variety', 'market_value', 'holding_qty', 'custody_confirm', 'stmt_date']
/** 旧结构 block2 股利字段（新结构 block2=本期发生额，不含这些） */
const LEGACY_DIVIDEND_FIELDS = ['dividend_receivable', 'dividend_per_share', 'received_amount', 'net_received', 'dividend_announce_date']

export interface UseAlternativeG06DataProps {
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeG06DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getBlockTotalByDirection: (company: AlternativeCompany, blockType: BlockType, direction: 'debit' | 'credit') => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: 'payment' | 'inbound') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  buildPayload: () => AlternativeG06Payload
  _getBlockRows: (company: AlternativeCompany, blockType: BlockType) => CheckRow[]
}

export function useAlternativeG06Data(props: UseAlternativeG06DataProps): UseAlternativeG06DataReturn {
  const core = createAlternativeConfirmationData({
    format: 'alternative-g06-v1',
    getSumFields: getSumFieldsG06,
    defaultBalance: () => ({ item_name: '交易性金融资产', investment_type: '交易性金融资产' }),
    baseAmount: (c: AlternativeCompany) =>
      Number(c.balance?.closing_balance ?? c.balance?.sales_amount ?? 0),
    // 两条命名比例——重构后持仓(market_value)/股利(received_amount/dividend_receivable)均迁至 block4，
    // 故两条 ratio 的 block 都指向 block4 以保持比例语义
    ratios: [
      { key: 'inbound', block: 'block4', fields: ['market_value', 'voucher_amount'], payloadKey: 'inbound_check_ratio' },
      { key: 'payment', block: 'block4', fields: ['received_amount', 'dividend_receivable'], payloadKey: 'payment_check_ratio' },
    ],
    emptyBase: 'null',
    metricRatioKeys: { receipt: 'payment', shipment: 'inbound' },
    htmlData: props.htmlData,
  })

  // ─── 一次性旧结构数据迁移（旧四并列区块 → 源三区 + 源外增强） ─────────────

  function migrateLegacyBlocks() {
    for (const company of core.companies.value) {
      if ((company as any)._g06_migrated) continue

      const block1Rows = (company.block1_rows || []) as CheckRow[]
      const block2Rows = (company.block2_rows || []) as CheckRow[]

      const hasLegacyHolding = block1Rows.some((r) =>
        LEGACY_HOLDING_FIELDS.some((f) => r[f] != null && r[f] !== ''),
      )
      const hasLegacyDividend = block2Rows.some((r) =>
        LEGACY_DIVIDEND_FIELDS.some((f) => r[f] != null && r[f] !== ''),
      )

      // 无旧结构数据 → 无需迁移（block4 若已有公允价值数据，在新结构下本就正确）
      if (!hasLegacyHolding && !hasLegacyDividend) continue

      const block4Rows = (company.block4_rows || []) as CheckRow[]
      // 旧 block1（持仓）+ 旧 block2（股利）追加到 block4（源外增强），旧 block4（公允价值）保留在前
      company.block4_rows = [...block4Rows, ...block1Rows, ...block2Rows]
      // 旧 block3（处置）原地保留（处置≈期后出售赎回，trade_amount/disposal_gain 复用）
      // 清空 block1、block2（数据已搬 block4）
      company.block1_rows = []
      company.block2_rows = []
      ;(company as any)._g06_migrated = true
    }
  }

  // ─── block2 `support_doc` 单列 → 支持性文件1「识别特征」（g0 spec R7.5 / Task 16）──
  //
  // 重构前 block2 把源模板「支持性文件1/2」各 3 列压成一个 `support_doc` 文本列。
  // 拆列后旧值必须有落点，否则既有底稿的支持性证据文字消失（数据零丢失红线）。
  //
  // 🔴 幂等：只在「有 support_doc 且 support1_feature 为空」时搬；`support_doc`
  //    **不删**（保留原值，供导入导出与回溯），故重复执行不会二次覆盖已填的新字段。

  function migrateSupportDoc() {
    for (const company of core.companies.value) {
      for (const row of (company.block2_rows || []) as CheckRow[]) {
        const legacy = row.support_doc
        if (legacy == null || legacy === '') continue
        if (row.support1_feature != null && row.support1_feature !== '') continue
        row.support1_feature = legacy
      }
    }
  }

  // 工厂已在构造时 initFromHtmlData 同步填充 companies；watch 覆盖 init + 后续 htmlData 变更。
  // 迁移靠 _g06_migrated 标记保证只迁一次（幂等）；support_doc 迁移自身幂等（见函数注释）。
  watch(
    core.companies,
    () => {
      migrateLegacyBlocks()
      migrateSupportDoc()
    },
    { immediate: true },
  )

  // ─── updateBlockField 包装：block3/block4 公式重算 ────────────────────────

  function updateBlockField(companyId: string, blockType: BlockType, rowId: string, field: string, value: any) {
    core.updateBlockField(companyId, blockType, rowId, field, value)
    if (blockType !== 'block3' && blockType !== 'block4') return
    const company = core.companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    const row = core._getBlockRows(company, blockType).find((r) => r._row_id === rowId)
    if (!row) return
    if (blockType === 'block3') {
      // 处置损益 = 成交金额 - 原始成本 - 手续费
      row.disposal_gain = calcDisposalGain(toNum(row.trade_amount), toNum(row.original_cost), toNum(row.fee))
    } else {
      // 股利差异 = 应收股利 - 实收金额 - 红利税（股利已迁至 block4）
      row.dividend_diff = calcDividendDiff(toNum(row.dividend_receivable), toNum(row.net_received), toNum(row.dividend_tax))
    }
  }

  // ─── getCheckRatio 命名别名（type 'payment'|'inbound' → 通用 getRatio） ────

  function getCheckRatio(company: AlternativeCompany, type: 'payment' | 'inbound'): number | null {
    return core.getRatio(company, type)
  }

  return {
    ...core,
    updateBlockField,
    getCheckRatio,
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeG06Payload
    buildPayload: () => core.buildPayload() as AlternativeG06Payload,
  }
}
