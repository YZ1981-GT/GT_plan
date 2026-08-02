/**
 * j2NoteSectionMap — J2 长期应付职工薪酬/设定受益计划净资产 披露表↔附注模块映射
 *
 * 权威来源：
 *   - note_template_variant_matrix.json: chang_qi_ying_fu_zhi_gong_xin_chou →
 *     listed 五、49 / soe 八、54
 *   - workpaper_sheet_classification(wp_code=J2):
 *     附注披露信息（上市公司）/ 附注披露信息（国有企业）
 *   - 源 xlsx: backend/wp_templates/J/J2 长期应付职工薪酬-设定受益计划净资产.xlsx
 *
 * Spec: .kiro/specs/disclosure-sync-path-buildout/ (批6 J2)
 */

export const J2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const

export const J2_NOTE_SECTION = {
  listed: '五、49',
  soe: '八、54',
} as const

/**
 * 设定受益计划净资产落点（五、17）。仅上市侧净资产状态时推。
 * variant_matrix: soe 侧为 null → 不推。
 */
export const J2_NET_ASSET_NOTE_SECTION = {
  listed: '五、17',
  soe: null,
} as const
