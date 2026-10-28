/**
 * 判定一个编辑控件是不是「表体单元格编辑器」（spec excel-style-table-editing ADR-2）。
 *
 * 沿组件父链上溯，渲染前就能定论（不闪烁）：
 * - 先遇到 `TableTdWrapper` 再遇到 `ElTable` ⇒ el-table 表体单元格（Element Plus 2.13.6 每格由
 *   TableTdWrapper 渲染 <td>；展开行内容由 ElTableBody 直接 h('td') 渲染，不经过它）；
 * - 先遇到表头 / 表尾 ⇒ 不是；
 * - 先遇到弹出层内容（气泡、下拉、弹窗、抽屉）⇒ 不是 —— 弹出层在单元格里声明、却渲染在 body 上；
 * - 遇到 `GtGridCell` ⇒ 由它托管（它自己再判定一次）；
 * - 遇到 `GtGridTable` ⇒ 原生表格单元格（挂载后再按 DOM 确认在 <td> 里）。
 */
import type { ComponentInternalInstance } from 'vue'

export type CellContext =
  | { kind: 'el-table'; table: ComponentInternalInstance; td: ComponentInternalInstance }
  | { kind: 'raw-table'; grid: ComponentInternalInstance }
  | { kind: 'grid-cell'; cell: ComponentInternalInstance }

/** 弹出层「内容」组件：其中的控件虽在单元格里声明，实际渲染在 body 上，不按单元格处理。 */
export const OVERLAY_COMPONENT_NAMES: ReadonlySet<string> = new Set([
  'ElPopperContent',
  'ElTooltipContent',
  'ElDialog',
  'ElDialogContent',
  'ElDrawer',
  'ElMessageBox',
])

export const GRID_CELL_COMPONENT_NAME = 'GtGridCell'
export const GRID_TABLE_COMPONENT_NAME = 'GtGridTable'

function nameOf(instance: ComponentInternalInstance): string {
  const t = instance.type as { name?: string; __name?: string }
  return t.name || t.__name || ''
}

export function detectCellContext(instance: ComponentInternalInstance | null): CellContext | null {
  if (!instance) return null
  let td: ComponentInternalInstance | null = null
  for (let p = instance.parent; p; p = p.parent) {
    const name = nameOf(p)
    if (name === GRID_CELL_COMPONENT_NAME) return { kind: 'grid-cell', cell: p }
    if (OVERLAY_COMPONENT_NAMES.has(name)) return null
    if (name === 'TableTdWrapper') {
      if (!td) td = p
      continue
    }
    if (name === 'ElTableHeader' || name === 'ElTableFooter') return null
    if (name === 'ElTable') return td ? { kind: 'el-table', table: p, td } : null
    if (name === GRID_TABLE_COMPONENT_NAME) return { kind: 'raw-table', grid: p }
  }
  return null
}

/** 向上找最近的 ElTable 实例（GtGridCell 用来找所在表格）。 */
export function findElTableInstance(instance: ComponentInternalInstance | null): ComponentInternalInstance | null {
  for (let p = instance?.parent ?? null; p; p = p.parent) {
    const name = nameOf(p)
    if (OVERLAY_COMPONENT_NAMES.has(name)) return null
    if (name === 'ElTable') return p
  }
  return null
}

export { nameOf as componentNameOf }
