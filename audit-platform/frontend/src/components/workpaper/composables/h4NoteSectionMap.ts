/**
 * H4 工程物资披露表 ↔ 附注章节映射（薄壳）
 *
 * H4 没有独立附注章节：它推的是 **H2 在建工程章节** 里的「工程物资」子表
 * （H2 负责「在建工程」行、H4 负责「工程物资」行，两者写同一张表）。
 * - 上市 → note_template_listed「五、23」子表「工程物资」
 * - 国企 → note_template_soe「八、23」子表「工程物资」
 *
 * 本文件只做两件事，**不含任何业务逻辑**：
 * 1. 内联章节号 / sheet 名字面量，供 `gen_note_wp_sync_registry.py` 与
 *    `disclosureSheetNameRegistry.spec.ts` 的 text-scan / glob 扫到 H4；
 * 2. re-export 真源 builder（`h4DisclosureSyncPayload` / `h4SoeDisclosureSyncPayload`）。
 *
 * 与 H2 的一致性由 `__tests__/h4h6NoteSectionMapShell.spec.ts` 交叉锁死。
 *
 * ⚠️ 两条生成器硬约束（H10 已实证，勿违反）：
 * - 章节号必须是**内联字符串字面量**，写 `= H2_NOTE_SECTION` 会让整条 wp_code 从 registry 消失；
 * - 常量对象体内**不得写注释**（注释里的 `listed: '…'` 会被优先抓到）。
 */
import {
  H2_DISCLOSURE_SHEET_NAME,
  H2_LISTED_SUBTABLE,
  H2_NOTE_SECTION,
  H2_SOE_SUBTABLE,
  isH2DisclosureApplicable,
  resolveH2CurrentStandard,
  type H2DisclosureVariant,
} from './h2NoteSectionMap'

export type H4DisclosureVariant = H2DisclosureVariant

export const H4_NOTE_SECTION = {
  listed: '五、23',
  soe: '八、23',
} as const satisfies Record<H4DisclosureVariant, string>

export const H4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H4DisclosureVariant, string>

/** H4 推送的子表名 = H2 章节里的「工程物资」表（真源在 h2NoteSectionMap） */
export const H4_MATERIALS_SUBTABLE = H2_LISTED_SUBTABLE.materials

/** 浅合并刷新目标：H2 汇总表的「工程物资」行 */
export const H4_SUMMARY_SUBTABLE = {
  listed: H2_LISTED_SUBTABLE.summary,
  soe: H2_SOE_SUBTABLE.summary,
} as const satisfies Record<H4DisclosureVariant, string>

export const isH4DisclosureApplicable = isH2DisclosureApplicable
export const resolveH4CurrentStandard = resolveH2CurrentStandard

export function resolveH4NoteSectionTarget(
  variant: H4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isH4DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = H4_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: H4_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveH4CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

/** 编制提示：合计数与在建工程一并披露，详见 H2 */
export const H4_XREF_H2 = '【工程物资与在建工程的合计数披露详见H2-1】'

/** H2 披露表 sheet 名（跨底稿芯片） */
export const H4_H2_DISCLOSURE_SHEET = H2_DISCLOSURE_SHEET_NAME

export {
  buildH4ListedMaterialsSubTable,
  buildH4ListedSyncPayloads,
  patchListedSummaryMaterialsRow,
  type H4ListedSyncSnapshot,
  type H4SyncFromWorkpaperPayload,
} from './h4DisclosureSyncPayload'

export {
  buildH4SoeColumns,
  buildH4SoeSyncPayloads,
  type H4SoeSyncPayload,
  type H4SoeSyncSnapshot,
} from './h4SoeDisclosureSyncPayload'
