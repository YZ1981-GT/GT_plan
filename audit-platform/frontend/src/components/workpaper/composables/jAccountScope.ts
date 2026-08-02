/**
 * J 类（职工薪酬）—— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 🔴 J2 原本硬编码 `2221`（应交税费！），长期应付职工薪酬实为 `2705`。
 * 活体三项目旧口径命中 33/68/18 个税种叶子（期末绝对值 23,109~7,604,040），
 * 不是恒空，是**把税种当长期应付职工薪酬显示在 J2-1 审定表里**。
 *
 * `report_config` 实证（四准则一致）::
 *
 *   J1: BS-051(listed) / BS-069(soe) = TB('2211','期末余额')  应付职工薪酬
 *   J2: BS-067(listed) / BS-093(soe) = NULL（兜底 2705）      长期应付职工薪酬
 *
 * 🔴 **两变体报表行编码不同**（平台其它循环多为同一 row_code 跨准则），
 * 故后端按 `entity_of(applicable_standards)` 挑 spec。
 *
 * 运行态口径以 render 下发的 `tb_source_codes.gross_standard` 为准，
 * 本文件的常量只作**兜底 + 展示**。禁止在组件里再写字面量科目码。
 *
 * spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
 *       Requirements 1.1, 3.3, 3.4
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

// ═══════════════════ J1 应付职工薪酬 ═══════════════════

/** J1 报表行次（按变体）：listed `BS-051` / soe `BS-069` */
export const J1_REPORT_ROW_BY_VARIANT = {
  listed: 'BS-051',
  soe: 'BS-069',
} as const

/** J1 原值兜底标准码 */
export const J1_GROSS_FALLBACK = '2211'

/** J1 科目中文名 */
export const J1_ACCOUNT_NAME = '应付职工薪酬'

/** J1 试算平衡表 / 余额表查询口径 */
export function j1GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, J1_GROSS_FALLBACK)
}

/** J1 单一科目码（回写 TB / EventBus 用） */
export function j1AccountCode(src?: TbSourceCodes | null): string {
  return j1GrossQueryCodes(src)[0]
}

// ═══════════════════ J2 长期应付职工薪酬 ═══════════════════

/** J2 报表行次（按变体）：listed `BS-067` / soe `BS-093` */
export const J2_REPORT_ROW_BY_VARIANT = {
  listed: 'BS-067',
  soe: 'BS-093',
} as const

/** J2 原值兜底标准码 —— 🔴 **不是** `2221`（应交税费）也不是 `2611`（不存在） */
export const J2_GROSS_FALLBACK = '2705'

/** J2 科目中文名 */
export const J2_ACCOUNT_NAME = '长期应付职工薪酬'

/**
 * 🔴 曾被误当作长期应付职工薪酬的科目族 —— 守卫用（源码不得再出现该字面量作科目码）。
 * `2221` = 应交税费；`2611` = 活体 account_chart 不存在。
 */
export const J2_WRONG_LEGACY_ACCOUNTS = ['2221', '2611'] as const

/** J2 试算平衡表 / 余额表查询口径 */
export function j2GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, J2_GROSS_FALLBACK)
}

/** J2 单一科目码（回写 TB / EventBus 用） */
export function j2AccountCode(src?: TbSourceCodes | null): string {
  return j2GrossQueryCodes(src)[0]
}

// ═══════════════════ J 类通用：无备抵科目 ═══════════════════

/**
 * J 类（职工薪酬）**无备抵科目** —— 负债类原值本身是贷方。
 * 溯源面板不传 `provisionLabel` 即自动隐藏备抵行。
 */
export const J_HAS_PROVISION = false

/**
 * 🔴 J 类**无账龄披露** —— J2「未折现的离职后福利预计到期分析」是到期分析（未来 4 档），
 * CAS 9 固定档位，语义与账龄（过去）相反。禁止引用 `disclosureAgingLabels` / `useAgingConfig`。
 */
export const J_MATURITY_BANDS = ['一年以内', '一到两年', '二到五年', '五年以上'] as const
