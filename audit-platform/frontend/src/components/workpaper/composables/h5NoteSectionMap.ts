/**
 * h5NoteSectionMap — H5 油气资产披露表 ↔ 附注联动映射（仅国企）
 *
 * 权威来源：
 * - 章节号 `note_template_variant_matrix.json` · `you_qi_zi_chan`：
 *   `soe_standalone = 八、25`；**`listed_standalone = null`**
 * - 结构 `backend/wp_templates/H/H5 油气资产.xlsx` 的「附注披露信息（国有企业）」
 *   （行 9 表头 5 列 / 行 10~24 四层 16 行）
 * - 附注模板 `note_template_soe.json §八、25`（行集已与源模板一致；
 *   columns/guidance 由 `fix_note_h5_oil_gas_structure.py` 补齐）
 *
 * 🔴 **上市侧不做**（实证，非欠账）：`variant_matrix` listed=null，且
 * `note_template_listed.json` 中油气资产章节数**实测 0** —— 上市准则下油气资产不单独
 * 设附注章节。源 xlsx 虽有「附注披露信息（上市公司）」sheet，但无落点，
 * **不得凭空新建章节**（宁缺勿造）。
 *
 * 契约（后端 `SyncFromWorkpaperRequest` 实测，勿改形状）：
 * 1. 顶层字段只有 `wp_id`/`sheet_name`/`section_id`/`sub_table_data`/`columns`/
 *    `current_standard`/`year`。
 * 2. 🔴 `_note_texts` 是 **`sub_table_data` 内的 `_` 前缀元数据键**（服务层
 *    `_extract_note_texts` pop 后写 `text_content`）。**放载荷顶层会被 pydantic 静默
 *    忽略** —— 本文件历史版本正是如此，导致「补充披露（国资监管要求）」从未进入附注。
 * 3. `sub_table_data` 行必须是**业务键 dict**（键 = `columns[].key`），投影器按
 *    `row.get(colDef.key)` 取值。历史版本用位置化 `values: [期末, 期初]`（2 值塞进
 *    4 个数据列且顺序与模板相反）→ 期末余额落进期初余额列。
 */
import type { ColumnDef } from './disclosureColumnDefs'

/** 权威附注章节号（仅 SOE 有独立章节） */
export const H5_NOTE_SECTION = { soe: '八、25' } as const

/** H5 SOE 版披露 sheet 真实 tab 名 */
export const H5_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

/** 与 note_template_soe §八、25 tables[].name 逐字一致 */
export const H5_SOE_SUBTABLE = { main: '油气资产' } as const

/** 四层「其中：」资产类别（源模板：累计折耗层只列探明矿区权益与井及相关设施两类） */
const CAT_FULL = ['1．探明矿区权益', '2．未探明矿区权益', '3．井及相关设施'] as const
const CAT_DEPLETION = ['1．探明矿区权益', '2．井及相关设施'] as const

/** 层定义：合计行标签 + 其中类别（顺序即模板行序，单一真源） */
const LAYERS = [
  { total: '一、原价合计', cats: CAT_FULL, key: 'cost' },
  { total: '二、累计折耗合计', cats: CAT_DEPLETION, key: 'depletion' },
  { total: '三、油气资产减值准备累计金额合计', cats: CAT_FULL, key: 'impairment' },
  { total: '四、油气资产账面价值合计', cats: CAT_FULL, key: 'carrying' },
] as const

/** 模板 §八、25 的 16 行标签（逐字、按序；供守卫与载荷共用） */
export const H5_SOE_ROW_LABELS: readonly string[] = LAYERS.flatMap((l) => [
  l.total,
  ...l.cats.map((c, i) => (i === 0 ? `其中：${c}` : c)),
])

/**
 * 汇总表列头（5 列单级 → 标签列标 `flat`，抑制 seed 路径把
 * `本期增加额`/`本期减少额` 反猜出凭空「本期」父表头）。
 * key 与 `fix_note_h5_oil_gas_structure.py` 的 columns 逐字一致。
 */
export const H5_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [H5_SOE_SUBTABLE.main]: [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加额', format: 'amount' },
    { key: 'decrease', label: '本期减少额', format: 'amount' },
    { key: 'end', label: '期末余额', format: 'amount' },
  ],
}

/** 层级期末合计（底稿审定表 H5-1 可得；其余维度底稿暂无数据） */
export interface H5LayerTotals {
  /** 一、原价合计 期末 */
  cost?: number | null
  /** 二、累计折耗合计 期末 */
  depletion?: number | null
  /** 三、减值准备累计金额合计 期末 */
  impairment?: number | null
}

export interface H5SyncPayloadOptions {
  wpId: string
  projectId: string
  year: number
  /** 层级期末合计（原值/折耗/减值） */
  layerTotals: H5LayerTotals
  /** 说明文本（国企特殊披露区段） */
  soeDisclosureText?: string
}

export interface H5SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function n(v: unknown): number {
  const x = Number(v)
  return Number.isFinite(x) ? x : 0
}

/**
 * 构造 16 行四层行集（业务键 dict）。
 *
 * 🔴 **宁缺勿造**：底稿（审定表 H5-1）只提供各层**期末合计**，
 * 故「其中：」类别行与 `期初余额`/`本期增加额`/`本期减少额` 一律 `null`，
 * **不用 0 冒充已知值**（0 与"未取数"在附注里语义完全不同）。
 * 待底稿补按矿区类别/变动明细的录入位置后再填。
 */
export function buildH5SoeRows(totals: H5LayerTotals): Record<string, unknown>[] {
  const cost = n(totals.cost)
  const depletion = n(totals.depletion)
  const impairment = n(totals.impairment)
  const endOf: Record<string, number> = {
    cost,
    depletion,
    impairment,
    // 源模板：四、账面价值合计 = 原价 − 累计折耗 − 减值准备
    carrying: cost - depletion - impairment,
  }

  const rows: Record<string, unknown>[] = []
  for (const layer of LAYERS) {
    rows.push({
      label: layer.total,
      begin: null,
      increase: null,
      decrease: null,
      end: endOf[layer.key],
      is_total: true,
    })
    layer.cats.forEach((c, i) => {
      rows.push({
        label: i === 0 ? `其中：${c}` : c,
        begin: null,
        increase: null,
        decrease: null,
        end: null,
      })
    })
  }
  return rows
}

/**
 * 构造 H5 SOE 版附注同步载荷。
 *
 * @returns 可直接 POST 到 `/api/projects/{pid}/disclosure-notes/sync-from-workpaper` 的请求体
 */
export function buildH5SyncPayload(opts: H5SyncPayloadOptions): H5SyncFromWorkpaperPayload {
  const { wpId, year, layerTotals, soeDisclosureText } = opts

  const sub_table_data: Record<string, unknown> = {
    [H5_SOE_SUBTABLE.main]: buildH5SoeRows(layerTotals),
  }

  // 🔴 `_note_texts` 必须放 `sub_table_data` 内（顶层会被 pydantic 静默丢弃）
  const text = String(soeDisclosureText || '').trim()
  if (text) {
    sub_table_data._note_texts = [
      { section: 'soe-supplementary', title: '补充披露（国资监管要求）', text },
    ]
  }

  return {
    wp_id: wpId,
    sheet_name: H5_DISCLOSURE_SHEET_SOE,
    section_id: H5_NOTE_SECTION.soe,
    current_standard: 'soe_standalone',
    year,
    sub_table_data,
    columns: H5_SOE_COLUMNS,
  }
}
