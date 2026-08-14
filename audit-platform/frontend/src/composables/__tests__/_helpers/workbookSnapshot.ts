/**
 * 工作簿快照序列化 —— 行为等价判据的唯一真源
 * spec: frontend-excel-io-single-entry-convergence
 *   (Requirements 2.1~2.5 / 5.4 / 5.5 · Property 6~10 / 28 / 29)
 *
 * ## 🔴 为什么是「读回后的结构」而不是 sha256
 *
 * B5 批的 4 个文件要从 ExcelJS 换到 SheetJS，两者产出的 xlsx **二进制必然不同**
 * （ZIP 条目顺序、`docProps/*` 内容、`styles.xml` 结构都不一样），但语义可以完全相同。
 * 若用 sha256 作判据，该批会永远红 —— 而永远红的守卫最终会被人改松或注释掉，
 * 那时真正的回归就没人拦了。
 *
 * ⇒ 判据落在**语义**上：单元格值、`!cols`、`cell.s`、`!merges`、sheet 名与顺序、文件名。
 *
 * ## 抓取与比对必须共用本文件
 *
 * 若「抓快照」和「验证」各写一份序列化，两份口径一旦漂移，验证就会拿两种不同的
 * 投影去比，红绿都不可信。故本文件是唯一真源，两端都调它。
 */

/** 单个 sheet 的语义投影 */
export interface SheetSnapshot {
  /** 列宽；原本未设置时为 null（必须能区分「无列宽」与「列宽为空数组」） */
  cols: Array<Record<string, unknown>> | null
  /** 合并区域；原本未设置时为 null */
  merges: Array<Record<string, unknown>> | null
  /** 单元格：地址 → { v 值, t 类型, s 样式 }；s 缺省时不落键 */
  cells: Record<string, { v: unknown; t?: string; s?: unknown }>
}

/** 一次导出的完整语义投影 */
export interface WorkbookSnapshot {
  /** 下载文件名（逐字比对，R2.5） */
  fileName: string
  /** sheet 名与**顺序**（R2.4） */
  sheetNames: string[]
  sheets: Record<string, SheetSnapshot>
}

/**
 * 把 SheetJS 工作簿对象投影成快照。
 *
 * @param wb SheetJS workbook（从 mock 的 writeFile 捕获，或 read 读回）
 * @param fileName 落盘文件名
 */
export function snapshotWorkbook(wb: any, fileName: string): WorkbookSnapshot {
  const sheetNames: string[] = [...(wb.SheetNames || [])]
  const sheets: Record<string, SheetSnapshot> = {}

  for (const name of sheetNames) {
    const ws = wb.Sheets?.[name]
    if (!ws) {
      sheets[name] = { cols: null, merges: null, cells: {} }
      continue
    }

    const cells: SheetSnapshot['cells'] = {}
    for (const addr of Object.keys(ws)) {
      // 以 ! 开头的是元数据键（!cols / !merges / !ref / !rows ...），单独处理
      if (addr.startsWith('!')) continue
      const cell = ws[addr]
      if (cell == null || typeof cell !== 'object') continue
      const entry: { v: unknown; t?: string; s?: unknown } = { v: cell.v }
      if (cell.t !== undefined) entry.t = cell.t
      // 只在确有样式时落 s 键 ⇒ 「原本无样式」与「样式为空对象」可区分（Property 8）
      if (cell.s !== undefined) entry.s = cell.s
      cells[addr] = entry
    }

    sheets[name] = {
      cols: ws['!cols'] ? JSON.parse(JSON.stringify(ws['!cols'])) : null,
      merges: ws['!merges'] ? JSON.parse(JSON.stringify(ws['!merges'])) : null,
      cells,
    }
  }

  return { fileName, sheetNames, sheets }
}

/**
 * 从字节读回并投影（供 `exportToBytes` 一类返回字节的入口使用）。
 *
 * 注意读回会丢失 `cell.s` —— SheetJS 社区版**不解析**样式。故字节路径的快照
 * 只能比值/列宽/sheet 名，样式比对须走 mock writeFile 捕获 wb 的路径。
 */
export async function snapshotFromBytes(bytes: Uint8Array, fileName: string): Promise<WorkbookSnapshot> {
  const XLSX: any = await import('xlsx')
  const wb = XLSX.read(bytes, { type: 'array' })
  return snapshotWorkbook(wb, fileName)
}

/** 差异条目 */
export interface SnapshotDiff {
  path: string
  before: unknown
  after: unknown
}

/**
 * 逐项比对两个快照，返回全部差异（而非首个差异）。
 *
 * 返回全部差异是刻意的：迁移一个文件常常一次引入多处偏差（样式 + 行号 + 文件名），
 * 只报第一处会让人改一处跑一次、反复多轮。
 */
export function diffSnapshots(before: WorkbookSnapshot, after: WorkbookSnapshot): SnapshotDiff[] {
  const diffs: SnapshotDiff[] = []

  if (before.fileName !== after.fileName) {
    diffs.push({ path: 'fileName', before: before.fileName, after: after.fileName })
  }

  if (JSON.stringify(before.sheetNames) !== JSON.stringify(after.sheetNames)) {
    diffs.push({ path: 'sheetNames(含顺序)', before: before.sheetNames, after: after.sheetNames })
  }

  const allSheets = new Set([...Object.keys(before.sheets), ...Object.keys(after.sheets)])
  for (const name of allSheets) {
    const b = before.sheets[name]
    const a = after.sheets[name]
    if (!b) {
      diffs.push({ path: `sheets[${name}]`, before: '(不存在)', after: '(新增)' })
      continue
    }
    if (!a) {
      diffs.push({ path: `sheets[${name}]`, before: '(存在)', after: '(丢失)' })
      continue
    }

    if (JSON.stringify(b.cols) !== JSON.stringify(a.cols)) {
      diffs.push({ path: `sheets[${name}].!cols`, before: b.cols, after: a.cols })
    }
    if (JSON.stringify(b.merges) !== JSON.stringify(a.merges)) {
      diffs.push({ path: `sheets[${name}].!merges`, before: b.merges, after: a.merges })
    }

    const allAddrs = new Set([...Object.keys(b.cells), ...Object.keys(a.cells)])
    for (const addr of allAddrs) {
      const bc = b.cells[addr]
      const ac = a.cells[addr]
      if (JSON.stringify(bc) !== JSON.stringify(ac)) {
        diffs.push({ path: `sheets[${name}].${addr}`, before: bc ?? '(无此格)', after: ac ?? '(无此格)' })
      }
    }
  }

  return diffs
}

/** 把差异列表格式化成可操作的断言消息 */
export function formatDiffs(label: string, diffs: SnapshotDiff[]): string {
  if (diffs.length === 0) return ''
  const lines = [
    `${label} 的产物与迁移前快照不一致，共 ${diffs.length} 处差异：`,
    '',
    ...diffs.slice(0, 30).map((d) => `  ${d.path}\n    迁移前: ${JSON.stringify(d.before)}\n    迁移后: ${JSON.stringify(d.after)}`),
  ]
  if (diffs.length > 30) lines.push(`  ...还有 ${diffs.length - 30} 处`)
  lines.push(
    '',
    '常见原因（按出现频率）：',
    '  1. 忘了传 applyStyles:false —— 会给原本无样式的产物加上仿宋 + 三线表（看 cell.s 差异）',
    '  2. 忘了传 includeNoteRow:false —— 表头前插了一行，全表行号下移（看 A1/A2 值错位）',
    '  3. 列宽算法换成了 computeColumnWidth —— 与原本手写的 wch 不同（看 !cols 差异）',
    '  4. 文件名拼接方式变了（看 fileName 差异）',
  )
  return lines.join('\n')
}
