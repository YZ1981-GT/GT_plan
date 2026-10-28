/**
 * 表格坐标（spec excel-style-table-editing ADR-3）。
 *
 * 选区按「视觉坐标」：行 = 可见数据行序号，列 = 叶子列序号。合并单元格按 rowspan / colspan
 * 建占位图，被覆盖的位置指回源格。只读 DOM，不改 DOM。
 *
 * - el-table：列号 = <td> class 里的列 id 在 `store.states.columns` 中的序号（勾选列 / 展开列 /
 *   序号列也是叶子列），行 = 主表体 tbody 下可见的 `tr.el-table__row`（展开行没有这个类）。
 * - 原生表格：按 HTML 表格模型逐行放格（跳过被上方 rowspan 占住的列）。
 */

export interface CellPos {
  r: number
  c: number
}

export interface CellBox extends CellPos {
  rs: number
  cs: number
}

export interface GridGeometry {
  readonly rowCount: number
  readonly colCount: number
  /** 覆盖 (r, c) 的源格（合并单元格返回左上角那一格）。 */
  cellAt(r: number, c: number): HTMLTableCellElement | null
  /** 格的左上角坐标与跨度；不是本表的格返回 null。 */
  boxOf(td: Element): CellBox | null
  /** 列标题（无障碍提示用）。 */
  columnLabel(c: number): string
}

export interface LeafColumnLite {
  id: string
  label?: string
}

const EMPTY_GEOMETRY: GridGeometry = {
  rowCount: 0,
  colCount: 0,
  cellAt: () => null,
  boxOf: () => null,
  columnLabel: () => '',
}

function buildFromRows(
  rows: HTMLTableRowElement[],
  colCount: number,
  colOf: (td: HTMLTableCellElement, r: number, occupied: (c: number) => boolean) => number,
  labelOf: (c: number) => string,
): GridGeometry {
  const grid: Array<Array<HTMLTableCellElement | null>> = rows.map(() => [])
  const boxes = new Map<Element, CellBox>()
  let maxCol = colCount
  rows.forEach((tr, r) => {
    for (const cell of Array.from(tr.cells)) {
      const c = colOf(cell, r, (cc) => grid[r][cc] != null)
      if (c < 0) continue
      const rs = Math.max(1, cell.rowSpan || 1)
      const cs = Math.max(1, cell.colSpan || 1)
      boxes.set(cell, { r, c, rs, cs })
      for (let dr = 0; dr < rs && r + dr < rows.length; dr++) {
        for (let dc = 0; dc < cs; dc++) {
          grid[r + dr][c + dc] = cell
          if (c + dc + 1 > maxCol) maxCol = c + dc + 1
        }
      }
    }
  })
  return {
    rowCount: rows.length,
    colCount: maxCol,
    cellAt: (r, c) => (r >= 0 && r < rows.length && c >= 0 ? grid[r][c] ?? null : null),
    boxOf: (td) => boxes.get(td) ?? null,
    columnLabel: labelOf,
  }
}

/** el-table 主表体（排除嵌套在单元格里的子表）。 */
export function elTableBody(root: HTMLElement): HTMLTableSectionElement | null {
  for (const table of Array.from(root.querySelectorAll<HTMLTableElement>('table.el-table__body'))) {
    if (table.closest('.el-table') === root) return table.tBodies[0] ?? null
  }
  return null
}

export function elTableRows(root: HTMLElement): HTMLTableRowElement[] {
  const tbody = elTableBody(root)
  if (!tbody) return []
  return Array.from(tbody.rows).filter(
    (tr) => tr.classList.contains('el-table__row') && tr.style.display !== 'none',
  )
}

export function buildElTableGeometry(root: HTMLElement | null, columns: LeafColumnLite[]): GridGeometry {
  if (!root) return EMPTY_GEOMETRY
  const prefix = root.dataset.prefix || 'el'
  const idIndex = new Map(columns.map((col, i) => [col.id, i]))
  // 列 id：顶层列 `el-table_1_column_3`；分组表头下的叶子列是「父 id + _column_n」，如 `el-table_1_column_3_column_4`
  const idPattern = new RegExp(`(?:^|\\s)(${prefix}-table_\\d+(?:_column_\\d+)+)(?:\\s|$)`)
  return buildFromRows(
    elTableRows(root),
    columns.length,
    (td) => {
      const m = idPattern.exec(td.className)
      if (!m) return -1
      return idIndex.get(m[1]) ?? -1
    },
    (c) => columns[c]?.label ?? '',
  )
}

/** 原生表格：本表的全部行（含 thead / tfoot，不含嵌套子表）。 */
export function rawTableRows(table: HTMLTableElement | null): HTMLTableRowElement[] {
  if (!table) return []
  return Array.from(table.rows).filter((tr) => tr.closest('table') === table && tr.style.display !== 'none')
}

export function buildRawTableGeometry(table: HTMLTableElement | null): GridGeometry {
  if (!table) return EMPTY_GEOMETRY
  const rows = rawTableRows(table)
  const headerRow = table.tHead?.rows[0] ?? null
  return buildFromRows(
    rows,
    0,
    (_td, _r, occupied) => {
      let c = 0
      while (occupied(c)) c++
      return c
    },
    (c) => {
      if (!headerRow) return ''
      let col = 0
      for (const cell of Array.from(headerRow.cells)) {
        const cs = Math.max(1, cell.colSpan || 1)
        if (c >= col && c < col + cs) return (cell.textContent || '').trim()
        col += cs
      }
      return ''
    },
  )
}

/** 事件目标所在的、属于本表的格（嵌套子表的格不算）。 */
export function cellFromTarget(target: EventTarget | null, geometry: GridGeometry): HTMLTableCellElement | null {
  let el = target instanceof Element ? target : null
  while (el) {
    const td = el.closest('td, th') as HTMLTableCellElement | null
    if (!td) return null
    if (geometry.boxOf(td)) return td
    el = td.parentElement
  }
  return null
}

/** 把格滚到可见（只滚表格自己的滚动容器，不动整页之外的祖先）。 */
export function scrollCellIntoView(td: HTMLElement): void {
  if (typeof td.scrollIntoView === 'function') td.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}

/**
 * 格相对根节点的矩形（承接框定位用）。绝对定位以根节点的内边距框为基准，
 * 要扣掉根节点自己的边框（原生表格常带 border；el-table 根节点无边框，扣 0）。
 */
export function rectWithin(td: HTMLElement, root: HTMLElement): { left: number; top: number; width: number; height: number } {
  const a = td.getBoundingClientRect()
  const b = root.getBoundingClientRect()
  return {
    left: a.left - b.left - (root.clientLeft || 0),
    top: a.top - b.top - (root.clientTop || 0),
    width: a.width,
    height: a.height,
  }
}
