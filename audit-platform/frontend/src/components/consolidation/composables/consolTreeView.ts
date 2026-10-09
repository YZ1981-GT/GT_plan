/**
 * 合并企业树的展示工具（纯函数）—— 合并页组织图、树形列表、中栏树、差额面板共用。
 *
 * Spec: .kiro/specs/consol-tree-three-code-autobuild/ 任务 10（需求 4.4 / 9.1~9.5）
 * 树完全来自后端三码推导（`GET /api/consolidation/worksheet/tree`），前端不再自造节点；
 * 节点身份一律用 `node_key`（`{企业代码}:{角色}`）—— 同一企业可以不同角色出现（合并户与母公司户）。
 */
import type {
  ConsolMode,
  ConsolNodeRole,
  ConsolTreeDiagnostic,
  ConsolTreeNode,
  CurrentConsolEntity,
} from '@/services/consolidationApi'
import { relationLabel } from '@/utils/groupRelation'

export const ROLE_LABELS: Record<ConsolNodeRole, string> = {
  consol: '合并',
  consol_elim: '合并差额',
  parent: '母公司',
  hq: '本部',
  branch_elim: '母分差额',
  subsidiary: '子公司',
  branch: '分公司',
}

/** 与后端 `consol_group_tree.MODE_LABELS` 同文案（接口也会直接返回 `mode_label`） */
export const MODE_LABELS: Record<ConsolMode, string> = {
  subsidiary: '母子合并',
  branch: '总分汇总',
  mixed: '母子合并＋总分汇总',
  none: '未识别到下级',
}

type TagType = 'warning' | 'info' | 'danger' | 'success' | 'primary'

/** 节点标记（后端 `TreeNode.flags`）的中文与提示级别 */
export const FLAG_META: Record<string, { label: string; type: TagType; hint: string }> = {
  detached: { label: '脱挂', type: 'warning', hint: '上级代码在本年度没有项目' },
  cycle_break: { label: '循环引用已断开', type: 'danger', hint: '上级关系成环，已断开一处连接' },
  relation_conflict: { label: '两口径关系不一致', type: 'warning', hint: '合并项目与单户项目的集团关系不一致，按单户项目取值' },
  relation_defaulted: { label: '关系未填', type: 'info', hint: '未填与上级关系，暂按子公司处理' },
  parent_missing: { label: '按控制方挂靠', type: 'info', hint: '未填上级代码，按最终控制方挂靠' },
  standalone_missing: { label: '未建单户项目', type: 'warning', hint: '本年度没有单户项目，金额按 0 计' },
}

export interface FlagTag {
  code: string
  label: string
  type: TagType
  hint: string
}

export function nodeLabel(node: Pick<ConsolTreeNode, 'display_name' | 'company_name' | 'company_code'>): string {
  return node.display_name || node.company_name || node.company_code || ''
}

/** 将组织树节点转换为报表与附注共用的当前实体上下文。 */
export function currentConsolEntityForNode(node: ConsolTreeNode): CurrentConsolEntity {
  return {
    code: node.company_code,
    name: nodeLabel(node),
    nodeKey: node.node_key,
  }
}

export function roleLabel(role: string | null | undefined): string {
  return (role && ROLE_LABELS[role as ConsolNodeRole]) || ''
}

/**
 * 组织图卡片上的「与上级关系」标签：与角色标签同文案时不重复显示
 * （子公司/分公司数据节点的角色就是关系本身；下级合并企业显示「合并」+「子公司」两个标签）。
 */
export function relationTagLabel(node: Pick<ConsolTreeNode, 'role' | 'relation'>): string {
  const label = relationLabel(node.relation)
  return label && label !== roleLabel(node.role) ? label : ''
}

export function modeLabel(mode: string | null | undefined, serverLabel?: string | null): string {
  if (serverLabel) return serverLabel
  return (mode && MODE_LABELS[mode as ConsolMode]) || ''
}

export function isElimNode(node: Pick<ConsolTreeNode, 'kind'> | null | undefined): boolean {
  return node?.kind === 'elim'
}

/** 「进入项目」只对有项目的节点显示：差额节点与有分公司的汇总节点没有自己的项目 */
export function canEnterProject(node: Pick<ConsolTreeNode, 'project_id'> | null | undefined): boolean {
  return !!node?.project_id
}

export function nodeIcon(node: Pick<ConsolTreeNode, 'kind'>): string {
  if (node.kind === 'elim') return '📝'
  if (node.kind === 'aggregate') return '🏢'
  return '🏠'
}

export function flagTags(node: Pick<ConsolTreeNode, 'flags'>): FlagTag[] {
  return (node.flags || []).map((code) => {
    const meta = FLAG_META[code]
    return meta ? { code, ...meta } : { code, label: code, type: 'info' as TagType, hint: '' }
  })
}

export function hasWarningFlag(node: Pick<ConsolTreeNode, 'flags'>): boolean {
  return flagTags(node).some((t) => t.type === 'warning' || t.type === 'danger')
}

/** 先序遍历（含根） */
export function* walkTree(root: ConsolTreeNode | null | undefined): Generator<ConsolTreeNode> {
  if (!root) return
  const stack: ConsolTreeNode[] = [root]
  while (stack.length) {
    const node = stack.pop()!
    yield node
    const kids = node.children || []
    for (let i = kids.length - 1; i >= 0; i -= 1) stack.push(kids[i])
  }
}

export function findNodeByKey(root: ConsolTreeNode | null | undefined, key: string | null | undefined): ConsolTreeNode | null {
  if (!key) return null
  for (const node of walkTree(root)) if (node.node_key === key) return node
  return null
}

/** 某企业在树里的首个节点（先序：有合并项目时即其「合并」节点，兼容按企业代码定位的旧调用方） */
export function findNodeByCompany(
  root: ConsolTreeNode | null | undefined, companyCode: string | null | undefined,
): ConsolTreeNode | null {
  if (!companyCode) return null
  for (const node of walkTree(root)) if (node.company_code === companyCode) return node
  return null
}

/** 承载某合并项目分录的「合并」节点（差额节点的 host_project_id → 该节点） */
export function findConsolNodeByProject(
  root: ConsolTreeNode | null | undefined, projectId: string | null | undefined,
): ConsolTreeNode | null {
  if (!projectId) return null
  for (const node of walkTree(root)) if (node.role === 'consol' && node.project_id === projectId) return node
  return null
}

/** 企业代码 → 企业名称（取企业所在位置的节点名，不带角色后缀） */
export function buildNameIndex(root: ConsolTreeNode | null | undefined): Map<string, string> {
  const names = new Map<string, string>()
  for (const node of walkTree(root)) {
    if (node.company_code && !names.has(node.company_code)) names.set(node.company_code, node.company_name || node.company_code)
  }
  return names
}

/** 「经 X、Y 间接持有」；没有中间企业返回空串 */
export function viaLabel(node: Pick<ConsolTreeNode, 'via'>, names: Map<string, string>): string {
  const via = node.via || []
  if (!via.length) return ''
  return `经 ${via.map((code) => names.get(code) || code).join('、')} 间接持有`
}

export function countNodes(root: ConsolTreeNode | null | undefined): number {
  let n = 0
  for (const _ of walkTree(root)) n += 1
  return n
}

export function maxDepth(root: ConsolTreeNode | null | undefined): number {
  if (!root) return 0
  const kids = root.children || []
  return 1 + (kids.length ? Math.max(...kids.map(maxDepth)) : 0)
}

export interface CompanyColumn {
  name: string
  code: string
  ratio: number
}

/**
 * 合并工作底稿的企业列（合并范围表为空时的回退）：根合并节点下的子公司类成员 ——
 * 下级合并企业与子公司（含经中间企业提升上来的），排除合并差额、母公司与分公司，按企业代码去重。
 */
export function directSubsidiaryMembers(root: ConsolTreeNode | null | undefined): CompanyColumn[] {
  if (!root) return []
  const out: CompanyColumn[] = []
  const seen = new Set<string>()
  for (const child of root.children || []) {
    if (child.role !== 'subsidiary' && child.role !== 'consol') continue
    if (!child.company_code || seen.has(child.company_code)) continue
    seen.add(child.company_code)
    out.push({
      name: child.company_name || child.company_code,
      code: child.company_code,
      ratio: Number(child.shareholding) || 0,
    })
  }
  return out
}

/** 诊断排序：警告在前，信息在后（同级保持后端顺序） */
export function sortDiagnostics(diags: ConsolTreeDiagnostic[] | null | undefined): ConsolTreeDiagnostic[] {
  const list = Array.isArray(diags) ? diags : []
  return [...list.filter((d) => d.level !== 'info'), ...list.filter((d) => d.level === 'info')]
}
