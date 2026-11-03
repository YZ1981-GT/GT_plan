/**
 * noteColumnTree — 附注表格列树（任意层表头；spec note-pull-header-formula-closure R4 / F8）
 *
 * 原先单体编辑器只渲染两层（`_column_groups` 一层分组 + 叶子），`multi_header` 三层时中间层被整个丢掉（Path B 顶层
 * `filter(headerIdx >= 0)` 把嵌套分组滤掉 ⇒ 列消失）、`columns[].group` 不认（同步来的披露表两组「金额」并排看不出
 * 是哪一组）。现统一成「逐列表头路径 → 列树」，与后端标题行库 `column_paths` 同一读法：
 *
 *   1. `multi_header`（≥ 3 行；或 2 行且没有 `_column_groups`）：二维数组按「非空格向右吞并连续空格 = 跨列、
 *      上方非空下方空 = 跨行」还原成格子，每列取自上而下覆盖它的格子文字；
 *   2. `_column_groups`：平铺 `{group,start,span}` / 树形 `{group,children}` / `{group,columns:[列号]}`；
 *      两行 `multi_header` 时叶子名取末行；
 *   3. `columns[].group`（与 headers 等长时）：按「/」拆层；
 *   4. 都没有：平表头（列名里的「/」是字面，如「递延所得税资产/负债」，不拆）。
 *
 * 叶子名去掉与分组路径重复的「分组/」前缀；`<br/>` 换行标记去掉。列树只描述表头，单元格坐标仍是 `headerIdx`
 * （第 0 列 = 标签列，值列 = `values[headerIdx - 1]`）。
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
export function noteColumnPaths(table: any): string[][] {
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

/** 表格列树：叶子带 `headerIdx`；没有分组信息时全是叶子（平表头）。 */
export function buildNoteColumnTree(table: any): NoteColNode[] {
  const paths = noteColumnPaths(table)
  return build(paths, paths.map((_p, c) => c), 0)
}

/**
 * 期间层（spec note-pull-header-formula-closure R4 / ADR-3，后端 `note_period_layout` 同规则）：数据列外包一层期间
 * （标签列 = 第一个叶子，留在外面）。没有期间 / 第一个节点不是标签列时原样返回。
 */
export function periodTree(nodes: NoteColNode[], period: unknown): NoteColNode[] {
  const label = text(period)
  if (!label || !nodes.length || nodes[0].headerIdx !== 0) return nodes
  return [nodes[0], { label, children: nodes.slice(1) }]
}

/** 叶子的表头下标整体平移（并到另一张表右侧时用）。 */
export function offsetTree(nodes: NoteColNode[], by: number): NoteColNode[] {
  return nodes.map((n) => (n.children?.length
    ? { label: n.label, children: offsetTree(n.children, by) }
    : { label: n.label, headerIdx: (n.headerIdx ?? 0) === 0 ? 0 : (n.headerIdx as number) + by }))
}

/** 两张表逐行行名相同（去空白比；有行才算）—— 期间并列合成的前提，不一致不合成、不猜。 */
export function sameRowLabels(a: any, b: any): boolean {
  const ra = Array.isArray(a?.rows) ? a.rows : []
  const rb = Array.isArray(b?.rows) ? b.rows : []
  const key = (r: any) => String(r?.label ?? '').replace(/\s+/g, '')
  return ra.length > 0 && ra.length === rb.length && ra.every((r: any, i: number) => key(r) === key(rb[i]))
}

/** 列树的叶子（自左而右）。 */
export function noteColumnLeaves(nodes: NoteColNode[]): NoteColNode[] {
  return nodes.flatMap((n) => (n.children?.length ? noteColumnLeaves(n.children) : [n]))
}

/** 列树最深几层（表头行数）。 */
export function noteColumnDepth(nodes: NoteColNode[]): number {
  return nodes.reduce((d, n) => Math.max(d, n.children?.length ? 1 + noteColumnDepth(n.children) : 1), 0)
}
