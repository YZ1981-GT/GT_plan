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
  ConsolScopeVersion,
  ConsolTreeDiagnostic,
  ConsolTreeDiff,
  ConsolTreeNode,
  CurrentConsolEntity,
} from '@/services/consolidationApi'
import { relationLabel } from '@/utils/groupRelation'
import { fmtDateTime } from '@/utils/formatters'

/**
 * 角色标签（与后端 `consol_node_naming` 同一口径，spec consol-autotree-linkage-closure R2）。
 * 母公司按节点类型区分：没有分公司 = 「单体母公司户」（数据节点），有分公司 = 「母公司户」（汇总节点），
 * 见 `roleLabel(role, kind)`；子公司 / 分公司自己有分公司时为「汇总户」。
 */
export const ROLE_LABELS: Record<ConsolNodeRole, string> = {
  consol: '合并户',
  consol_elim: '差额户',
  parent: '单体母公司户',
  hq: '本部单体户',
  branch_elim: '母分差额户',
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

export function roleLabel(role: string | null | undefined, kind?: string | null): string {
  if (kind === 'aggregate') {
    if (role === 'parent') return '母公司户'
    if (role === 'subsidiary' || role === 'branch') return '汇总户'
  }
  return (role && ROLE_LABELS[role as ConsolNodeRole]) || ''
}

/**
 * 组织图卡片上的「与上级关系」标签：与角色标签同文案时不重复显示
 * （子公司/分公司数据节点的角色就是关系本身；下级合并企业显示「合并户」+「子公司」两个标签）。
 */
export function relationTagLabel(node: Pick<ConsolTreeNode, 'role' | 'relation'> & { kind?: string | null }): string {
  const label = relationLabel(node.relation)
  return label && label !== roleLabel(node.role, node.kind) ? label : ''
}

/** 节点口径（内容区上下文条）：汇总 = 合并口径；差额户 = 本级调整与抵销；数据节点 = 单体项目 */
export function nodeBasisLabel(node: Pick<ConsolTreeNode, 'kind'> | null | undefined): string {
  if (!node) return ''
  if (node.kind === 'elim') return '本级调整与抵销'
  if (node.kind === 'data') return '单体项目'
  return '合并口径'
}

/** node_key → 直接上级节点 */
export function parentIndex(root: ConsolTreeNode | null | undefined): Map<string, ConsolTreeNode> {
  const parents = new Map<string, ConsolTreeNode>()
  for (const node of walkTree(root)) for (const child of node.children || []) parents.set(child.node_key, node)
  return parents
}

/**
 * 最近的汇总节点：本身是汇总节点就是自己，否则沿上级找（差额表选中非汇总节点时按它展示并高亮该列，R7.6）。
 * 找不到节点返回 null。
 */
export function nearestAggregateAncestor(
  root: ConsolTreeNode | null | undefined, nodeKey: string | null | undefined,
): ConsolTreeNode | null {
  let node = findNodeByKey(root, nodeKey)
  if (!node) return null
  const parents = parentIndex(root)
  while (node && node.kind !== 'aggregate') node = parents.get(node.node_key) || null
  return node
}

export interface StandaloneEntity {
  projectId: string | null
  name: string
  companyCode: string
  nodeKey: string
}

/**
 * 数据节点对应的单体项目（R6：本部单体户、单体母公司户、子公司、分公司）；汇总 / 差额节点返回 null。
 * `projectId` 为 null = 本年度没有单体项目（调用方给说明，不拿合并口径冒充）。
 */
export function standaloneEntityOf(node: ConsolTreeNode | null | undefined): StandaloneEntity | null {
  if (!node || node.kind !== 'data') return null
  return {
    projectId: node.project_id || null,
    name: node.company_name || nodeLabel(node),
    companyCode: node.company_code,
    nodeKey: node.node_key,
  }
}

export interface TreeOption {
  value: string
  label: string
  depth: number
  kind: string
}

/** 节点下拉：企业树全部节点（先序、按层级缩进、显示名称，不显示内部键，R10.2） */
export function treeOptionsWithDepth(root: ConsolTreeNode | null | undefined): TreeOption[] {
  const out: TreeOption[] = []
  const visit = (node: ConsolTreeNode, depth: number) => {
    out.push({ value: node.node_key, label: nodeLabel(node), depth, kind: node.kind })
    for (const child of node.children || []) visit(child, depth + 1)
  }
  if (root) visit(root, 0)
  return out
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

/** 诊断排序：警告在前，信息在后（同级保持后端顺序） */
export function sortDiagnostics(diags: ConsolTreeDiagnostic[] | null | undefined): ConsolTreeDiagnostic[] {
  const list = Array.isArray(diags) ? diags : []
  return [...list.filter((d) => d.level !== 'info'), ...list.filter((d) => d.level === 'info')]
}

// ─── 企业树版本（spec consol-autotree-linkage-closure R1.4~R1.6）────────────────────

/** 中栏版本标签：「树版本 v3」/「树版本：尚未记录」；悬停说明记录方式与时间 */
export function scopeVersionLabel(sv: ConsolScopeVersion | null | undefined): { text: string; tip: string } {
  if (!sv) return { text: '', tip: '' }
  if (!sv.revision) return { text: '树版本：尚未记录', tip: '首次推送合并数时自动记录企业树版本' }
  const how = sv.mode === 'user' ? '手动记录' : '推送时自动记录'
  const when = sv.recorded_at ? `，${fmtDateTime(sv.recorded_at)}` : ''
  const drift = sv.matches ? '' : sv.structural_change ? '；当前企业树结构已变化' : '；当前企业树只改了名称'
  return { text: `树版本 v${sv.revision}`, tip: `${how}${when}${drift}` }
}

/** 结构差异一句话：「新增 2 个节点、上级变化 1 个」（只列非零项；改名不算结构变化，不列） */
export function treeDiffSummary(diff: ConsolTreeDiff | null | undefined): string {
  if (!diff) return ''
  const parts: string[] = []
  if (diff.added?.length) parts.push(`新增 ${diff.added.length} 个节点`)
  if (diff.removed?.length) parts.push(`移除 ${diff.removed.length} 个节点`)
  if (diff.moved?.length) parts.push(`上级变化 ${diff.moved.length} 个`)
  if (diff.changed?.length) parts.push(`类型或与上级关系变化 ${diff.changed.length} 个`)
  return parts.join('、')
}

/** 差异明细（弹窗逐条列出）：每条一句中文 */
export function treeDiffLines(diff: ConsolTreeDiff | null | undefined): string[] {
  if (!diff) return []
  const name = (x: { label?: string | null; node_key: string }) => x.label || x.node_key
  return [
    ...(diff.added || []).map((x) => `新增：${name(x)}`),
    ...(diff.removed || []).map((x) => `移除：${name(x)}`),
    ...(diff.moved || []).map((x) => `上级变化：${name(x)}（${x.from_label || '无'} → ${x.to_label || '无'}）`),
    ...(diff.changed || []).map((x) => `类型或关系变化：${name(x)}`),
    ...(diff.renamed || []).map((x) => `改名：${x.from || '—'} → ${x.to || '—'}`),
  ]
}
