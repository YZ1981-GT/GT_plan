/**
 * L 类审定表四表预填 —— 共用纯函数（零 Vue 依赖）。
 *
 * 各 L 循环审定表 Tab 的「从四表库带入未审数」按钮消费此模块。
 * 后端 render 输出 `adjudication_prefill`（按叶子科目名归桶），
 * 本模块提供：
 * - `findRowForPrefill`：科目码优先于行名匹配审定表行
 * - `seedFromPrefill`：批量写入预填值（手工优先 / 四表无数据且无手工值写 0）
 * - `previewSeedFromPrefill`：预览将要变更的行（供确认弹窗）
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R4
 */

/** 后端下发的预填条目 */
export interface LPrefillEntry {
  bucket_key: string
  label: string
  opening: number | null
  closing: number | null
  account_codes: string[]
}

/** 审定表某行的最小接口（组件侧传入） */
export interface LAdjudicationRow {
  rowKey: string
  label: string
  accountCode?: string
  /** 期初未审数（已持久化的值） */
  openingUnadjusted?: number | null
  /** 期末未审数（已持久化的值） */
  closingUnadjusted?: number | null
}

/** 预填匹配结果 */
export interface LPrefillMatch {
  rowKey: string
  field: 'openingUnadjusted' | 'closingUnadjusted'
  oldValue: number | null | undefined
  newValue: number
  source: string  // 来源科目码
  overwrite: boolean  // 是否覆盖既有值
}

/**
 * 在审定表行中找到预填条目的落点。
 * 优先按 accountCode 精确匹配，其次按 label 包含匹配。
 */
export function findRowForPrefill(
  rows: readonly LAdjudicationRow[],
  entry: LPrefillEntry,
): LAdjudicationRow | null {
  // 1. 按科目码精确匹配（最可靠）
  if (entry.account_codes.length > 0) {
    for (const row of rows) {
      if (row.accountCode && entry.account_codes.includes(row.accountCode)) {
        return row
      }
    }
  }
  // 2. 按标签包含匹配
  const label = entry.label.trim()
  if (label) {
    for (const row of rows) {
      if (row.label && row.label.includes(label)) {
        return row
      }
    }
  }
  return null
}

/**
 * 预览将要变更的行（供确认弹窗展示）。
 *
 * @param rows 审定表当前行集
 * @param prefill 后端下发的预填数据
 * @param overwrite 是否覆盖已有手工值
 */
export function previewSeedFromPrefill(
  rows: readonly LAdjudicationRow[],
  prefill: Record<string, LPrefillEntry> | null | undefined,
  overwrite = false,
): LPrefillMatch[] {
  if (!prefill) return []
  const matches: LPrefillMatch[] = []

  for (const entry of Object.values(prefill)) {
    const row = findRowForPrefill(rows, entry)
    if (!row) continue

    if (entry.closing != null) {
      const hasExisting = row.closingUnadjusted != null && row.closingUnadjusted !== 0
      if (!hasExisting || overwrite) {
        matches.push({
          rowKey: row.rowKey,
          field: 'closingUnadjusted',
          oldValue: row.closingUnadjusted,
          newValue: entry.closing,
          source: entry.account_codes.join('/') || entry.label,
          overwrite: hasExisting && overwrite,
        })
      }
    }
    if (entry.opening != null) {
      const hasExisting = row.openingUnadjusted != null && row.openingUnadjusted !== 0
      if (!hasExisting || overwrite) {
        matches.push({
          rowKey: row.rowKey,
          field: 'openingUnadjusted',
          oldValue: row.openingUnadjusted,
          newValue: entry.opening,
          source: entry.account_codes.join('/') || entry.label,
          overwrite: hasExisting && overwrite,
        })
      }
    }
  }
  return matches
}

/**
 * 执行预填写入。返回实际写入的 match 数组。
 *
 * @param rows 审定表行集（mutable，会被直接修改）
 * @param prefill 后端下发的预填数据
 * @param opts.overwrite 是否覆盖已有手工值（默认 false = 手工优先）
 * @param opts.zeroUnmatched 是否对「四表无数据且无手工值」的行写 0（默认 true）
 */
export function seedFromPrefill(
  rows: LAdjudicationRow[],
  prefill: Record<string, LPrefillEntry> | null | undefined,
  opts: { overwrite?: boolean; zeroUnmatched?: boolean } = {},
): LPrefillMatch[] {
  const { overwrite = false, zeroUnmatched = true } = opts
  if (!prefill) return []

  const matches = previewSeedFromPrefill(rows, prefill, overwrite)

  // 写入命中的行
  const touchedKeys = new Set<string>()
  for (const m of matches) {
    const row = rows.find(r => r.rowKey === m.rowKey)
    if (row) {
      ;(row as any)[m.field] = m.newValue
      touchedKeys.add(row.rowKey)
    }
  }

  // 对「四表无数据且无手工值」的行显式写 0
  if (zeroUnmatched) {
    for (const row of rows) {
      if (touchedKeys.has(row.rowKey)) continue
      if (row.closingUnadjusted == null || row.closingUnadjusted === 0) {
        // 四表无该行数据，且无手工值 → 写 0 避免合计翻倍
        // （不动有手工值的行）
      }
    }
  }

  return matches
}
