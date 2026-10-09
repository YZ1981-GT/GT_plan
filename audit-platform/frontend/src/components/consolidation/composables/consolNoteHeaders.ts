/** Compact Word/API header rows. Covered cells are omitted, never real leaf columns. */
export interface NoteHeaderCell { text: string; colspan: number; rowspan: number }
export interface NoteHeaderColumn { label: string; colIndex: number; children?: NoteHeaderColumn[] }
export interface NoteHeaderConfig {
  headers: string[]
  header_rows?: NoteHeaderCell[][]
  multi_header?: string[][] | null
  _column_groups?: Array<{ group: string; start: number; span: number }> | null
  _header_row_indexes?: number[]
}

export function noteHeaderRows(config: NoteHeaderConfig): NoteHeaderCell[][] {
  if (config.header_rows?.length) return config.header_rows
  const mh = config.multi_header
  if (mh?.length) {
    const out: NoteHeaderCell[][] = mh.map(() => [])
    const visit = (r: number, start: number, end: number) => {
      const anchors = [start]
      for (let c = start + 1; c < end; c++) if (mh[r]?.[c]?.trim()) anchors.push(c)
      anchors.forEach((c, i) => {
        const stop = anchors[i + 1] ?? end
        const leaf = mh.slice(r + 1).every((row) => row.slice(c, stop).every((text) => !text?.trim()))
        out[r].push({ text: mh[r]?.[c] || '', colspan: stop - c, rowspan: leaf ? mh.length - r : 1 })
        if (!leaf) visit(r + 1, c, stop)
      })
    }
    visit(0, 0, config.headers.length)
    return out
  }
  const groups = config._column_groups
  if (groups?.length) {
    const top: NoteHeaderCell[] = [], bottom: NoteHeaderCell[] = []
    let cursor = 0
    for (const g of [...groups].sort((a, b) => a.start - b.start)) {
      for (; cursor < g.start; cursor++) top.push({ text: config.headers[cursor], colspan: 1, rowspan: 2 })
      top.push({ text: g.group, colspan: g.span, rowspan: 1 })
      for (; cursor < g.start + g.span; cursor++) bottom.push({ text: config.headers[cursor]?.split('/').at(-1) || '', colspan: 1, rowspan: 1 })
    }
    for (; cursor < config.headers.length; cursor++) top.push({ text: config.headers[cursor], colspan: 1, rowspan: 2 })
    return [top, bottom]
  }
  return [config.headers.map((text) => ({ text, colspan: 1, rowspan: 1 }))]
}

export function noteHeaderColumns(config: NoteHeaderConfig): NoteHeaderColumn[] {
  const rows = noteHeaderRows(config), width = config.headers.length
  const grid: Array<Array<{ r: number; c: number; cell: NoteHeaderCell } | undefined>> = rows.map(() => Array(width))
  const placed: Array<{ r: number; c: number; cell: NoteHeaderCell }> = []
  rows.forEach((row, r) => {
    let cursor = 0
    row.forEach((cell) => {
      while (cursor < width && grid[r][cursor]) cursor++
      if (![cell.colspan, cell.rowspan].every((n) => Number.isInteger(n) && n > 0)
        || cursor + cell.colspan > width || r + cell.rowspan > rows.length) throw new Error('附注表头跨度无效')
      const entry = { r, c: cursor, cell }
      for (let rr = r; rr < r + cell.rowspan; rr++) for (let cc = cursor; cc < cursor + cell.colspan; cc++) {
        if (grid[rr][cc]) throw new Error('附注表头跨度重叠')
        grid[rr][cc] = entry
      }
      placed.push(entry)
      cursor += cell.colspan
    })
  })
  if (grid.some((row) => Array.from({ length: width }, (_, c) => !row[c]).some(Boolean))) throw new Error('附注表头没有覆盖全部列')
  const children = (r: number, start: number, end: number): NoteHeaderColumn[] => placed
    .filter((p) => p.r === r && p.c >= start && p.c < end)
    .flatMap(({ c, cell }) => {
      const next = r + cell.rowspan
      if (next < rows.length) return [{ label: cell.text, colIndex: -1, children: children(next, c, c + cell.colspan) }]
      return Array.from({ length: cell.colspan }, (_, offset) => ({ label: cell.text, colIndex: c + offset }))
    })
  return children(0, 0, width)
}

export function noteBodyRows<T>(rows: T[], headerIndexes: readonly number[] = []): T[] {
  if (headerIndexes.some((i) => !Number.isInteger(i) || i < 0 || i >= rows.length)
    || new Set(headerIndexes).size !== headerIndexes.length) throw new Error('附注子表头行索引无效')
  const excluded = new Set(headerIndexes)
  return rows.filter((_, i) => !excluded.has(i))
}
