/** H10 资产处置损益 — 常量（与 xlsx H10 资产处置损益.xlsx 一致） */
import { H10_ADJUDICATION_ITEMS, type H10AdjudicationLineDef } from './h10AdjudicationItems'

export { H10_ADJUDICATION_ITEMS, type H10AdjudicationLineDef }

export const H10_ACCOUNT_CODE = '6115'
export const H10_CHANGE_RATE_THRESHOLD = 0.2

/** H10-3 调整分录回写目标行 */
export const H10_ADJ_WRITEBACK_ROW_KEY = 'fixed_asset_disposal'

/**
 * 明细表来源底稿下拉
 * GT 编码：H8=使用权资产、I1=无形资产；6115 不含投房(H3)/金融工具/长投
 * DR/NM 从 OTHER 拆出，便于汇总至债务重组/非货币审定行
 */
export const SOURCE_WP_OPTIONS = [
  { value: 'H1', label: 'H1 固定资产', indexHint: 'H1-8' },
  { value: 'H2', label: 'H2 在建工程', indexHint: 'H2-5' },
  { value: 'H5', label: 'H5 油气资产', indexHint: 'H5-8' },
  { value: 'H6', label: 'H6 固定资产清理', indexHint: 'H6-2' },
  { value: 'H7', label: 'H7 生产性生物资产', indexHint: 'H7-7' },
  { value: 'H8', label: 'H8 使用权资产', indexHint: 'H8-12' },
  { value: 'I1', label: 'I1 无形资产', indexHint: 'I1-8' },
  { value: 'DR', label: '债务重组（非流动资产）', indexHint: '' },
  { value: 'NM', label: '非货币性资产交换', indexHint: '' },
  { value: 'OTHER', label: '其他', indexHint: '' },
] as const

export type H10SourceWp = (typeof SOURCE_WP_OPTIONS)[number]['value']

/** 附注披露（上市）— 与 H10-1 行一一对应（含试运行） */
export const H10_DISCLOSURE_LISTED_ROWS: H10AdjudicationLineDef[] = H10_ADJUDICATION_ITEMS.map((d) =>
  d.rowKey === 'trial_operation_sales'
    ? { rowKey: d.rowKey, label: '试运行销售损益' }
    : d,
)

/** 附注披露（国企）— 短标签 + 非经常性列 */
export const H10_DISCLOSURE_SOE_ROWS: H10AdjudicationLineDef[] = H10_ADJUDICATION_ITEMS.map((d) => ({
  rowKey: d.rowKey,
  label: d.rowKey === 'trial_operation_sales'
    ? '试运行销售损益'
    : d.label.replace(/（损失以"-"填列）$/, ''),
}))

/** 上市 — 试运行销售明细（收入/成本，对齐 xlsx 明细表 + 解释第15号） */
export const H10_TRIAL_DETAIL_ROWS: H10AdjudicationLineDef[] = [
  { rowKey: 'fixed_asset_trial', label: '固定资产试运行销售' },
  { rowKey: 'rd_sample_sales', label: '研发样品销售' },
]

/** 旧版披露「其中」子行 → 主行映射（加载时迁移，防丢数） */
export const H10_DISCLOSURE_LEGACY_KEY_MAP: Record<string, string> = {
  listed_sub_dr: 'debt_restructuring_disposal',
  listed_sub_nm: 'non_monetary_exchange',
  soe_sub_dr: 'debt_restructuring_disposal',
}

export const H10_COMPLIANCE_OPTIONS = [
  { value: 'compliant', label: '合规' },
  { value: 'non_compliant', label: '不合规' },
  { value: 'not_applicable', label: '不适用' },
] as const

export type H10ImportableSheet = 'H10-2' | 'H10-3'

export const H10_IMPORTABLE_SHEETS: { code: H10ImportableSheet; label: string }[] = [
  { code: 'H10-2', label: 'H10-2 明细表' },
  { code: 'H10-3', label: 'H10-3 调整分录' },
]

export const H10_API_PREFIX = 'h10'
