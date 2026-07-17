/**
 * useAlternativeF05Data — F0-5 预付及采购替代程序数据核心 composable
 *
 * confirmation-alternative-factory-convergence Task 7（F05 迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 F05 的 AltConfig + 调工厂 + 组装原返回签名。
 *
 * 零回归约束：导出名 `useAlternativeF05Data`、props 签名 `{htmlData, readonly}`、
 * 返回对象形状与类型（`UseAlternativeF05DataReturn`，buildPayload 返回
 * `AlternativeF05Payload`）逐字不变；F05 现有 characterization spec 不改任何
 * 断言必须全绿。
 *
 * F05 差异（经 AltConfig 声明）：
 * - format = 'alternative-f05-v1'
 * - getSumFields = getSumFieldsF05
 * - defaultBalance = () => ({ item_name: '预付账款' })
 * - baseAmount = c.balance?.purchase_amount ?? c.balance?.sales_amount ?? 0
 * - ratios：block3 付款金额（payment_amount ?? bank_amount）→ payment_check_ratio；
 *           block4 入库证据金额（voucher_amount ?? invoice_amount）→ inbound_check_ratio
 * - metricRatioKeys：metrics.receipt_ratio←payment、shipment_ratio←inbound
 */
import { type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../alternativeD05/alternativeD05Types'
import type { AlternativeF05Payload } from '../alternativeF05Types'
import { getSumFieldsF05 } from '../blockColumnConfigsF05'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'

export interface UseAlternativeF05DataProps {
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeF05DataReturn {
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
  buildPayload: () => AlternativeF05Payload
}

export function useAlternativeF05Data(props: UseAlternativeF05DataProps): UseAlternativeF05DataReturn {
  const core = createAlternativeConfirmationData({
    format: 'alternative-f05-v1',
    getSumFields: getSumFieldsF05,
    // F05 默认 balance 带 item_name='预付账款'
    defaultBalance: () => ({ item_name: '预付账款' }),
    // 比例分母基数：采购额（缺失回退销售额，再缺失/0 → emptyBase='null' 交给工厂处理）
    baseAmount: (c: AlternativeCompany) =>
      Number(c.balance?.purchase_amount ?? c.balance?.sales_amount ?? 0),
    ratios: [
      { key: 'payment', block: 'block3', fields: ['payment_amount', 'bank_amount'], payloadKey: 'payment_check_ratio' },
      { key: 'inbound', block: 'block4', fields: ['voucher_amount', 'invoice_amount'], payloadKey: 'inbound_check_ratio' },
    ],
    emptyBase: 'null',
    // metrics receipt_ratio←payment、shipment_ratio←inbound
    metricRatioKeys: { receipt: 'payment', shipment: 'inbound' },
    htmlData: props.htmlData,
  })

  return {
    ...core,
    // getCheckRatio 是 F05 对通用 getRatio 的命名别名（type 'payment'|'inbound'）
    getCheckRatio: (c: AlternativeCompany, type: 'payment' | 'inbound') => core.getRatio(c, type),
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeF05Payload
    buildPayload: () => core.buildPayload() as AlternativeF05Payload,
  }
}
