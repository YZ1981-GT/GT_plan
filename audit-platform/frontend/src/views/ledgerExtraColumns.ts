/**
 * 凭证/序时账明细「非关键列」动态列构建 — 纯函数（组件与单测共用同一份，避免 copy 漂移）
 *
 * 后端 ledger_penetration_service 的凭证/序时账查询已为每条分录透出一个 `extra_fields`
 * 对象（导入时的非关键列，已过滤 `_` 前缀系统标记，无值时为 `{}`）。前端明细表格需要把
 * 这些额外字段作为动态列显示，列集合取「本批分录 extra_fields 键的并集」。
 *
 * 关键不变式（Property 6）：
 *  - 返回本批所有分录 extra_fields 键的并集；
 *  - 保持键首次出现的顺序（对齐 Python dict 插入序 = 导入列序）；
 *  - 去重（同一键只出现一次）；
 *  - 全部为空 / items 为空 → 返回 []；
 *  - 部分行缺 extra_fields（undefined/缺字段）→ 跳过不报错。
 */

/** 本批分录 extra_fields 键并集，保持首次出现顺序、去重、全空返回 []。 */
export function buildExtraColumns(
  items: Array<{ extra_fields?: Record<string, unknown> }>,
): string[] {
  const seen = new Set<string>()
  const cols: string[] = []
  for (const it of items ?? []) {
    const ef = it?.extra_fields
    if (!ef) continue
    for (const k of Object.keys(ef)) {
      if (!seen.has(k)) {
        seen.add(k)
        cols.push(k)
      }
    }
  }
  return cols
}

/**
 * 额外列单元格取值格式化（非标量值防御）— 纯函数（组件与单测共用）。
 *
 * 真实 extra_fields 值多为标量（string/number/bool），但历史脏数据或嵌套 JSON
 * 可能是 object/array，直接 `String(v)` 会渲染成 `[object Object]`。此处：
 *  - null / undefined → 空串（缺失单元格）；
 *  - object / array → `JSON.stringify`（可读、可复制、不再 [object Object]）；
 *  - 其余标量 → `String(v)`。
 */
export function fmtExtraCell(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}

/**
 * 额外列显隐过滤 — 纯函数（组件与单测共用）。
 *
 * @param allKeys  本批 extra_fields 键并集（buildExtraColumns 产出）
 * @param prefs    列显隐偏好 map（键 → 是否显示）；未在 map 中的键默认显示（true）
 * @returns        prefs[k] !== false 的键（保持原顺序）
 */
export function visibleExtraColumns(
  allKeys: string[],
  prefs: Record<string, boolean> = {},
): string[] {
  return (allKeys ?? []).filter((k) => prefs[k] !== false)
}

/**
 * 构建复制到剪贴板的 Tab 分隔表（固定字段列 + extra_fields 业务键展开列）— 纯函数（组件与单测共用）。
 *
 * - 排除内部字段（`_` 前缀）与传入的 excludeKeys（含 raw_extra / extra_fields 对象本身，避免 [object Object]）；
 * - extra_fields 的业务键（本批键并集，保序，复用 buildExtraColumns）展开为额外列，缺失写空；
 * - header = 固定列 + 额外列（Tab 分隔）；每行 = 固定值 + 额外值（Tab 分隔）。
 */
export function buildClipboardTable(
  rows: Array<Record<string, any>>,
  excludeKeys: Iterable<string> = [],
): { header: string; lines: string[]; baseKeys: string[]; extraKeys: string[] } {
  if (!rows || rows.length === 0) return { header: '', lines: [], baseKeys: [], extraKeys: [] }
  const exclude = new Set<string>(excludeKeys)
  const baseKeys = Object.keys(rows[0]).filter((k) => !exclude.has(k) && !k.startsWith('_'))
  const extraKeys = buildExtraColumns(rows as Array<{ extra_fields?: Record<string, unknown> }>)
  const header = [...baseKeys, ...extraKeys].join('\t')
  const lines = rows.map((r) => {
    const baseVals = baseKeys.map((k) => {
      const v = r[k]
      return v == null ? '' : String(v)
    })
    const extraVals = extraKeys.map((k) => fmtExtraCell(r?.extra_fields?.[k]))
    return [...baseVals, ...extraVals].join('\t')
  })
  return { header, lines, baseKeys, extraKeys }
}
