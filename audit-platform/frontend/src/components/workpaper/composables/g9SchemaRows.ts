/**
 * G9 行定义 — 源自 G9.xlsx / wp_render_schema/generated/G9.yaml
 * 生成参考：backend/wp_templates/G/G9 其他非流动金融资产.xlsx
 */

export interface G9DisclosureRowDef {
  rowKey: string
  label: string
}

/** 附注披露（上市/国企）— xlsx rows 8-11 四类 + row 12 合计 */
const G9_DISCLOSURE_DATA_LABELS = [
  '债务工具投资',
  '权益工具投资',
  '指定为以公允价值计量且其变动计入当期损益的金融资产',
  '其他',
] as const

export const G9_DISCLOSURE_LISTED_SCHEMA: G9DisclosureRowDef[] = G9_DISCLOSURE_DATA_LABELS.map(
  (label, i) => ({ rowKey: `listed_${i + 1}`, label }),
)

export const G9_DISCLOSURE_SOE_SCHEMA: G9DisclosureRowDef[] = G9_DISCLOSURE_DATA_LABELS.map(
  (label, i) => ({ rowKey: `soe_${i + 1}`, label }),
)

/** 与 Excel 表头一致（上市 / 国企文案不同） */
export const G9_DISCLOSURE_COL_LABELS = {
  listed: {
    item: '种  类',
    current: '期末余额',
    prior: '上年年末余额',
  },
  soe: {
    item: '项  目',
    current: '期末公允价值',
    prior: '期初公允价值',
  },
} as const

export const G9_DISCLOSURE_TOTAL_LABEL = '合  计'
