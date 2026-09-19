/**
 * m5NoteSectionMap — M5 盈余公积 披露 ↔ 附注章节映射（薄壳）
 *
 * 🔴 结构与 M4 资本公积 / M7 专项储备同构（标准变动表），实现收敛在共享映射
 * `mEquityChangeNoteSectionMap.ts`（`buildMEquitySyncPayload('M5', …)`）。本文件仅提供
 * per-wp 常量供 `gen_note_wp_sync_registry.py` 与 `disclosureSheetNameRegistry.spec.ts`
 * 扫描；章节号 / sheet 名字面由 `mEquityNoteSubtableContract.spec.ts` 交叉锁死。
 */
export {
  buildMEquitySyncPayload,
  mEquityColumnsFor,
  M_EQUITY_CONFIG,
} from './mEquityChangeNoteSectionMap'

/** 章节号（单一真源 = M_EQUITY_CONFIG.M5.section，此处字面由契约测试锁死） */
export const M5_NOTE_SECTION = { listed: '五、59', soe: '八、62' } as const

/** 披露 sheet 真实 tab 名（实测源 xlsx，全角括号；两版共用 = M_EQUITY_DISCLOSURE_SHEET_NAME） */
export const M5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const
