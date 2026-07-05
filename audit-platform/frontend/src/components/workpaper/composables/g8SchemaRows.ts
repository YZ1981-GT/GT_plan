/**
 * G8 行定义 — 源自 G8.xlsx / wp_render_schema/generated/G8.yaml / wp_fine_rules
 * 生成参考：backend/wp_templates/G/G8 其他权益工具投资.xlsx
 */

export type G8DisclosureSection = 'balance' | 'designation' | 'oci' | 'detail'

export interface G8DisclosureRowDef {
  rowKey: string
  label: string
  section: G8DisclosureSection
  /** 叙事性行（无金额列，仅存附注文本） */
  isNarrative?: boolean
}

/** G8-1 审定表明细行 — xlsx 审定表G8-1 rows 8-17（10 槽位）+ detail_discovery 示例标签 */
export const G8_ADJUDICATION_SCHEMA_LABELS = [
  '权益工具投资（FVOCI）',
  '其他',
  ...Array.from({ length: 8 }, (_, i) => `被投资单位${i + 1}`),
] as const

/** 附注披露（上市）18 行 × 7 列 — 余额 10 + 指定原因 1 + OCI 变动 7 */
export const G8_DISCLOSURE_LISTED_SCHEMA: G8DisclosureRowDef[] = [
  ...G8_ADJUDICATION_SCHEMA_LABELS.map((label, i) => ({
    rowKey: `listed_bal_${i + 1}`,
    label,
    section: 'balance' as const,
  })),
  {
    rowKey: 'listed_designation',
    label: '指定为以公允价值计量且其变动计入其他综合收益的原因',
    section: 'designation',
    isNarrative: true,
  },
  ...Array.from({ length: 7 }, (_, i) => ({
    rowKey: `listed_oci_${i + 1}`,
    label: i === 0 ? '权益工具投资（FVOCI）' : `被投资单位${i}`,
    section: 'oci' as const,
  })),
]

/** 附注披露（国企）20 行 × 7 列 — 余额 7 + 指定原因 1 + 期末明细 12 */
export const G8_DISCLOSURE_SOE_SCHEMA: G8DisclosureRowDef[] = [
  ...Array.from({ length: 7 }, (_, i) => ({
    rowKey: `soe_bal_${i + 1}`,
    label:
      i === 0 ? '权益工具投资（FVOCI）' : i === 1 ? '其他' : `被投资单位${i - 1}`,
    section: 'balance' as const,
  })),
  {
    rowKey: 'soe_designation',
    label: '指定为以公允价值计量且其变动计入其他综合收益的原因',
    section: 'designation',
    isNarrative: true,
  },
  ...Array.from({ length: 12 }, (_, i) => ({
    rowKey: `soe_detail_${i + 1}`,
    label: `项目名称${i + 1}`,
    section: 'detail' as const,
  })),
]
