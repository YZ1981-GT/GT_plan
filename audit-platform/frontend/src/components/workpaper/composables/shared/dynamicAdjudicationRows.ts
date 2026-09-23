/**
 * 审定表动态明细行 —— 平台级共享件（零 Vue 依赖纯函数）。
 *
 * **为什么要有它**
 *
 * 源模板对多数审定表的明细项目都写着「根据实际情况列示；不存在的项目请删除」
 * （K2 上市披露 sheet A5 逐字），但历史实现普遍把项目行**硬编码成固定枚举** ——
 * 客户实际没有的项目占着行、实际有的项目无处填，四表预填还得靠「模糊包含匹配 +
 * 兜底塞进『其他』行」，一旦不匹配就把别的科目金额堆到错误行上（K2 实测把三行
 * 坏账准备全堆进「其他」）。
 *
 * 本模块把「动态行」抽成与循环无关的纯函数：行清单序列化 / 反序列化、`rowId` 生成、
 * 重名判定、历史固定行迁移、四表 seed、行键收集与清理。**循环差异全部由入参
 * `DynamicRowsSpec` 声明**（前缀 / 清单 itemId / 历史 rowKey / 金额字段 / 外来行警示），
 * 模块内不含任何循环专属常量 —— 第 N 个循环接入时只写一份 spec 声明。
 *
 * 与 `checklist_responses` 的关系::
 *
 *     {prefix}-rows            → JSON 行清单 [{rowId, label, source, accountCode}]
 *     {prefix}-{rowId}-{field} → 该行各列的值（begin/debit/credit/unadj/aje/rje/remark…）
 *
 * 历史固定行迁移时 **`rowId` 沿用旧 rowKey** → `{prefix}-{旧rowKey}-{field}` 键原样命中，
 * 零丢数（这是「只增不删」的关键）。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.1
 *       Requirements 2.1, 2.4, 2.5, 2.6 / Property 5, 6, 7, 8
 */

/** 行来源：四表库 seed / 手工新增 / 历史固定行迁移 */
export type DynamicRowSource = 'tb' | 'manual' | 'legacy'

export interface DynamicAdjRow {
  /** 行标识（持久化键的组成部分，创建后不再变；历史行沿用旧 rowKey） */
  rowId: string
  /** 行名（审计师可改） */
  label: string
  source: DynamicRowSource
  /** 仅 `source==='tb'` 时有值，供溯源展示 */
  accountCode?: string
  /**
   * 派生行（`source==='tb'`）最近一次由上游派生写入 store 的各字段值（选项 b 覆盖状态机的
   * 第三个量 `snap`，见 spec d4-html-to-oo-store-contract-alignment 裁决 D4）。
   * `resolveCellState`（Task 13）用 `stored`/`snap`/`derived` 三者判 S1~S4。
   */
  derivedSnapshot?: Record<string, number | null>
  /**
   * 随行落库的金额值（Task 8 起，仅 `serializeRows(rows, {reader})` 形态写入）——
   * **平铺在行对象顶层**（如 `currentUnadjusted: 153431246.16`），与后端契约一致：
   * `build_store_projection_d41` 读的正是 `row.get(store_key)` 顶层键。既有四键形态下不出现。
   * 用索引签名承载这些动态字段（字段名 = `spec.valueFields`）。
   */
  [field: string]: unknown
}

/** 四表库预填候选（后端 `adjudication_prefill` 的形态） */
export interface DynamicRowPrefillItem {
  name: string
  code?: string
  opening_balance?: number
  closing_balance?: number
}

/** 历史固定行声明（迁移用） */
export interface LegacyFixedRow {
  /** 旧 rowKey —— 迁移后作为 `rowId` 沿用，保证既有持久化键命中 */
  key: string
  label: string
}

/**
 * 某循环的动态行规格（调用方声明，纯数据）。
 */
export interface DynamicRowsSpec {
  /** 持久化键前缀（如 `K2-1`） */
  prefix: string
  /** 历史固定行（迁移源；无历史实现时传 `[]`） */
  legacyRows: readonly LegacyFixedRow[]
  /**
   * 迁移判定用的金额字段集：这些字段任一非零即认为该历史行「有数据」，必须保留。
   * 例：`['begin','debit','credit','unadj','aje','rje']`
   */
  valueFields: readonly string[]
}

/** 行清单 itemId */
export function rowsItemId(spec: DynamicRowsSpec): string {
  return `${spec.prefix}-rows`
}

/** 某行某字段的 itemId */
export function rowFieldItemId(spec: DynamicRowsSpec, rowId: string, field: string): string {
  return `${spec.prefix}-${rowId}-${field}`
}

/** 该行全部字段键的公共前缀（删除时按此前缀清理） */
export function rowKeyPrefix(spec: DynamicRowsSpec, rowId: string): string {
  return `${spec.prefix}-${rowId}-`
}

// ─── 行名规范化与重名判定 ────────────────────────────────────────────────────

/**
 * 行名规范化 —— 去首尾空白 + **压缩内部空白**。
 *
 * 🔴 源模板行名常带全/半角空格（「合 计」「合　计」），不压缩会让「押金保证金」与
 * 「押金 保证金」被判为两行不同名 → 撞名校验失效、按行名带入时匹配不上。
 */
export function normalizeLabel(label: string | null | undefined): string {
  return String(label ?? '').replace(/[\s\u3000]+/g, ' ').trim()
}

/** 行名比较键（规范化 + 去掉全部空白，用于撞名判定） */
export function labelKey(label: string | null | undefined): string {
  return normalizeLabel(label).replace(/\s+/g, '')
}

/**
 * 找出与 `label` 撞名的现有行（排除 `exceptRowId` 自身，供改名场景用）。
 * 返回撞名的行，无撞名返回 `null`。
 */
export function findDuplicateLabel(
  rows: readonly DynamicAdjRow[],
  label: string,
  exceptRowId?: string,
): DynamicAdjRow | null {
  const key = labelKey(label)
  if (!key) return null
  for (const r of rows || []) {
    if (exceptRowId && r.rowId === exceptRowId) continue
    if (labelKey(r.label) === key) return r
  }
  return null
}

// ─── rowId 生成 ──────────────────────────────────────────────────────────────

/**
 * 生成新 `rowId`（在 `rows` 内唯一）。
 *
 * 形态 `r-{base36 随机}`；理论碰撞时追加后缀直到唯一（纯函数可测，不依赖时间戳精度）。
 */
export function nextRowId(
  rows: readonly DynamicAdjRow[],
  rand: () => number = Math.random,
): string {
  const used = new Set((rows || []).map((r) => r.rowId))
  for (let attempt = 0; attempt < 64; attempt++) {
    const id = `r-${Math.floor(rand() * 0x7fffffff).toString(36)}`
    if (!used.has(id)) return id
  }
  // 兜底：线性探测（保证函数必返唯一 id）
  let i = 0
  while (used.has(`r-x${i}`)) i++
  return `r-x${i}`
}

// ─── 序列化 / 反序列化 ───────────────────────────────────────────────────────

/** 行清单 → 持久化字符串（只落 4 个字段，派生列一律读时推导） */
/**
 * 序列化时把 `valueFields` 一并落进行对象所需的读取器。
 *
 * 组件传入（共享件不认识 `allResponses`，保持它对存储介质无知）：给定 rowId + field，
 * 返回该格当前值（`number | null`）。返回 `null`（或 undefined）表示该格无值、不落该键。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 8 · 裁决 D2/D3
 */
export interface SerializeRowsValueReader {
  /** 读某行某金额字段的当前值。`null`/`undefined` = 该格无值。 */
  readField(rowId: string, field: string): number | null | undefined
  /**
   * 可选：把行的 `derivedSnapshot`（最近一次由派生写入 store 的各字段值）一并落库。
   * 仅 `source==='tb'` 的派生行需要（选项 b 覆盖状态机的第三个量，见 spec 裁决 D4）。
   * 返回 `null` 表示该行无快照、不落 `derivedSnapshot` 键。
   */
  readDerivedSnapshot?(rowId: string): Record<string, number | null> | null
}

/**
 * 行清单 → 持久化字符串。
 *
 * **两种调用形态**（Task 8 起）：
 *
 * * `serializeRows(rows)` —— **既有行为，逐字节不变**：只落 `{rowId,label,source,accountCode}`
 *   四键，派生列读时推导。D1/J1 等自带另一套 serialize 的消费方与本形态无关；K2 若不需要
 *   金额落库也走这条。P10 基线（`dynamicAdjRowsBackcompatBaseline.spec.ts`）冻结这条路径。
 *
 * * `serializeRows(rows, { readField, readDerivedSnapshot? })` —— **金额随行落库**（D4-1 选项 b
 *   的存储载体）：在四键基础上，为 `spec.valueFields` 每个字段追加 `number` 值键（值经
 *   `readField` 取、`null`/`undefined` 的字段不落键）；`source==='tb'` 且提供了
 *   `readDerivedSnapshot` 时追加 `derivedSnapshot`。
 *
 * 🔴 金额写成 `number`（不是字符串）：per-field item 是纯文本 remark，但行对象里的金额是
 * 结构化 JSON 值，后端 `merge.normalize_value` 对 amount 接受数字、对 text 拒绝数字。写入前
 * 用 `Number()` 归一（与 `readNum` 同源口径），非有限值落 `null` 而非 `NaN`/字符串。
 */
export function serializeRows(
  rows: readonly DynamicAdjRow[],
  options?: { spec?: DynamicRowsSpec; reader?: SerializeRowsValueReader },
): string {
  const reader = options?.reader
  const valueFields = options?.spec?.valueFields ?? []
  return JSON.stringify(
    (rows || []).map((r) => {
      const out: DynamicAdjRow & Record<string, unknown> = {
        rowId: r.rowId,
        label: normalizeLabel(r.label),
        source: r.source,
      }
      if (r.accountCode) out.accountCode = r.accountCode
      if (reader) {
        for (const field of valueFields) {
          const raw = reader.readField(r.rowId, field)
          if (raw == null) continue
          const n = Number(raw)
          if (Number.isFinite(n)) out[field] = n
        }
        if (r.source === 'tb' && reader.readDerivedSnapshot) {
          const snap = reader.readDerivedSnapshot(r.rowId)
          if (snap && Object.keys(snap).length > 0) {
            const clean: Record<string, number | null> = {}
            for (const [k, v] of Object.entries(snap)) {
              clean[k] = v == null || !Number.isFinite(Number(v)) ? null : Number(v)
            }
            out.derivedSnapshot = clean
          }
        }
      }
      return out
    }),
  )
}

/**
 * 持久化字符串 → 行清单。
 *
 * 容错：非 JSON / 非数组 / 元素缺 `rowId` 或 `label` 一律跳过（不白屏）；
 * `rowId` 重复时保留首次出现者。
 */
export function deserializeRows(raw: unknown): DynamicAdjRow[] {
  if (typeof raw !== 'string' || !raw.trim()) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []
  const out: DynamicAdjRow[] = []
  const seen = new Set<string>()
  /** 行对象的**结构性**键（非金额值键）——透传金额时跳过它们。 */
  const STRUCT_KEYS = new Set(['rowId', 'label', 'source', 'accountCode', 'derivedSnapshot'])
  for (const item of parsed) {
    if (!item || typeof item !== 'object') continue
    const rec = item as Record<string, unknown>
    const rowId = String(rec.rowId ?? '').trim()
    const label = normalizeLabel(rec.label as string)
    if (!rowId || seen.has(rowId)) continue
    seen.add(rowId)
    const source = rec.source
    const row: DynamicAdjRow = {
      rowId,
      label,
      source:
        source === 'tb' || source === 'legacy' || source === 'manual'
          ? source
          : 'manual',
    }
    const code = String(rec.accountCode ?? '').trim()
    if (code) row.accountCode = code
    // 🔴 透传随行落库的金额值（Task 8 起）：任何非结构键且值为有限数字的字段原样带出，
    //    供 Task 9 的单源读优先命中。既有四键形态下无这些键，行为不变。
    for (const [k, v] of Object.entries(rec)) {
      if (STRUCT_KEYS.has(k)) continue
      const n = Number(v)
      if (v != null && Number.isFinite(n)) row[k] = n
    }
    // derivedSnapshot（派生行的 snap；只对象形态才带）。
    const snap = rec.derivedSnapshot
    if (snap && typeof snap === 'object' && !Array.isArray(snap)) {
      const clean: Record<string, number | null> = {}
      for (const [k, v] of Object.entries(snap as Record<string, unknown>)) {
        clean[k] = v == null || !Number.isFinite(Number(v)) ? null : Number(v)
      }
      row.derivedSnapshot = clean
    }
    out.push(row)
  }
  return out
}

// ─── 读值助手（`checklist_responses` 形态兼容） ───────────────────────────────

/** 从 `allResponses` 取原始串（兼容 `{remark}` / `{conclusion}` / 裸字符串三形态） */
export function readRaw(
  responses: Map<string, unknown> | null | undefined,
  itemId: string,
): string {
  const item = responses?.get(itemId) as Record<string, unknown> | string | undefined
  if (item == null) return ''
  if (typeof item === 'string') return item
  const remark = (item as Record<string, unknown>).remark
  if (remark != null && remark !== '') return String(remark)
  const conclusion = (item as Record<string, unknown>).conclusion
  return conclusion == null ? '' : String(conclusion)
}

/** 从 `allResponses` 取数值（非数/空 → 0） */
export function readNum(
  responses: Map<string, unknown> | null | undefined,
  itemId: string,
): number {
  const n = Number(readRaw(responses, itemId))
  return Number.isFinite(n) ? n : 0
}

/**
 * 单源读某行某金额字段：**行对象顶层值优先，缺则回落 per-field item**。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 9 · 裁决 D3 · Requirement 4.1/4.2
 *
 * ═══ 为什么行对象优先（不是 per-field 优先）═══
 *
 * Task 8 起 `D4-1-rows` 的行对象可携带金额（选项 b 的存储载体，也是 OO 回写的落点：
 * `merge_projection_into_d41_rows` 写进行对象）。若反过来 per-field 优先，OO 侧改的值会
 * 永远被旧 per-field 值盖住（缺陷 A2 的反向翻版）。所以行对象值一旦存在即为权威。
 *
 * ═══ 为什么必须有 per-field 回落（不是直接只读行对象）═══
 *
 * 既有项目的金额只落在 per-field item `{prefix}-{rowId}-{field}`（行对象里没有金额键）。
 * 双写迁移期（裁决 D3）行对象值渐次补齐，未补齐的行必须回落 per-field，否则旧项目金额归零
 * （需求 4.2 的迁移不归零）。回落读用 `readNum`（非数/空 → 0）保持既有语义。
 *
 * 判定「行对象是否有该字段值」：顶层键存在且为**有限数字**。写成 `null` 的字段（序列化时
 * 显式落 null 的极少数场景）视为"无值"、回落 per-field —— 与 serializeRows 的 `raw==null`
 * 不落键口径对称。
 */
export function readRowFieldWithFallback(
  row: DynamicAdjRow | null | undefined,
  responses: Map<string, unknown> | null | undefined,
  spec: DynamicRowsSpec,
  field: string,
): number {
  if (row) {
    const direct = (row as Record<string, unknown>)[field]
    if (direct != null) {
      const n = Number(direct)
      if (Number.isFinite(n)) return n
    }
  }
  const rid = row?.rowId ?? ''
  if (!rid) return 0
  return readNum(responses, rowFieldItemId(spec, rid, field))
}

// ─── 选项 b 逐格覆盖状态机（Task 13）───────────────────────────────────────────

/** 派生行某格的四态（spec d4-html-to-oo-store-contract-alignment 裁决 D4 / 需求 6.2）。 */
export type DerivedCellState = 'S1' | 'S2' | 'S3' | 'S4'

/** 金额相等判定的容差（与前端 BALANCE_TOLERANCE / 后端 0.005 同口径）。 */
export const CELL_VALUE_TOLERANCE = 0.005

function _finiteOrNull(v: number | null | undefined): number | null {
  if (v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 两个量在容差内是否相等。**null 语义**：两者都为 null 视为相等（都"无值"）；
 * 一方 null 一方有值视为不等（出现/消失也是一种变化）。
 */
function _eq(a: number | null, b: number | null): boolean {
  if (a == null && b == null) return true
  if (a == null || b == null) return false
  return Math.abs(a - b) <= CELL_VALUE_TOLERANCE
}

/**
 * 派生行某格的四态解析（选项 b 覆盖状态机的**唯一**判定实现）。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 13 · Requirement 6.1/6.2 · Property 11/12
 *
 * 三个量（见裁决 D4）：
 *   - `stored`  = 行对象/per-field 里该格当前值（可能被 OO 回写改过）；
 *   - `snap`    = derivedSnapshot 里该字段值（最近一次由派生写入 store 的值）；
 *   - `derived` = 当前现算派生值（crossSheet computed）。
 *
 * | 态 | stored vs snap | snap vs derived | 含义 |
 * |---|---|---|---|
 * | S1 | = | = | 纯派生（显示 derived，无标记） |
 * | S2 | ≠ | = | 人工覆盖、上游未变（显示 stored + 「已人工覆盖」） |
 * | S3 | = | ≠ | 无覆盖、上游已变（自动跟随，把 stored/snap 推到 derived） |
 * | S4 | ≠ | ≠ | 覆盖 且 上游已变（双值可见 + 恢复取数） |
 *
 * 🔴 覆盖判定基于 `stored vs snap`（**不是** `stored vs derived`）—— 需求 6.1 明令：
 * 用 `stored ≠ derived` 判覆盖会在上游一变时把**所有**纯派生格误判成人工覆盖。
 * 本函数以 snap 为"上一次派生的锚点"，故上游变化（snap≠derived）与人工覆盖
 * （stored≠snap）是两个正交维度，四态穷举封闭、无第五态。
 */
export function resolveCellState(
  stored: number | null | undefined,
  snap: number | null | undefined,
  derived: number | null | undefined,
): DerivedCellState {
  const s = _finiteOrNull(stored)
  const p = _finiteOrNull(snap)
  const d = _finiteOrNull(derived)
  const overridden = !_eq(s, p) // stored ≠ snap ⇒ 被人工覆盖
  const upstreamChanged = !_eq(p, d) // snap ≠ derived ⇒ 上游已变
  if (!overridden && !upstreamChanged) return 'S1'
  if (overridden && !upstreamChanged) return 'S2'
  if (!overridden && upstreamChanged) return 'S3'
  return 'S4'
}

/**
 * 某格应当**显示**的值（按四态）：S1/S3 用 derived（跟随上游），S2/S4 用 stored（覆盖值）。
 *
 * 注意 S3 显示 derived 是"自动跟随"的**显示侧**语义；把 stored/snap 真正推到 derived 的
 * **落库**动作由调用方（syncDerivedRowsIntoStore）幂等完成，二者一致。
 */
export function displayValueForCellState(
  state: DerivedCellState,
  stored: number | null | undefined,
  derived: number | null | undefined,
): number {
  const s = _finiteOrNull(stored)
  const d = _finiteOrNull(derived)
  if (state === 'S2' || state === 'S4') return s ?? 0
  return d ?? 0
}

// ─── 历史固定行迁移 ──────────────────────────────────────────────────────────

/**
 * 历史固定行 → 动态行清单（迁移，**只增不删**）。
 *
 * 规则：
 * - `rowId` 沿用旧 rowKey → `{prefix}-{rowKey}-{field}` 键原样命中，金额零丢失。
 * - 只迁移**有数据**的行（`valueFields` 任一非零，或 `remark` 非空）——
 *   从未填过的固定行不该在新模型里占位（宁缺勿造）。
 * - 全部固定行都无数据 → 返回 `[]`（交由四表 seed 或手工新增）。
 */
export function migrateLegacyFixedRows(
  spec: DynamicRowsSpec,
  responses: Map<string, unknown> | null | undefined,
): DynamicAdjRow[] {
  const out: DynamicAdjRow[] = []
  for (const legacy of spec.legacyRows || []) {
    if (!hasLegacyRowData(spec, responses, legacy.key)) continue
    out.push({
      rowId: legacy.key,
      label: normalizeLabel(legacy.label),
      source: 'legacy',
    })
  }
  return out
}

/** 该历史固定行是否已有录入（金额任一非零或备注非空） */
export function hasLegacyRowData(
  spec: DynamicRowsSpec,
  responses: Map<string, unknown> | null | undefined,
  rowKey: string,
): boolean {
  for (const f of spec.valueFields || []) {
    if (readNum(responses, rowFieldItemId(spec, rowKey, f)) !== 0) return true
  }
  return readRaw(responses, rowFieldItemId(spec, rowKey, 'remark')).trim() !== ''
}

// ─── 四表库 seed ─────────────────────────────────────────────────────────────

export interface SeedFromPrefillResult {
  /** 新建的行（已并入 `rows` 之后的完整清单由调用方组装） */
  rows: DynamicAdjRow[]
  /** 要写入的字段值 `{itemId: 字符串值}`（调用方负责持久化 + 手工优先判定） */
  values: Record<string, string>
  /** 本次新建的 rowId（其余为命中已有行） */
  createdRowIds: string[]
  /** 本次带入涉及的 rowId → 该行是否由四表库承载（供调用方判「可否刷新覆盖」） */
  touchedRowIds: string[]
}

/**
 * 在现有清单里为某个预填项找对应行 —— **先按科目码，再按行名**。
 *
 * 🔴 按科目码优先是「刷新取数」能用的前提：审计师把四表带入的行改名后
 * （如把科目全名改成披露口径的简称），只按行名匹配会再建一行重复行。
 */
export function findRowForPrefill(
  rows: readonly DynamicAdjRow[],
  item: DynamicRowPrefillItem,
): DynamicAdjRow | null {
  const code = String(item?.code ?? '').trim()
  if (code) {
    const byCode = (rows || []).find((r) => r.accountCode === code)
    if (byCode) return byCode
  }
  return findDuplicateLabel(rows, normalizeLabel(item?.name))
}

/**
 * 四表库预填 → 动态行 + 字段值。
 *
 * **宁缺勿造**：预填为空 / 科目名为空 → 返回空结果，**不产生兜底行**
 * （旧实现「未匹配一律塞进『其他』」是把别的科目金额堆到错误行的根因）。
 *
 * **动态插行 + 刷新取数**：四表库新增明细子科目 → 自动补出新行；已存在的行
 * （按科目码优先匹配，改名不失联）只更新金额、不重复建行。是否覆盖已有值由**调用方**
 * 按 `touchedRowIds` + 行 `source` 决定（手工行永不覆盖）。
 *
 * @param spec 循环声明
 * @param prefill 后端 `adjudication_prefill`
 * @param existing 现有动态行清单
 * @param fields 期初 / 未审 字段名（默认 `begin` / `unadj`）
 */
export function seedRowsFromPrefill(
  spec: DynamicRowsSpec,
  prefill: readonly DynamicRowPrefillItem[] | null | undefined,
  existing: readonly DynamicAdjRow[] = [],
  fields: { opening?: string; closing?: string } = {},
  rand: () => number = Math.random,
): SeedFromPrefillResult {
  const openingField = fields.opening ?? 'begin'
  const closingField = fields.closing ?? 'unadj'
  const rows: DynamicAdjRow[] = [...(existing || [])]
  const values: Record<string, string> = {}
  const createdRowIds: string[] = []
  const touchedRowIds: string[] = []
  if (!prefill || prefill.length === 0) {
    return { rows: [...(existing || [])], values, createdRowIds, touchedRowIds }
  }

  for (const p of prefill) {
    const label = normalizeLabel(p?.name)
    if (!label) continue
    let row = findRowForPrefill(rows, p)
    if (!row) {
      row = {
        rowId: nextRowId(rows, rand),
        label,
        source: 'tb',
        ...(p.code ? { accountCode: String(p.code) } : {}),
      }
      rows.push(row)
      createdRowIds.push(row.rowId)
    } else if (p.code && !row.accountCode) {
      // 命中的是「同名手工/历史行」→ 回填科目码，下次刷新即可按码定位
      const idx = rows.indexOf(row)
      row = { ...row, accountCode: String(p.code) }
      rows[idx] = row
    }
    if (!touchedRowIds.includes(row.rowId)) touchedRowIds.push(row.rowId)
    const opening = Number(p?.opening_balance) || 0
    const closing = Number(p?.closing_balance) || 0
    values[rowFieldItemId(spec, row.rowId, openingField)] = String(opening)
    values[rowFieldItemId(spec, row.rowId, closingField)] = String(closing)
  }
  return { rows, values, createdRowIds, touchedRowIds }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

export interface DropRowResult {
  rows: DynamicAdjRow[]
  /** 需从 `allResponses` / DB 删除的 itemId（该行全部字段键） */
  removedItemIds: string[]
}

/** 收集某行在 `responses` 里实际存在的全部字段键 */
export function collectRowItemIds(
  spec: DynamicRowsSpec,
  responses: Map<string, unknown> | null | undefined,
  rowId: string,
): string[] {
  const prefix = rowKeyPrefix(spec, rowId)
  const out: string[] = []
  for (const key of responses?.keys() ?? []) {
    if (typeof key === 'string' && key.startsWith(prefix)) out.push(key)
  }
  return out.sort()
}

/**
 * 删除某行 —— 返回新清单 + 待清理的字段键。
 *
 * 不存在该行时原样返回（幂等）。其它行的键**不受影响**（Property 7）。
 */
export function dropRow(
  spec: DynamicRowsSpec,
  rows: readonly DynamicAdjRow[],
  responses: Map<string, unknown> | null | undefined,
  rowId: string,
): DropRowResult {
  const exists = (rows || []).some((r) => r.rowId === rowId)
  if (!exists) return { rows: [...(rows || [])], removedItemIds: [] }
  return {
    rows: (rows || []).filter((r) => r.rowId !== rowId),
    removedItemIds: collectRowItemIds(spec, responses, rowId),
  }
}

/** 改名（返回新清单；行不存在时原样返回） */
export function renameRowLabel(
  rows: readonly DynamicAdjRow[],
  rowId: string,
  label: string,
): DynamicAdjRow[] {
  const next = normalizeLabel(label)
  if (!next) return [...(rows || [])]
  return (rows || []).map((r) => (r.rowId === rowId ? { ...r, label: next } : r))
}

/** 追加手工行（不做撞名校验 —— 由调用方先用 `findDuplicateLabel` 拦） */
export function appendManualRow(
  rows: readonly DynamicAdjRow[],
  label: string,
  rand: () => number = Math.random,
): { rows: DynamicAdjRow[]; row: DynamicAdjRow } {
  const list = [...(rows || [])]
  const row: DynamicAdjRow = {
    rowId: nextRowId(list, rand),
    label: normalizeLabel(label),
    source: 'manual',
  }
  list.push(row)
  return { rows: list, row }
}

/**
 * 解析初始行清单：优先读持久化清单，其次迁移历史固定行。
 *
 * 返回 `{rows, migrated}` —— `migrated=true` 表示清单来自迁移，调用方应立即持久化，
 * 否则下次加载还要重算一遍。
 */
export function resolveInitialRows(
  spec: DynamicRowsSpec,
  responses: Map<string, unknown> | null | undefined,
): { rows: DynamicAdjRow[]; migrated: boolean } {
  const stored = deserializeRows(readRaw(responses, rowsItemId(spec)))
  if (stored.length > 0) return { rows: stored, migrated: false }
  const migrated = migrateLegacyFixedRows(spec, responses)
  return { rows: migrated, migrated: migrated.length > 0 }
}
