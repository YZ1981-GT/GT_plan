/**
 * E1 货币资金披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、1 / note_template_soe.json 八、1「货币资金」
 * （sheet 结构见 E1 底稿「附注披露信息(上市公司)/(国企)」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 表结构对齐附注模板（附注模块 el-table 仅支持单级表头，故不推送外币多级表头表；
 * 外币信息按模板归属附注五、81 外币货币性项目，不落 五、1/八、1）：
 *  - listed 五、1：单表「货币资金」（项目/期末余额/上年年末余额）
 *  - soe 八、1：主表「货币资金」（项目/期末余额/期初余额）+「受限制的货币资金明细」
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { e1MainRows } from './e1DisclosureScope'

export type E1DisclosureVariant = 'listed' | 'soe'

export const E1_NOTE_SECTION = {
  listed: '五、1',
  soe: '八、1',
} as const satisfies Record<E1DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（半角括号，见 workpaper_sheet_classification wp_code=E1）。
// 用真实 sheet 名而非合成标识，使附注「打开同步底稿」(_last_sync_sheet) 反向跳转也能精确定位。
export const E1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<E1DisclosureVariant, string>

/**
 * ②表在附注模板里的表名（逐字，`sub_table_data` 以表名为键 → 错一个字就产生孤儿表）。
 *
 * 国企 `八、1` 模板已有该表；上市 `五、1` 由 `fix_note_e1_monetary_fund_structure.py`
 * 按用户裁决补建（两版同名同结构，列头 label 按变体分开）。
 */
export const E1_RESTRICTED_TABLE = '受限制的货币资金明细'

/**
 * 合计行字面 —— 按**本章节实证**取值。
 *
 * 🔴 平台的 `DISCLOSURE_TOTAL_LABEL`（`合 计`，带空格）**不可全局硬套**：
 * 附注模板 `五、1`/`八、1` 的合计行字面是 `合计`（无空格），而源 xlsx 底稿侧是
 * `合  计`（两空格）→ 底稿 UI 用源模板字面、同步载荷投影成附注字面（D3 同款教训）。
 */
export const E1_NOTE_TOTAL_LABEL = '合计'

export function resolveE1CurrentStandard(
  variant: E1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

const AMT = 'amount' as const

// ─── 列头元数据（逐字取自附注模板 五、1/八、1 + E1TabDisclosure 披露表列）──────
// listed 主表：项目/期末余额/上年年末余额（模板 五、1 headers）
// 🔴 必须显式标 `flat`（单级表头）—— 否则 `_infer_groups_from_headers` 可能凭空
// 推出父表头；且 **seed 与推送两处都要加**（H8 踩过只加一侧的坑）。
const MAIN_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
// soe 主表：项目/期末余额/期初余额（模板 八、1 headers）
const MAIN_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
]
/**
 * ②表列头 —— **3 列，逐字对齐源 xlsx**（国企 R16「项 目/期末余额/年初余额」）。
 *
 * 🔴 底稿的「受限原因」列**不推送到附注**：源模板②表只有 3 列，受限事由按 R13 括注
 * 「应单独说明」的要求写在**文字说明段**里（`_note_texts` 的「受限及境外款项说明」）。
 * 平台铁律：附注是交付物，列结构随附注模版；底稿可多留审计列，同步时投影成附注形状。
 * 改造前载荷推 4 列（含 `reason`）而模板只有 3 列 = 孤儿列。
 */
const RESTRICTED_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
const RESTRICTED_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
]

/** 主表表名（两版同名，模板 五、1 / 八、1 的 `tables[0].name`） */
export const E1_MAIN_TABLE = '货币资金'

/**
 * 子表名映射 `{语义键: 模板表名}` —— 供契约测试与孤儿表判定。
 * 🔴 值必须与 `note_template_*.json` 的 `tables[].name` **逐字一致**，
 * 否则同步产出孤儿子表（附注 TAB 永空 + 底稿数据丢失）。
 */
export const E1_LISTED_SUBTABLE = Object.freeze({
  main: E1_MAIN_TABLE,
  restricted: E1_RESTRICTED_TABLE,
})
export const E1_SOE_SUBTABLE = Object.freeze({
  main: E1_MAIN_TABLE,
  restricted: E1_RESTRICTED_TABLE,
})

/**
 * 列定义（**零入参**）—— 平台 `disclosureColumnsCoverage` 的 sweep 用空入参调用
 * 所有 `build*Columns` 导出，故不得设必填参数。
 */
export function buildE1ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [E1_MAIN_TABLE]: MAIN_COLUMNS_LISTED,
    [E1_RESTRICTED_TABLE]: RESTRICTED_COLUMNS_LISTED,
  }
}

export function buildE1SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [E1_MAIN_TABLE]: MAIN_COLUMNS_SOE,
    [E1_RESTRICTED_TABLE]: RESTRICTED_COLUMNS_SOE,
  }
}

// ─── 快照行类型（组件层传入，字段与 E1TabDisclosure 行接口对齐）───────────────
export interface E1MainRowLike {
  key: string
  /** 底稿 UI 字面（源 xlsx 口径） */
  label: string
  /**
   * 附注字面（源 docx 口径）——**可选**。不传时由 `e1MainRows(variant)` 真源按 `key`
   * 反查（见 `mainRow()`），故调用方无需逐个传；传了则优先。
   */
  noteLabel?: string
  endingAmount: number
  openingAmount: number
}
export interface E1RestrictedRowLike {
  item: string
  openingAmount: number
  endingAmount: number
  reason: string
}

/** 一段披露说明（按源模板分段，每段带中文 title）。 */
export interface E1NoteSectionLike {
  key: string
  title: string
  text: string
}

export interface E1DisclosureSnapshot {
  /** 主披露表行（含合计/其中：存放境外，label 直接来自披露表） */
  mainRows: E1MainRowLike[]
  /**
   * ② 受限制的货币资金明细。
   * 🔴 **两变体都推**（用户裁决 2026-08-01：上市侧也建该表 —— 校验预设 listed 侧的
   * F1-4/F1-5/F1-6 明确引用②表）。**条件表语义**：空数组 = 不推该表且进
   * `_removed_table_keys`（有录入区块的条件表，K7 范式）。
   */
  restrictedRows?: E1RestrictedRowLike[]
  /**
   * 披露说明（按源模板分段）。上市 2 段 / 国企 2 段，见 `e1DisclosureScope.e1NoteTexts`。
   * 空文本段自动过滤，不产生空 `_note_texts` 条目。
   */
  noteSections?: E1NoteSectionLike[]
  /** @deprecated 旧版单一说明框；仍支持以兼容存量调用方，等价于单段「货币资金说明」。 */
  noteText?: string
}

export interface E1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

/** 主表行 key → 是否合计行（合计标 is_total 供投影器识别加粗）。 */
function isTotalKey(key: string): boolean {
  return key === 'total'
}

/**
 * 构建 E1 → 附注 sync-from-workpaper 载荷。
 * listed：单表「货币资金」；soe：主表「货币资金」+「受限制的货币资金明细」。
 */
export function buildE1SyncPayload(
  variant: E1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: E1DisclosureSnapshot,
): E1SyncPayload {
  // 🔴 附注行标签走 **docx 口径**（`noteLabel`），底稿 UI 保留 xlsx 口径（`label`）。
  // soe 首行底稿是「现金」而附注模板是「库存现金」—— 直接推 `label` 会产生孤儿行
  // （`sub_table_data` 以行标签匹配）。真源是 `e1DisclosureScope`，此处按 key 反查，
  // 不要求调用方逐个传 `noteLabel`（少传一个就是一条静默孤儿行）。
  const noteLabelByKey = new Map<string, string>(
    e1MainRows(variant)
      .filter((d) => !!d.noteLabel)
      .map((d) => [d.key, d.noteLabel as string]),
  )
  const mainRow = (r: E1MainRowLike) => ({
    label: r.noteLabel ?? noteLabelByKey.get(r.key) ?? r.label,
    end_amount: num(r.endingAmount),
    prior_amount: num(r.openingAmount),
    ...(isTotalKey(r.key) ? { is_total: true } : {}),
  })

  const subTableData: Record<string, unknown> = {
    [E1_MAIN_TABLE]: snapshot.mainRows.map(mainRow),
    _note_texts: buildNoteTexts(variant, snapshot),
  }

  // 列定义单一真源 = 零参 builder（契约测试与覆盖率 sweep 读的也是它，禁在此另写一份）
  const allColumns = variant === 'soe' ? buildE1SoeColumns() : buildE1ListedColumns()
  const columns: Record<string, ColumnDef[]> = {
    [E1_MAIN_TABLE]: allColumns[E1_MAIN_TABLE],
  }

  // ② 受限制的货币资金明细 —— **两变体都推**（用户裁决）。
  //
  // 🔴 `undefined` 与 `[]` 语义必须区分（K3 vs K7 铁律）：
  //  - `undefined` = 调用方**不管**这张表 → 跳过，**不进** `_removed_table_keys`
  //    （表可能由别的底稿承载，越权删会打断对方）
  //  - `[]`        = 调用方**管这张表但当前为空** → 不推空表**且进** `_removed_table_keys`
  //    （否则用户填过再删空，附注会永久残留上次推送的过时明细，K7 已实测复现）
  const restricted = snapshot.restrictedRows
  const removedTableKeys: string[] = []
  if (restricted && restricted.length) {
    const endTotal = restricted.reduce((s, r) => s + num(r.endingAmount), 0)
    const openTotal = restricted.reduce((s, r) => s + num(r.openingAmount), 0)
    subTableData[E1_RESTRICTED_TABLE] = [
      // `reason` 不进附注（源模板②表只有 3 列，事由走文字说明段）
      ...restricted.map((r) => ({
        label: r.item,
        end_amount: num(r.endingAmount),
        prior_amount: num(r.openingAmount),
      })),
      {
        label: E1_NOTE_TOTAL_LABEL,
        end_amount: endTotal,
        prior_amount: openTotal,
        is_total: true,
      },
    ]
    columns[E1_RESTRICTED_TABLE] = allColumns[E1_RESTRICTED_TABLE]
  } else if (restricted) {
    removedTableKeys.push(E1_RESTRICTED_TABLE)
  }
  if (removedTableKeys.length) {
    subTableData._removed_table_keys = removedTableKeys
  }

  return {
    wp_id: wpId,
    sheet_name: E1_DISCLOSURE_SHEET_NAME[variant],
    section_id: E1_NOTE_SECTION[variant],
    current_standard: resolveE1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns,
  }
}

/**
 * 披露说明 → `_note_texts`（**仅非空段**），保证附注 `text_content` 与披露表一致。
 *
 * 🔴 每条必须带**中文 `title`** —— 后端 `_format_note_texts` 缺 title 时用 `section`
 * 兜底，附注正文会渲染成 `【listed-note】` 这类英文键（违反 UI 全中文化铁律）。
 */
export function buildNoteTexts(
  variant: E1DisclosureVariant,
  /** 分段快照；也接受旧签名的裸字符串（单一说明框）以保持公开 API 兼容 */
  input: Pick<E1DisclosureSnapshot, 'noteSections' | 'noteText'> | string | null | undefined,
): Array<{ section: string; title: string; text: string }> {
  const snapshot: Pick<E1DisclosureSnapshot, 'noteSections' | 'noteText'> =
    typeof input === 'string' ? { noteText: input } : (input ?? {})
  const sections = snapshot.noteSections
  if (sections && sections.length) {
    return sections
      .map((s) => ({
        section: `${variant}-note-${s.key}`,
        title: String(s.title ?? '').trim() || '货币资金说明',
        text: String(s.text ?? '').trim(),
      }))
      .filter((s) => !!s.text)
  }
  // 兼容旧签名：单一说明框
  const text = String(snapshot.noteText ?? '').trim()
  if (!text) return []
  return [{ section: `${variant}-note`, title: '货币资金说明', text }]
}
