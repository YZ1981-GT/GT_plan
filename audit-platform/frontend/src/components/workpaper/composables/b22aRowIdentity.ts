/**
 * b22aRowIdentity — B22A 稳定行身份纯函数层（对齐 D4 已交付范式）。
 *
 * spec: b-cycle-sync-foundation-and-first-canary（BC-53 行身份缺陷族）
 *
 * ═══ 为什么必须存在 ═══════════════════════════════════════════════════════
 *
 * 改造前 B22A 的行键是**数组下标**：`B22A-T{tab}-item-{index}-{field}`（每字段
 * 一条 checklist_responses 记录），且 `removeCheckItem` 用「整块 shift 搬迁」实现
 * 删行 —— 删第 3 行时把第 4..N 行的每个字段值逐个往前挪一格、再清空末行。两类真缺陷：
 *
 *   ① **双向回写必错位**：OO 侧插/删行不走这套 shift，两侧行号立刻脱钩。用户在
 *      Excel 第 3 行插一行，HTML 侧第 3 行之后全部错位一格 —— BC-53 判定 B22A
 *      不能直接接真双向的根因。
 *   ② **外部引用静默错配**：行身份是下标 ⇒ 指向「第 n 行」的外部记录（B22B 带入的
 *      控制点、复核线程锚点、缺陷清单回链）在删行后指向**别人的内容**而非失效。
 *
 * ═══ 形态对齐 D4（不是另发明一套）═════════════════════════════════════════
 *
 * D4 已交付范式（`phase5_d4_revenue_detail.py` + `useIpoChecklistTab.ts` 实测）：
 *   - 后端 `ROW_IDENTITY_STORE_KEY = "rowId"`，行身份是**行对象内的字段**
 *   - `store_row_identity()` 缺 `rowId` 直接抛 `StorePayloadError`（fail closed，
 *     **不得**退回数组下标作身份）
 *   - 前端整组行存**单条 item 的 JSON 数组**（如 `D4-2-rows`），每行对象带 `rowId`
 *   - legacy 兼容按 `row.rowId ?? '{scope}-legacy-{i}'` 补发稳定串
 *
 * 本模块沿用同一形态：B22A 每个 tab（含 IT 子区）一条 `B22A-T{tab}-rows`，
 * remark = 行对象 JSON 数组，每行带 `rowId`。删行 = 从数组摘除该行对象，
 * **不搬迁任何字段值**。
 */

import { newRowIdentity } from './shared/rowIdentity'

/** 行身份字段名 —— 与 D4 后端 `ROW_IDENTITY_STORE_KEY` 逐字一致，禁改。 */
export const ROW_IDENTITY_KEY = 'rowId' as const

/** 受管字段集（与 legacy generateItemId 的 field 联合类型一致）。 */
export const B22A_ROW_FIELDS = [
  'point', 'desc', 'method', 'conclusion', 'ref', 'nochange',
] as const

export type B22ARowField = (typeof B22A_ROW_FIELDS)[number]

/** 行对象：rowId + seq（显示序号）+ 受管字段 + attrs（B22B 属性 JSON）。 */
export interface B22ARow {
  rowId: string
  seq: number
  point?: string
  desc?: string
  method?: string
  conclusion?: string | null
  ref?: string
  nochange?: string
  /** B22B 控制矩阵属性（反舞弊/频率/执行人等），原 `-attrs` 字段。 */
  attrs?: Record<string, unknown>
  [key: string]: unknown
}

/** scope 串：无 subPanel 为 `T{tab}`，有则 `T{tab}-{subPanel}`。 */
export function rowScope(tab: number | string, subPanel?: string): string {
  return subPanel ? `T${tab}-${subPanel}` : `T${tab}`
}

/**
 * 行数组的 item_id（单条记录存整组行）。
 *
 * 命名沿用 `B22A-` 前缀，使真库既有 `item_id LIKE 'B22A-%'` 查询仍能命中。
 */
export function rowsItemId(tab: number | string, subPanel?: string): string {
  return subPanel
    ? `B22A-T${tab}-IT-${subPanel}-rows`
    : `B22A-T${tab}-rows`
}

/**
 * 生成稳定行 id。
 *
 * 🔴 不用裸 `Date.now()` / `Math.random()` 作**唯一**来源：熵键单独用在持久化键上
 * 会让同一行在不同会话拿到不同身份（BC-53 熵键判据）。这里的形态是
 * `{scope}-{时间基}-{短随机}`，与 D4 `useIpoChecklistTab.newRow()` 实测一致 ——
 * 时间基保证单调可读，短随机避免同毫秒并发碰撞，生成后即写入行对象**不再变化**。
 */
export function makeRowId(scope: string): string {
  return newRowIdentity(`B22A-${scope}`)
}

/** legacy 行的补发身份（对齐 D4 `row.rowId ?? '{scope}-legacy-{i}'`）。 */
export function legacyRowId(scope: string, index: number): string {
  return `B22A-${scope}-legacy-${index}`
}

/** legacy 下标形态的字段 item_id（迁移时回读旧数据用）。 */
export function legacyFieldItemId(
  tab: number | string,
  index: number,
  field: B22ARowField | string,
  subPanel?: string,
): string {
  const prefix = subPanel
    ? `B22A-T${tab}-IT-${subPanel}`
    : `B22A-T${tab}-item`
  return `${prefix}-${index}-${field}`
}

/** legacy count 键（迁移时读行数用）。 */
export function legacyCountItemId(
  tab: number | string,
  subPanel?: string,
): string {
  return subPanel
    ? `B22A-T${tab}-IT-${subPanel}-count`
    : `B22A-T${tab}-count`
}

// ═══════════════════════════════════════════════════════════════════════════
// 前缀化行表（IT 子区：B22A-it-summary / -it-system / -it-sod）
// ═══════════════════════════════════════════════════════════════════════════
//
// 🔴 IT 子区是与 COSO tab **并存的第二套行存储**：键形状是
// `{prefix}-{index}-{field}`（如 `B22A-it-summary-3-name`），由 `_getRows` /
// `_addRow` / `_removeRow` / `_setRowField` 四个前缀化函数服务三个表。
// 它有与 COSO tab 完全同型的 shift 搬迁缺陷，改造口径一致：行数组 + 稳定 rowId。

/** 前缀化行表的行数组 item_id。 */
export function prefixedRowsItemId(prefix: string): string {
  return `${prefix}-rows`
}

/** 前缀化行表的 legacy count 键。 */
export function prefixedLegacyCountItemId(prefix: string): string {
  return `${prefix}-count`
}

/** 前缀化行表的 legacy 字段键。 */
export function prefixedLegacyFieldItemId(
  prefix: string,
  index: number,
  field: string,
): string {
  return `${prefix}-${index}-${field}`
}

/** 前缀 → scope 串（去掉 `B22A-` 前缀，保留辨识段）。 */
export function prefixScope(prefix: string): string {
  return prefix.replace(/^B22A-/, '')
}

/**
 * 迁移前缀化行表的 legacy 数据。
 *
 * 与 `migrateLegacyGroup` 的差异：字段集由调用方传入（各 IT 表列不同），
 * 且全部字段走 remark（IT 子区没有 conclusion 白名单列）。
 */
export function migrateLegacyPrefixedRows(
  reader: {
    getCount(prefix: string): number
    getField(itemId: string): { remark?: string | null } | undefined
  },
  prefix: string,
  fields: readonly string[],
): B22ARow[] {
  const scope = prefixScope(prefix)
  const count = reader.getCount(prefix)
  const rows: B22ARow[] = []
  for (let i = 1; i <= count; i++) {
    const row: B22ARow = { rowId: legacyRowId(scope, i), seq: i }
    for (const f of fields) {
      const rec = reader.getField(prefixedLegacyFieldItemId(prefix, i, f))
      if (rec?.remark != null) row[f] = rec.remark
    }
    rows.push(row)
  }
  return rows
}

/**
 * 解析行数组（非法/缺失 → 空数组，fail soft 不抛）。
 *
 * 🔴 与后端 `iter_store_rows` 的 fail-closed 语义**分工不同**：前端渲染侧宁可显示
 * 空表也不能白屏；后端投影侧必须拒绝无身份的行（否则会把脏行写进 OO）。两侧各管一段，
 * 这与 D4 `useIpoChecklistTab` 的注释「OO 侧行身份由后端按 rowId 判定，两者各管一段」同口径。
 */
export function parseRows(remark: string | null | undefined, scope: string): B22ARow[] {
  if (!remark) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(remark)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []
  return parsed.map((raw, i) => normalizeRow(raw, scope, i))
}

/** 归一单行：补齐 rowId / seq，保留其余字段。 */
export function normalizeRow(raw: unknown, scope: string, index: number): B22ARow {
  const obj = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const rid = obj[ROW_IDENTITY_KEY]
  return {
    ...obj,
    rowId: typeof rid === 'string' && rid.trim() ? rid : legacyRowId(scope, index),
    seq: Number(obj.seq) || index + 1,
  } as B22ARow
}

/** 序列化行数组。 */
export function serializeRows(rows: readonly B22ARow[]): string {
  return JSON.stringify([...rows])
}

/** 重排 seq（删/插行后调用，使显示序号连续）。 */
export function resequence(rows: readonly B22ARow[]): B22ARow[] {
  return rows.map((r, i) => ({ ...r, seq: i + 1 }))
}

/**
 * 判断行是否为「纯占位空行」（除 rowId/seq 外全空）。
 *
 * 对齐 D4 的空行过滤：源模板占位序号不应被推成真实数据行。
 */
export function isBlankRow(row: B22ARow): boolean {
  for (const f of B22A_ROW_FIELDS) {
    const v = row[f]
    if (v != null && String(v).trim() !== '') return false
  }
  return true
}

// ═══════════════════════════════════════════════════════════════════════════
// 存量迁移：legacy 每字段一条记录 → 整行数组
// ═══════════════════════════════════════════════════════════════════════════

/** 迁移输入：一个 (tab, subPanel) 组的 legacy 记录读取器。 */
export interface LegacyReader {
  /** 读 legacy 行数（count 键的 remark）。 */
  getCount(tab: number | string, subPanel?: string): number
  /** 读 legacy 字段值，返回 {conclusion, remark, wp_ref}。 */
  getField(itemId: string): {
    conclusion?: string | null
    remark?: string | null
    wp_ref?: string | null
  } | undefined
}

/**
 * 把一个 (tab, subPanel) 组的 legacy 下标数据迁移为行数组。
 *
 * 🔴 字段值语义按 legacy 原样搬运，不做任何"顺手清洗"：
 *   - `point` / `desc` / `ref` / `nochange` 取 remark
 *   - `conclusion` 取 conclusion（白名单枚举列）
 *   - `method` 取 remark（多选序列化串）
 *   - `attrs` 取 `-attrs` 的 remark（JSON）
 * 迁移只改**键的形状**，不改值 —— 值变了就不是迁移而是篡改审计记录。
 */
export function migrateLegacyGroup(
  reader: LegacyReader,
  tab: number | string,
  subPanel?: string,
): B22ARow[] {
  const scope = rowScope(tab, subPanel)
  const count = reader.getCount(tab, subPanel)
  const rows: B22ARow[] = []
  for (let i = 1; i <= count; i++) {
    const row: B22ARow = {
      rowId: legacyRowId(scope, i),
      seq: i,
    }
    for (const field of B22A_ROW_FIELDS) {
      const rec = reader.getField(legacyFieldItemId(tab, i, field, subPanel))
      if (!rec) continue
      if (field === 'conclusion') {
        if (rec.conclusion != null) row.conclusion = rec.conclusion
      } else if (rec.remark != null) {
        row[field] = rec.remark
      }
      // wp_ref 只在 nochange 行用作日期，保留原语义
      if (field === 'nochange' && rec.wp_ref != null) {
        row.nochangeDate = rec.wp_ref
      }
    }
    const attrsRec = reader.getField(
      legacyFieldItemId(tab, i, 'attrs', subPanel),
    )
    if (attrsRec?.remark) {
      try {
        row.attrs = JSON.parse(attrsRec.remark)
      } catch {
        /* 非法 JSON 丢弃 attrs，其余字段照迁 */
      }
    }
    rows.push(row)
  }
  return rows
}
