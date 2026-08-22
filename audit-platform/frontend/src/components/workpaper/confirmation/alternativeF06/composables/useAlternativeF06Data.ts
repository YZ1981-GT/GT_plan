/**
 * useAlternativeF06Data — F0-6 应付及采购替代程序数据核心 composable
 *
 * confirmation-alternative-factory-convergence Task 8（F06 迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 F06 的 AltConfig + 调工厂 + 组装原返回签名。
 *
 * 零回归约束：导出名 `useAlternativeF06Data`、props 签名 `{htmlData, readonly}`、
 * 返回对象形状与类型（`UseAlternativeF06DataReturn`，buildPayload 返回
 * `AlternativeF06Payload`）逐字不变；F06 现有 characterization spec 不改任何断言必须全绿。
 *
 * F06 差异（经 AltConfig 声明，注意 block 与 F05 相反）：
 * - defaultBalance = () => ({ item_name: '应付账款' })
 * - baseAmount = c.balance?.purchase_amount ?? c.balance?.sales_amount（缺失/0 → emptyBase='null'）
 * - ratios：inbound 用 block3 记账凭证/发票金额 → inbound_check_ratio；
 *   payment 用 block4 付款/银行金额 → payment_check_ratio（block 映射与 F05 相反）
 * - metrics：receipt_ratio←payment、shipment_ratio←inbound（metricRatioKeys 声明）
 */
import { type Ref, type ComputedRef } from 'vue'
// alternativeD05 是 confirmation 的**同级兄弟目录**，而本文件在
// confirmation/alternativeF06/composables/ ⇒ 要上两级（'../../'）。
// 下面 '../alternativeF06Types' 只上一级是对的，两者深度不同，别照抄。
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import type { AlternativeF06Payload } from '../alternativeF06Types'
import { getSumFieldsF06 } from '../blockColumnConfigsF06'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseAlternativeF06DataProps {
  htmlData: () => any
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseAlternativeF06DataReturn {
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
  getCheckRatio: (company: AlternativeCompany, type: 'payment' | 'inbound') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  buildPayload: () => AlternativeF06Payload
}

// ─── Composable 主体（工厂适配器） ───────────────────────────────────────────

export function useAlternativeF06Data(props: UseAlternativeF06DataProps): UseAlternativeF06DataReturn {
  const core = createAlternativeConfirmationData({
    format: 'alternative-f06-v1',
    getSumFields: getSumFieldsF06,
    // F06 默认 balance.item_name = '应付账款'
    defaultBalance: () => ({ item_name: '应付账款' }),
    // 比例分母基数：本期采购额（回退销售额；缺失/0 → emptyBase='null' 交给工厂处理）
    baseAmount: (c: AlternativeCompany) =>
      Number(c.balance?.purchase_amount ?? c.balance?.sales_amount ?? 0),
    // 注意 block 映射与 F05 相反：inbound 用 block3、payment 用 block4
    ratios: [
      { key: 'inbound', block: 'block3', fields: ['voucher_amount', 'invoice_amount'], payloadKey: 'inbound_check_ratio' },
      { key: 'payment', block: 'block4', fields: ['payment_amount', 'bank_amount'], payloadKey: 'payment_check_ratio' },
    ],
    emptyBase: 'null',
    // metrics receipt_ratio←payment、shipment_ratio←inbound
    metricRatioKeys: { receipt: 'payment', shipment: 'inbound' },
    htmlData: props.htmlData,
  })

  return {
    ...core,
    // getCheckRatio 是 F06 对通用 getRatio 的命名别名（type 'payment'|'inbound'）
    getCheckRatio: (c: AlternativeCompany, type: 'payment' | 'inbound') => core.getRatio(c, type),
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeF06Payload
    buildPayload: () => core.buildPayload() as AlternativeF06Payload,
  }
}
