/**
 * useAlternativeData — D0-5 合同负债及销售替代程序数据核心 composable
 *
 * confirmation-alternative-factory-convergence Task 5（D05 试点迁移）：
 * 本 composable 已迁移为 Shared_Core 工厂 `createAlternativeConfirmationData` 的
 * 薄适配器——构造 D05 的 AltConfig + 调工厂 + 组装原返回签名。
 *
 * 零回归约束：导出名 `useAlternativeData`、props 签名 `{htmlData, readonly}`、
 * 返回对象形状与类型（`UseAlternativeDataReturn`，buildPayload 返回
 * `AlternativeD05Payload`）逐字不变；D05 现有 spec 不改任何断言必须全绿。
 *
 * 职责（经工厂承载）：
 * - 从 htmlData 初始化 companies + watch 重建 + dirty
 * - companies CRUD（add/delete/update/import）
 * - 各区块合计（精确小数）+ 检查比例自动计算
 * - completionStatus（4 区块有记录占比）+ hasAbnormal
 * - buildPayload（_format: alternative-d05-v1）
 *
 * D05 差异（经 AltConfig 声明）：
 * - defaultBalance = () => ({})（D05 默认 balance 为空对象）
 * - baseAmount = c.balance?.sales_amount（本期销售额，缺失/0 → emptyBase='null'）
 * - ratios：block3 收款金额 → receipt_check_ratio；block4 出库金额 → shipment_check_ratio
 */
import { type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  AlternativeD05Payload,
  CheckRow,
  BlockType,
} from '../alternativeD05Types'
import { getSumFields } from '../blockColumnConfigs'
import { createAlternativeConfirmationData } from '../../coordination/createAlternativeConfirmationData'

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseAlternativeDataProps {
  htmlData: () => any
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseAlternativeDataReturn {
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
  buildPayload: () => AlternativeD05Payload
}

// ─── Composable 主体（工厂适配器） ───────────────────────────────────────────

export function useAlternativeData(props: UseAlternativeDataProps): UseAlternativeDataReturn {
  const core = createAlternativeConfirmationData({
    format: 'alternative-d05-v1',
    getSumFields,
    // D05 默认 balance 是空对象
    defaultBalance: () => ({}),
    // 比例分母基数：本期销售额（缺失/0 → emptyBase='null' 交给工厂处理）
    baseAmount: (c: AlternativeCompany) => Number(c.balance?.sales_amount ?? 0),
    ratios: [
      { key: 'receipt', block: 'block3', fields: ['receipt_amount'], payloadKey: 'receipt_check_ratio' },
      { key: 'shipment', block: 'block4', fields: ['product_amount'], payloadKey: 'shipment_check_ratio' },
    ],
    emptyBase: 'null',
    metricRatioKeys: { receipt: 'receipt', shipment: 'shipment' },
    htmlData: props.htmlData,
  })

  return {
    ...core,
    // getCheckRatio 是 D05 对通用 getRatio 的命名别名（type 'receipt'|'shipment'）
    getCheckRatio: (c: AlternativeCompany, type: 'receipt' | 'shipment') => core.getRatio(c, type),
    // 工厂 buildPayload 返回 {_format:string,...}，收窄为 AlternativeD05Payload
    buildPayload: () => core.buildPayload() as AlternativeD05Payload,
  }
}
