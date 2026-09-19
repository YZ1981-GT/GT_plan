/**
 * g7NoteSectionMap — G7 长期股权投资 披露 ↔ 附注章节映射（薄壳）
 *
 * 文件名须匹配 `^([a-z]+\d+)NoteSectionMap\.ts$` 才会被
 * `gen_note_wp_sync_registry.py` 与 `disclosureSheetNameRegistry.spec.ts` 扫到。
 *
 * 🔴 章节号必须内联字面量、对象体内无注释、
 * `G7_DISCLOSURE_SHEET_NAME` 必须写成单个对象（分离常量无分号会被正则吞掉）。
 * 跨章 `七、1` / `七、*` 不进此处（registry 只记主章节），由前端 payload 自行携带。
 *
 * spec: g7-four-table-extraction-and-disclosure-alignment (Task 6.1)
 */
export const G7_NOTE_SECTION = { listed: '五、18', soe: '八、18' } as const

export const G7_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const

export { buildG7ListedSyncPayloads } from '../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
export { buildG7SoeSyncPayloads } from '../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'
