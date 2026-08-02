/**
 * 设定受益计划动态插行 —— 零 Vue 依赖纯函数共享件。
 *
 * 源模板的 `1、……` / `2、……` / `……` 落在父行 SUM 范围内，是真实可扩行位。
 * 本模块提供：
 *  - 稳定 key 生成（`{group}_{seq}`，禁用 label 作 key —— 源模板默认名同为 `……` 会撞键）
 *  - 父行 SUM 派生
 *  - 增删行纯函数
 *
 * 🔴 **不含任何 J2 专属字面量**（守卫反向自检），可供后续其他循环复用。
 *
 * spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
 *       Requirements 7.1~7.5 / Property 11
 */

// ─────────────────── 类型 ───────────────────

/** 一组可扩行的规格声明（由调用方按循环差异声明） */
export interface DbpDynamicSpec {
  /** 分组键：用于 key 前缀（如 `equity` / `debt` / `dbo_other`） */
  group: string
  /** 父行 key（SUM 派生）；null = 无父行（顶层可扩） */
  parentKey: string | null
  /** 源模板默认行名（`1、……` 等），仅用于 seed 提示 */
  defaultLabel: string
  /** 源模板预留位数（seed 时生成这么多空骨架行） */
  minRows: number
}

/** 一个动态行的数据模型（通用部分，具体金额字段由调用方扩展） */
export interface DbpDynamicRow {
  /** 稳定 key（`{group}_{seq}`，不因改名而变） */
  key: string
  /** 用户可编辑的行标签 */
  label: string
  /** 所属分组 */
  group: string
  /** 序号（从 1 开始，自增） */
  seq: number
}

// ─────────────────── 纯函数 ───────────────────

/** 取分组内当前最大 seq */
function _maxSeq(rows: DbpDynamicRow[], group: string): number {
  let max = 0
  for (const r of rows) {
    if (r.group === group && r.seq > max) max = r.seq
  }
  return max
}

/** 生成稳定 key：`{group}_{seq}`（两位数补零方便排序） */
export function makeRowKey(group: string, seq: number): string {
  return `${group}_${String(seq).padStart(2, '0')}`
}

/**
 * 新增一行（返回新行对象，不修改入参）。
 *
 * @param rows 当前行集
 * @param group 目标分组
 * @param label 用户输入的行名
 * @returns 新行（key 自动生成），调用方 push 到行集
 */
export function addDynamicRow(
  rows: readonly DbpDynamicRow[],
  group: string,
  label: string,
): DbpDynamicRow {
  const seq = _maxSeq([...rows], group) + 1
  return { key: makeRowKey(group, seq), label, group, seq }
}

/**
 * 删除一行（返回新数组，不修改入参）。
 *
 * @param rows 当前行集
 * @param key 要删除的行 key
 * @returns 新行集（不含该行）
 */
export function removeDynamicRow<T extends DbpDynamicRow>(
  rows: readonly T[],
  key: string,
): T[] {
  return rows.filter(r => r.key !== key)
}

/**
 * 按分组 seed 骨架行（幂等：已有该 group 的行则跳过）。
 *
 * @param existing 已有行集
 * @param spec 分组规格
 * @returns 需要追加的新行（调用方 concat）
 */
export function seedDynamicRows(
  existing: readonly DbpDynamicRow[],
  spec: DbpDynamicSpec,
): DbpDynamicRow[] {
  const hasGroup = existing.some(r => r.group === spec.group)
  if (hasGroup) return []
  const out: DbpDynamicRow[] = []
  for (let i = 1; i <= spec.minRows; i++) {
    out.push({
      key: makeRowKey(spec.group, i),
      label: spec.defaultLabel.replace(/\d+/, String(i)),
      group: spec.group,
      seq: i,
    })
  }
  return out
}

/**
 * 父行 SUM 派生：取指定分组内所有子行的某数值字段之和。
 *
 * @param rows 全部行集
 * @param group 目标分组
 * @param field 金额字段名
 * @returns 子行该字段的合计
 */
export function sumGroupField<T extends DbpDynamicRow>(
  rows: readonly T[],
  group: string,
  field: keyof T,
): number {
  let total = 0
  for (const r of rows) {
    if (r.group === group) {
      const v = r[field]
      if (typeof v === 'number' && Number.isFinite(v)) total += v
    }
  }
  return Math.round(total * 100) / 100
}

/**
 * 校验行 key 全局唯一（Property 11）。
 *
 * @returns 重复的 key 列表（为空即全部唯一）
 */
export function findDuplicateKeys(rows: readonly DbpDynamicRow[]): string[] {
  const seen = new Set<string>()
  const dupes: string[] = []
  for (const r of rows) {
    if (seen.has(r.key)) dupes.push(r.key)
    seen.add(r.key)
  }
  return dupes
}

/**
 * 行名撞名检查（新增/改名前调用）。
 *
 * @param rows 当前行集
 * @param label 待检查的名称
 * @param excludeKey 排除自身 key（改名场景）
 * @returns true = 有撞名
 */
export function hasLabelConflict(
  rows: readonly DbpDynamicRow[],
  label: string,
  excludeKey?: string,
): boolean {
  const norm = (label || '').trim()
  if (!norm) return false
  return rows.some(r => r.key !== excludeKey && (r.label || '').trim() === norm)
}
