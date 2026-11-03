/** GtGridCell 与它托管的编辑器之间的约定（spec excel-style-table-editing ADR-6）。 */
import type { InjectionKey } from 'vue'
import type { CellEditorHandle } from './editorHost'

export interface GridCellHost {
  register(handle: CellEditorHandle): void
  unregister(id: string): void
  /** 托管的编辑器自己结束（失焦提交、下拉选定）时通知 GtGridCell。 */
  finished(handle: CellEditorHandle, value: unknown, refocus: boolean): void
}

export const GRID_CELL_KEY: InjectionKey<GridCellHost> = Symbol('GtGridCell')
