/**
 * useAlternativeD06Data — D0-6 应收及销售替代程序数据核心 composable
 *
 * confirmation-alternative-factory-convergence Task 6（D06 迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 D06 的 AltConfig + 调工厂 + 组装原返回签名。
 *
 * 零回归约束：导出名 `useAlternativeD06Data`、props 签名 `{htmlData, readonly}`、
 * 返回对象形状与类型（`UseAlternativeD06DataReturn`，buildPayload 返回
 * `AlternativeD06Payload`）逐字不变；D06 现有 spec 不改任何断言必须全绿。
 *
 * 职责（经工厂承载）：
 * - 从 htmlData 初始化 companies + watch 重建 + dirty
 * - companies CRUD（add/delete/update/import）
 * - 各区块合计（精确小数，使用 D06 列配置）+ 检查比例自动计算
 * - completionStatus（4 区块有记录占比）+ hasAbnormal
 * - buildPayload（_format: alternative-d06-v1）
 *
 * D06 差异（经 AltConfig 声明，注意 block 与 D05 相反）：
 * - getSumFields = getSumFieldsD06（D06 专属列配置）
 * - defaultBalance = () => ({})（D06 默认 balance 为空对象）
 * - baseAmount = c.balance?.sales_amount（本期销售额，缺失/0 → emptyBase='null'）
 * - ratios：block4 收款金额 → receipt_check_ratio；block3 出库金额 → shipment_check_ratio
 *   （receipt 用 block4、shipment 用 block3，与 D05 相反）
 */
import { type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import type { AlternativeD06Payload } from '../alternativeD06Types'
import { getSumFieldsD06 } from '../blockColumnConfigsD06'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseAlternativeD06DataProps {
  htmlData: () => any
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseAlternativeD06DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>

  // CRUD
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void

  // 区块行操作
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void

  // 计算
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: 'receipt' | 'shipment') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean

  // 看板
  metrics: ComputedRef<AlternativeD05Metrics>

  // 持久化
  buildPayload: () => AlternativeD06Payload
}

// ─── Composable 主体（工厂适配器） ───────────────────────────────────────────

export function useAlternativeD06Data(props: UseAlternativeD06DataProps): UseAlternativeD06DataReturn {
  const core = createAlternativeConfirmationData({
    format: 'alternative-d06-v1',
    getSumFields: getSumFieldsD06,
    // D06 默认 balance 是空对象
    defaultBalance: () => ({}),
    // 比例分母基数：本期销售额（缺失/0 → emptyBase='null' 交给工厂处理）
    baseAmount: (c: AlternativeCompany) => Number(c.balance?.sales_amount ?? 0),
    // 注意 block 与 D05 相反：receipt 用 block4、shipment 用 block3
    ratios: [
      { key: 'receipt', block: 'block4', fields: ['receipt_amount'], payloadKey: 'receipt_check_ratio' },
      { key: 'shipment', block: 'block3', fields: ['product_amount'], payloadKey: 'shipment_check_ratio' },
    ],
    emptyBase: 'null',
    metricRatioKeys: { receipt: 'receipt', shipment: 'shipment' },
    htmlData: props.htmlData,
  })

  return {
    ...core,
    // getCheckRatio 是 D06 对通用 getRatio 的命名别名（type 'receipt'|'shipment'）
    getCheckRatio: (c: AlternativeCompany, type: 'receipt' | 'shipment') => core.getRatio(c, type),
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeD06Payload
    buildPayload: () => core.buildPayload() as AlternativeD06Payload,
  }
}
