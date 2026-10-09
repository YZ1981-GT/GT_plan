/**
 * D7 sheet 编码 → render-config sheet_name 默认映射
 */
export interface D7IndexRowDef {
  seq: number
  name: string
  code: string
  group: string
  applicable: boolean
}

export const D7_SHEET_LABEL_MAP: Record<string, string> = {
  D7: '底稿目录',
  'D7-目录': '底稿目录',
  D7A: '合同负债审计程序表D7A',
  'D7-1': '合同负债审定表D7-1',
  'D7-2': '合同负债明细表D7-2',
  'D7-3': '合同负债调整分录汇总D7-3',
  'D7-4': '合同负债分析表D7-4',
  'D7-5': '账龄1年以上合同负债检查D7-5',
  'D7-6': '关联方合同负债检查D7-6',
  'D7-7': '合同负债凭证检查D7-7',
  'D7-附注上市': '合同负债附注披露信息（上市公司）',
  'D7-附注国企': '合同负债附注披露信息（国企）',
}

export const D7_INDEX_ROWS: D7IndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'D7', group: '核心', applicable: true },
  { seq: 2, name: '合同负债审计程序表', code: 'D7A', group: '核心', applicable: true },
  { seq: 3, name: '合同负债审定表', code: 'D7-1', group: '核心', applicable: true },
  { seq: 4, name: '合同负债明细表', code: 'D7-2', group: '核心', applicable: true },
  { seq: 5, name: '调整分录汇总', code: 'D7-3', group: '核心', applicable: true },
  { seq: 6, name: '合同负债分析表', code: 'D7-4', group: '分析', applicable: true },
  { seq: 7, name: '账龄1年以上检查', code: 'D7-5', group: '检查', applicable: true },
  { seq: 8, name: '关联方检查', code: 'D7-6', group: '检查', applicable: true },
  { seq: 9, name: '凭证检查', code: 'D7-7', group: '检查', applicable: true },
  { seq: 10, name: '附注披露（上市公司）', code: 'D7-附注上市', group: '核心', applicable: true },
  { seq: 11, name: '附注披露（国企）', code: 'D7-附注国企', group: '核心', applicable: true },
]

export const D7_PROC_INDEX_SHEET_MAP: Record<string, string> = {
  'D7-1': D7_SHEET_LABEL_MAP['D7-1'],
  'D7-2': D7_SHEET_LABEL_MAP['D7-2'],
  'D7-7': D7_SHEET_LABEL_MAP['D7-7'],
}

export function resolveD7SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  if (availableSheets?.length) {
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
    if (code === 'D7-附注上市' || code === '附注上市') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D7-附注国企' || code === '附注国企') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D7' || code === 'D7-目录') {
      const d = availableSheets.find(s => s.sheet_name?.includes('目录'))
      if (d?.sheet_name) return d.sheet_name
    }
  }
  return D7_SHEET_LABEL_MAP[code] ?? code
}

// ─── 底稿目录完成度判定（d567 spec Task 1：聚合键缺陷修复）──────────────
//
// 提取为纯函数供 D7TabIndex.vue 调用，并让判据可直接驱动真实生产逻辑
// （不镜像键名 —— D1 那次「单测镜像错误锚点、恒绿而生产恒死」是同源事故）。
//
// 🔴 D7-4 / D7-7 必须读**真实写入方**的分区键，旧聚合键 'D7-4-rows' / 'D7-7-rows'
// 全仓零写入点，读它们完成度恒「未填」。

type RemarkEntry = { remark?: string } | undefined

/** remark 存 JSON 行数组且非空 ⇒ 该 store 键有行 */
export function hasJsonRows(m: Map<string, RemarkEntry>, key: string): boolean {
  const raw = m.get(key)?.remark
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

/** 判定某编码的 D7 底稿是否已编制 */
export function isD7SheetComplete(code: string, m: Map<string, RemarkEntry>): boolean {
  switch (code) {
    case 'D7A':
      return [...m.keys()].some(k => k.startsWith('D7-proc-'))
    case 'D7-1':
      return [...m.keys()].some(k => k.startsWith('D7-1-adj-'))
    case 'D7-2':
      return hasJsonRows(m, 'D7-2-rows')
    case 'D7-3':
      return hasJsonRows(m, 'D7-3-rows')
    case 'D7-4':
      // 双受管区：credit/debit 任一有行即算已填（真实写入方 useD7Analysis）
      return hasJsonRows(m, 'D7-4-credit-rows') || hasJsonRows(m, 'D7-4-debit-rows')
    case 'D7-5':
      return hasJsonRows(m, 'D7-5-rows')
    case 'D7-6':
      return hasJsonRows(m, 'D7-6-rows')
    case 'D7-7':
      // 双受管区：period/post 任一有行即算已填（真实写入方 useD7VoucherCheck）
      return hasJsonRows(m, 'D7-7-period-rows') || hasJsonRows(m, 'D7-7-post-rows')
    case 'D7-附注上市':
    case 'D7-附注国企':
      return [...m.keys()].some(k => k.startsWith('D7-note-'))
    default:
      return false
  }
}
