/**
 * m4NoteSectionMap — M4 资本公积 披露 ↔ 附注章节映射（薄壳）
 *
 * 🔴 结构与 M5 盈余公积 / M7 专项储备同构（标准变动表），实现收敛在共享映射
 * `mEquityChangeNoteSectionMap.ts`（`buildMEquitySyncPayload('M4', …)`）。本文件仅提供：
 *   ① 生成器 / 守卫需要的 per-wp 常量（文件名须匹配 `^([a-z]+\d+)NoteSectionMap\.ts$`
 *      才会被 `gen_note_wp_sync_registry.py` 与 `disclosureSheetNameRegistry.spec.ts` 扫到）；
 *   ② 章节号 / sheet 名单一真源仍是共享映射 —— 本文件字面量由
 *      `mEquityNoteSubtableContract.spec.ts` 交叉锁死（≡ M_EQUITY_CONFIG.M4 / 共享 sheet 名），
 *      防两处漂移。
 */
export {
  buildMEquitySyncPayload,
  mEquityColumnsFor,
  M_EQUITY_CONFIG,
} from './mEquityChangeNoteSectionMap'

/** 章节号（单一真源 = M_EQUITY_CONFIG.M4.section，此处字面由契约测试锁死） */
export const M4_NOTE_SECTION = { listed: '五、55', soe: '八、60' } as const

/** 披露 sheet 真实 tab 名（实测源 xlsx，全角括号；两版共用 = M_EQUITY_DISCLOSURE_SHEET_NAME） */
export const M4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const
