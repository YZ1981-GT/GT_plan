/**
 * 附注表格列树（数据节点只读面板用；spec consol-autotree-linkage-closure R6）：任意层表头 → 列树。
 *
 * 读法与单体附注编辑器的列树 `views/composables/noteColumnTree.ts`（spec note-pull-header-formula-closure R4 / F8；
 * 本文件写作时它尚未入库，不能直接引用）逐条一致，也与后端标题行库 `column_paths` 同一读法：
 *
 *   1. `multi_header`（≥ 3 行；或 2 行且没有 `_column_groups`）：二维数组按「非空格向右吞并连续空格 = 跨列、
 *      上方非空下方空 = 跨行」还原成格子，每列取自上而下覆盖它的格子文字；
 *   2. `_column_groups`：平铺 `{group,start,span}` / 树形 `{group,children}` / `{group,columns:[列号]}`；
 *      两行 `multi_header` 时叶子名取末行；
 *   3. `columns[].group`（与 headers 等长时）：按「/」拆层；
 *   4. 都没有：平表头（列名里的「/」是字面，如「递延所得税资产/负债」，不拆）。
 *
 * 叶子名去掉与分组路径重复的「分组/」前缀；`<br/>` 换行标记去掉。叶子带 `headerIdx`（0 = 标签列，值列 =
 * `values[headerIdx - 1]`）。两份实现的一致性由 `__tests__/consolNoteColumns.spec.ts` 逐表对拍守护（编辑器列树
 * 存在时）；编辑器列树入库后，这里应改为直接复用它并删本文件。
 */

export interface NoteColNode {
  label: string
  /** 叶子：表头下标（0 = 标签列）；分组没有 */
  headerIdx?: number
  children?: NoteColNode[]
}

const BR_RE = /<br\s*\/?>/gi

function text(value: unknown): string {
  return String(value ?? '').replace(BR_RE, '').trim()
}

/** 二维 `multi_header` → 每列自上而下的表头文字（合并格只算一次）。 */
function gridPaths(mh: unknown[][], width: number): string[][] {
  const rows = mh.length
  const cols = Math.max(width, ...mh.map((r) => (Array.isArray(r) ? r.length : 0)))
  const cell = (r: number, c: number) => text(Array.isArray(mh[r]) ? mh[r][c] : '')
  // owner[r][c] = 覆盖这一格的锚点（"r,c"）
  const owner: string[][] = Array.from({ length: rows }, (_v, r) => Array.from({ length: cols }, (_u, c) => `${r},${c}`))
  const claimed: boolean[][] = Array.from({ length: rows }, () => Array(cols).fill(false))
  for (let r = 0; r < rows; r++) {
    let c = 0
    while (c < cols) {
      if (!cell(r, c)) { c++; continue }
      let end = c + 1
      while (end < cols && !cell(r, end)) {
        let above = false
        for (let rr = r - 1; rr >= 0; rr--) {
          if (cell(rr, end) && !claimed[rr][end]) { above = true; break }
        }
        if (above) break
        end++
      }
      for (let cc = c + 1; cc < end; cc++) { owner[r][cc] = `${r},${c}`; claimed[r][cc] = true }
      c = end
    }
  }
  for (let c = 0; c < cols; c++) {
    for (let r = rows - 1; r >= 1; r--) {
      if (cell(r, c) || claimed[r][c]) continue
      let anchor = r - 1
      while (anchor >= 0 && !cell(anchor, c) && !claimed[anchor][c]) anchor--
      if (anchor >= 0) {
        for (let rr = anchor + 1; rr <= r; rr++) { owner[rr][c] = owner[anchor][c]; claimed[rr][c] = true }
      }
    }
  }
  return Array.from({ length: cols }, (_v, c) => {
    const seen = new Set<string>()
    const path: string[] = []
    for (let r = 0; r < rows; r++) {
      const key = owner[r][c]
      if (seen.has(key)) continue
      seen.add(key)
      const [r0, c0] = key.split(',').map(Number)
      const t = cell(r0, c0)
      if (t) path.push(t)
    }
    return path
  })
}

function walkGroups(item: any, prefix: string[], out: Map<number, string[]>) {
  if (!item || typeof item !== 'object') return
  const name = text(item.group)
  const levels = name ? [...prefix, name] : prefix
  if (Array.isArray(item.children)) {
    for (const child of item.children) walkGroups(child, levels, out)
    return
  }
  if (Array.isArray(item.columns)) {
    for (const idx of item.columns) if (Number.isInteger(idx)) out.set(idx, levels)
    return
  }
  if (Number.isInteger(item.start)) {
    const span = Math.max(1, Number(item.span) || 1)
    for (let k = item.start; k < item.start + span; k++) out.set(k, levels)
  } else if (Number.isInteger(item.headerIdx) && levels.length) {
    out.set(item.headerIdx, levels)
  }
}

function leafLabel(raw: unknown, groups: string[]): string {
  const label = text(raw)
  const prefix = groups.length ? `${groups.join('/')}/` : ''
  return prefix && label.startsWith(prefix) ? label.slice(prefix.length) : label
}

/** 每列自上而下的表头文字（第 0 列为标签列）。 */
export function columnPaths(table: any): string[][] {
  const headers: unknown[] = Array.isArray(table?.headers) ? table.headers : []
  const width = headers.length
  if (!width) return []
  const mh = Array.isArray(table?.multi_header) ? table.multi_header : null
  const groups = Array.isArray(table?._column_groups) ? table._column_groups : null
  if (mh && mh.length >= 2 && (mh.length >= 3 || !groups?.length)) {
    const paths = gridPaths(mh, width).slice(0, width)
    return paths.map((p, c) => (p.length ? p : [text(headers[c])]))
  }
  const byCol = new Map<number, string[]>()
  if (groups?.length) {
    for (const g of groups) walkGroups(g, [], byCol)
  } else if (Array.isArray(table?.columns) && table.columns.length === width) {
    table.columns.forEach((col: any, c: number) => {
      if (col && col.group && !col.is_label) byCol.set(c, String(col.group).split('/').map(text).filter(Boolean))
    })
  }
  const leafRow = mh && mh.length >= 2 ? mh[mh.length - 1] : null
  return headers.map((h, c) => {
    const levels = byCol.get(c) ?? []
    const fromRow = Array.isArray(leafRow) ? text(leafRow[c]) : ''
    const leaf = fromRow || leafLabel(h, levels)
    return levels.length && levels[levels.length - 1] === leaf ? levels : [...levels, leaf]
  })
}

function build(paths: string[][], cols: number[], depth: number): NoteColNode[] {
  const out: NoteColNode[] = []
  let i = 0
  while (i < cols.length) {
    const c = cols[i]
    const p = paths[c]
    if (p.length - 1 <= depth) {
      out.push({ label: p[p.length - 1] ?? '', headerIdx: c })
      i++
      continue
    }
    const name = p[depth]
    let j = i
    while (j < cols.length && paths[cols[j]].length - 1 > depth && paths[cols[j]][depth] === name) j++
    out.push({ label: name, children: build(paths, cols.slice(i, j), depth + 1) })
    i = j
  }
  return out
}

/** 表格列树：叶子带 `headerIdx`；没有分组信息时全是叶子（平表头）；没有表头 ⇒ 空。 */
export function buildColumnTree(table: any): NoteColNode[] {
  const paths = columnPaths(table)
  return build(paths, paths.map((_p, c) => c), 0)
}

/** 列树的叶子（自左而右）。 */
export function columnLeaves(nodes: NoteColNode[]): NoteColNode[] {
  return nodes.flatMap((n) => (n.children?.length ? columnLeaves(n.children) : [n]))
}

/** 列树最深几层（表头行数）。 */
export function columnDepth(nodes: NoteColNode[]): number {
  return nodes.reduce((d, n) => Math.max(d, n.children?.length ? 1 + columnDepth(n.children) : 1), 0)
}
