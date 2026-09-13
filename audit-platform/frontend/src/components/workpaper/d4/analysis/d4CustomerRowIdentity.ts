/**
 * D4-9 客户行稳定身份（rowId）工具 —— 单一真源。
 *
 * spec: d4-9-customer-structure-bidirectional-writeback / Task 2 (Requirement 3)
 *
 * 结构化视图、历史数据迁移、导入路径（Task 10）共用同一套身份规则：
 * - rowId 非数组下标，区域内唯一；
 * - 缺失或重复即补新 id（不静默合并、不退回下标）；
 * - 迁移保留既有手工值（name/amount/quantity/priorRank）。
 */

export interface D4CustomerRow {
  rowId: string
  name: string
  amount: number
  quantity: number
  priorRank: string
  [k: string]: unknown
}

/** 稳定行 id：crypto.randomUUID 优先，退化到时间戳+随机（同会话内不撞）。 */
export function newRowId(): string {
  const c = (globalThis as unknown as { crypto?: { randomUUID?: () => string } }).crypto
  if (c?.randomUUID) return c.randomUUID()
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/**
 * 给一组行补齐稳定 rowId，区域内去重。
 * @returns rows（补齐后的新数组）+ changed（是否发生迁移，用于一次性持久化）
 */
export function migrateRowIds<T extends Partial<D4CustomerRow>>(
  rows: T[] | null | undefined,
): { rows: (T & { rowId: string })[]; changed: boolean } {
  let changed = false
  const seen = new Set<string>()
  const out = (rows || []).map((r) => {
    let id = typeof r?.rowId === 'string' ? r.rowId : ''
    if (!id || seen.has(id)) {
      id = newRowId()
      changed = true
    }
    seen.add(id)
    return { ...r, rowId: id }
  })
  return { rows: out, changed }
}
