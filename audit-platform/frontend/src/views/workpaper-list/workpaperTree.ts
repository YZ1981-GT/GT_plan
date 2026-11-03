// 底稿编码扁平列表 → 一层父子目录树（runtime-performance-and-reload-hardening-followup R6.4）。
//
// 与旧 buildTree 语义逐项相同：只有列表中真实存在的编码才能当父；子项只认 `父码-` 边界；
// 多个真实父前缀时取最长（A1-1 优先于 A1）。返回仍是一层 TreeNode，保持旧组件的展示行为。
// 复杂度由「每个候选父 × 每个编码」O(n²) 降为按连字符向前查 Set，O(Σ编码段数)。
export interface WorkpaperCodeRow {
  wp_code: string
}

export interface WorkpaperTreeNode<T extends WorkpaperCodeRow> {
  row: T
  children: T[]
}

function nearestRealParent(code: string, codes: ReadonlySet<string>): string {
  let cut = code.lastIndexOf('-')
  while (cut > 0) {
    const candidate = code.slice(0, cut)
    if (codes.has(candidate)) return candidate
    cut = code.lastIndexOf('-', cut - 1)
  }
  return ''
}

export function buildWorkpaperTree<T extends WorkpaperCodeRow>(items: readonly T[]): WorkpaperTreeNode<T>[] {
  const codes = new Set(items.map(item => item.wp_code))
  const parentByItem = new Map<T, string>()
  const childrenByParent = new Map<string, T[]>()

  for (const item of items) {
    const parent = nearestRealParent(item.wp_code, codes)
    if (!parent) continue
    parentByItem.set(item, parent)
    const children = childrenByParent.get(parent)
    if (children) children.push(item)
    else childrenByParent.set(parent, [item])
  }

  const roots: WorkpaperTreeNode<T>[] = []
  for (const item of items) {
    if (parentByItem.has(item)) continue
    roots.push({ row: item, children: childrenByParent.get(item.wp_code) ?? [] })
  }
  return roots
}
