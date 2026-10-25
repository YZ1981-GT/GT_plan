/**
 * useB22ARowStore — B22A 行数组存储层（稳定行身份，含 legacy 自动迁移）。
 *
 * spec: b-cycle-sync-foundation-and-first-canary（BC-53）
 *
 * ═══ 设计约束：组件层 API 零改动 ═══════════════════════════════════════════
 *
 * `GtB22AControlMatrix.vue`（2661 行）大量用 `row.index` 调 setter
 * （`setConclusion(tab, row.index, ...)`）。若把组件层改成传 rowId，改动面失控。
 *
 * 故本层的职责是：**把 index 从存储键降级为显示序号**，对外仍暴露 index 语义，
 * 内部把 (tab, subPanel, index) 解析为稳定 rowId 后落进行数组。
 *
 *   组件层：setConclusion(tab, 3, '有效')        ← index 不变
 *   本层：  index 3 → rowId 'B22A-T1-...-x7f2'   ← 解析
 *   存储：  B22A-T1-rows 的第 3 个行对象 conclusion 字段
 *
 * ═══ legacy 自动迁移 ═════════════════════════════════════════════════════
 *
 * 读取时若「行数组不存在但 legacy count > 0」⇒ 当场按 legacy 下标数据迁移成行数组
 * （`migrateLegacyGroup`），并落库一次。迁移**幂等**：行数组一旦存在就不再回读 legacy。
 * 🔴 迁移只改键形状不改值（见 b22aRowIdentity.migrateLegacyGroup 注释）。
 */
import type { Ref } from 'vue'
import {
  type B22ARow,
  type LegacyReader,
  legacyCountItemId,
  legacyFieldItemId,
  makeRowId,
  migrateLegacyGroup,
  parseRows,
  resequence,
  rowScope,
  rowsItemId,
  serializeRows,
} from './b22aRowIdentity'

export interface ChecklistLike {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

export interface B22ARowStoreOptions {
  /** 全量 checklist 响应 Map（与 composable 共享同一引用）。 */
  readonly allResponses: Ref<Map<string, { conclusion?: string | null; remark?: string | null; wp_ref?: string | null }>>
  /** 落库函数。 */
  readonly saveImmediate: (items: ChecklistLike[]) => void | Promise<void>
}

export function useB22ARowStore(options: B22ARowStoreOptions) {
  const { allResponses, saveImmediate } = options

  /** 已完成 legacy 迁移的 scope 集合（防重复迁移）。 */
  const migrated = new Set<string>()

  function rawRecord(itemId: string) {
    return allResponses.value.get(itemId)
  }

  function buildLegacyReader(): LegacyReader {
    return {
      getCount: (tab, subPanel) => {
        const rec = rawRecord(legacyCountItemId(tab, subPanel))
        const n = parseInt(rec?.remark || '0', 10)
        return Number.isNaN(n) ? 0 : n
      },
      getField: (itemId) => {
        const rec = rawRecord(itemId)
        if (!rec) return undefined
        return {
          conclusion: rec.conclusion ?? null,
          remark: rec.remark ?? null,
          wp_ref: rec.wp_ref ?? null,
        }
      },
    }
  }

  /**
   * 读一组行（自动迁移 legacy）。
   *
   * 优先级：行数组存在 → 直接用；否则 legacy count > 0 → 迁移并落库；都无 → 空数组。
   */
  function readRows(tab: number | string, subPanel?: string): B22ARow[] {
    const itemId = rowsItemId(tab, subPanel)
    const scope = rowScope(tab, subPanel)
    const rec = rawRecord(itemId)

    if (rec?.remark) {
      return parseRows(rec.remark, scope)
    }

    // 行数组不存在 —— 尝试 legacy 迁移（每 scope 只做一次）
    if (!migrated.has(scope)) {
      migrated.add(scope)
      const reader = buildLegacyReader()
      if (reader.getCount(tab, subPanel) > 0) {
        const rows = migrateLegacyGroup(reader, tab, subPanel)
        if (rows.length > 0) {
          writeRows(tab, rows, subPanel)
          return rows
        }
      }
    }
    return []
  }

  /** 写一组行（落库 + 更新本地 Map）。 */
  function writeRows(
    tab: number | string,
    rows: readonly B22ARow[],
    subPanel?: string,
  ): void {
    const itemId = rowsItemId(tab, subPanel)
    const item: ChecklistLike = {
      item_id: itemId,
      conclusion: null,
      remark: serializeRows(resequence(rows)),
      wp_ref: null,
    }
    allResponses.value.set(itemId, item)
    void saveImmediate([item])
  }

  /** 追加一行，返回新行。 */
  function appendRow(
    tab: number | string,
    subPanel?: string,
    seed?: Partial<B22ARow>,
  ): B22ARow {
    const rows = readRows(tab, subPanel)
    const row: B22ARow = {
      ...seed,
      rowId: makeRowId(rowScope(tab, subPanel)),
      seq: rows.length + 1,
    }
    writeRows(tab, [...rows, row], subPanel)
    return row
  }

  /** 批量追加（套用示例控制点用），返回新增行。 */
  function appendRows(
    tab: number | string,
    seeds: readonly Partial<B22ARow>[],
    subPanel?: string,
  ): B22ARow[] {
    if (seeds.length === 0) return []
    const rows = readRows(tab, subPanel)
    const scope = rowScope(tab, subPanel)
    const created = seeds.map((seed, i) => ({
      ...seed,
      rowId: makeRowId(scope),
      seq: rows.length + i + 1,
    } as B22ARow))
    writeRows(tab, [...rows, ...created], subPanel)
    return created
  }

  /**
   * 按显示序号（1-based）删行。
   *
   * 🔴 与 legacy `removeCheckItem` 的根本差异：这里是**从数组摘除行对象**，
   * 不搬迁任何字段值 ⇒ 剩余行的 rowId ↔ 内容绑定关系不变。
   */
  function removeRowAt(
    tab: number | string,
    index: number,
    subPanel?: string,
  ): boolean {
    const rows = readRows(tab, subPanel)
    if (index < 1 || index > rows.length) return false
    const next = rows.filter((_, i) => i !== index - 1)
    writeRows(tab, next, subPanel)
    return true
  }

  /** 按显示序号取行（不存在返回 undefined）。 */
  function rowAt(
    tab: number | string,
    index: number,
    subPanel?: string,
  ): B22ARow | undefined {
    const rows = readRows(tab, subPanel)
    if (index < 1 || index > rows.length) return undefined
    return rows[index - 1]
  }

  /**
   * 按显示序号更新字段（行不存在时按需补足到该序号）。
   *
   * 补足语义与 legacy 一致：legacy 允许先写 `item-5-point` 再把 count 改成 5，
   * 组件层某些路径依赖这个宽松行为。补足产生的中间行是空行（isBlankRow 为真）。
   */
  function patchRowAt(
    tab: number | string,
    index: number,
    patch: Partial<B22ARow>,
    subPanel?: string,
  ): B22ARow | undefined {
    if (index < 1) return undefined
    const rows = readRows(tab, subPanel)
    const scope = rowScope(tab, subPanel)
    const next = [...rows]
    while (next.length < index) {
      next.push({ rowId: makeRowId(scope), seq: next.length + 1 })
    }
    const target = { ...next[index - 1], ...patch }
    next[index - 1] = target
    writeRows(tab, next, subPanel)
    return target
  }

  /** 当前行数（替代 legacy getCount）。 */
  function rowCount(tab: number | string, subPanel?: string): number {
    return readRows(tab, subPanel).length
  }

  return {
    readRows,
    writeRows,
    appendRow,
    appendRows,
    removeRowAt,
    rowAt,
    patchRowAt,
    rowCount,
    /** 测试用：暴露迁移标记以便断言幂等。 */
    __migratedScopes: migrated,
  }
}
