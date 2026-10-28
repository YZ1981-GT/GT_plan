/**
 * 合并工作底稿「基本信息表」按企业树带出（spec consol-autotree-linkage-closure R4）。
 *
 * - 企业清单 = 根合并节点下的子公司类成员（下级合并企业与子公司，含经中间企业间接持有、提升上来的）；
 *   企业名称、企业代码、上级单位代码、最终控制方及其代码取自企业树（项目向导的三个企业代码），只读；
 * - 持股类型 / 间接持股方按「经 X 间接持有」预填（只对新出现的企业；已保存的行保留用户的选择）；
 * - 已保存的行按企业代码保留其余字段；企业树里已没有的行留在表尾（由表格标「已不在企业树中」，可删除）；
 * - 企业列只以企业树为准，持股比例取基本信息表的填写值。
 */
import type { ConsolTreeNode } from '@/services/consolidationApi'
import { buildNameIndex } from './consolTreeView'

/** 企业树带出、表内只读的字段 */
export const TREE_OWNED_INFO_FIELDS = [
  'company_name', 'company_code', 'parent_code', 'ultimate_controller', 'ultimate_controller_code',
] as const

export interface TreeMemberInfo {
  company_name: string
  company_code: string
  parent_code: string
  ultimate_controller: string
  ultimate_controller_code: string
  holding_type: '直接' | '间接'
  /** 间接持有时的直接持股企业名称（「经 X 间接持有」的 X） */
  indirect_holder: string
}

/** 基本信息表行的最小形状（完整字段见 ConsolWorksheetTabs 的 SubsidiaryInfoRow） */
export interface InfoRowLike {
  company_name: string
  company_code: string
  parent_code: string
  ultimate_controller: string
  ultimate_controller_code: string
  holding_type: string
  indirect_holder: string
  non_common_ratio?: number | null
  common_ratio?: number | null
  no_consol_ratio?: number | null
}

function code(v: unknown): string {
  return String(v ?? '').trim()
}

/** 企业树 → 基本信息表成员（树序，按企业代码去重） */
export function treeMemberInfos(root: ConsolTreeNode | null | undefined): TreeMemberInfo[] {
  if (!root) return []
  const names = buildNameIndex(root)
  const out: TreeMemberInfo[] = []
  const seen = new Set<string>()
  for (const child of root.children || []) {
    if (child.role !== 'subsidiary' && child.role !== 'consol') continue
    const c = code(child.company_code)
    if (!c || seen.has(c)) continue
    seen.add(c)
    const via = child.via || []
    const holder = via.length ? via[via.length - 1] : ''
    const ultimate = code(child.ultimate_company_code)
    out.push({
      company_name: child.company_name || c,
      company_code: c,
      parent_code: code(child.parent_company_code),
      ultimate_controller: ultimate ? names.get(ultimate) || '' : '',
      ultimate_controller_code: ultimate,
      holding_type: via.length ? '间接' : '直接',
      indirect_holder: holder ? names.get(holder) || holder : '',
    })
  }
  return out
}

/**
 * 按企业树对齐基本信息表：企业树成员在前（树序；树带出的字段覆盖、其余字段按企业代码保留），
 * 企业树里没有的已填行留在表尾（不丢用户数据，由表格标出可删）；全空行丢弃。幂等。
 */
export function alignInfoRows<R extends InfoRowLike>(
  current: readonly R[],
  members: readonly TreeMemberInfo[],
  mkEmpty: () => R,
): R[] {
  const byCode = new Map<string, R>()
  for (const row of current) {
    const c = code(row.company_code)
    if (c && !byCode.has(c)) byCode.set(c, row)
  }
  const memberCodes = new Set(members.map((m) => m.company_code))
  const out: R[] = members.map((m) => {
    const existing = byCode.get(m.company_code)
    const row: R = existing
      ? { ...existing }
      : { ...mkEmpty(), holding_type: m.holding_type, indirect_holder: m.indirect_holder }
    for (const field of TREE_OWNED_INFO_FIELDS) (row as InfoRowLike)[field] = m[field]
    return row
  })
  for (const row of current) {
    const c = code(row.company_code)
    if (c ? memberCodes.has(c) : !code(row.company_name)) continue
    out.push(row)
  }
  return out
}

/** 行的持股比例：按非同控 / 同控 / 不涉及合并的填写值依次取 */
export function infoRatio(row: Partial<InfoRowLike> | null | undefined): number {
  if (!row) return 0
  return Number(row.non_common_ratio || row.common_ratio || row.no_consol_ratio) || 0
}

/** 工作底稿企业列：企业树可用时只认企业树（比例取基本信息表），否则回退基本信息表的已填企业 */
export function worksheetCompanyColumns(
  members: readonly TreeMemberInfo[] | null,
  rows: readonly InfoRowLike[],
): Array<{ name: string; code: string; ratio: number }> {
  if (members) {
    const byCode = new Map<string, InfoRowLike>()
    for (const r of rows) if (code(r.company_code) && !byCode.has(code(r.company_code))) byCode.set(code(r.company_code), r)
    return members.map((m) => ({ name: m.company_name, code: m.company_code, ratio: infoRatio(byCode.get(m.company_code)) }))
  }
  return rows.filter((r) => r.company_name)
    .map((r) => ({ name: r.company_name, code: r.company_code, ratio: infoRatio(r) }))
}

/**
 * 企业树锁定模式的 Excel 导入：按企业代码只更新可编辑字段（`keys` 中且导入行里有的字段），
 * 匹配不上的行列出并跳过，不新增行。
 */
export function mergeImportedInfoRows<R extends InfoRowLike>(
  current: readonly R[],
  imported: ReadonlyArray<Record<string, unknown>>,
  keys: readonly string[],
): { rows: R[]; updated: number; unmatched: string[] } {
  const owned = new Set<string>(TREE_OWNED_INFO_FIELDS)
  const editable = keys.filter((k) => !owned.has(k))
  const rows = current.map((r) => ({ ...r }))
  const index = new Map<string, number>()
  rows.forEach((r, i) => { const c = code(r.company_code); if (c && !index.has(c)) index.set(c, i) })
  const touched = new Set<number>()
  const unmatched: string[] = []
  for (const imp of imported) {
    const c = code(imp.company_code)
    const i = c ? index.get(c) : undefined
    if (i === undefined) {
      unmatched.push(c || code(imp.company_name) || '（未填企业代码）')
      continue
    }
    for (const k of editable) if (k in imp) (rows[i] as unknown as Record<string, unknown>)[k] = imp[k]
    touched.add(i)
  }
  return { rows, updated: touched.size, unmatched }
}
