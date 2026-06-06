/**
 * 交付件「文档结构树」纯逻辑模块
 *
 * 抽离可测纯逻辑（结构构建 / 默认全选 / 父子联动 / 选择投影），
 * 供 DocStructureTree.vue 与 fast-check 属性测试共用，避免重度依赖组件挂载。
 *
 * 对应需求：1.2（默认全选）、1.3 + 18.3（选择投影一致）、1.5（按文档类型不同结构）、1.6（附注层级联动）。
 */

export interface DocTreeNode {
  id: string
  label: string
  children?: DocTreeNode[]
}

/** 审计报告正文：段落级结构（需求 18.3 段落级选择） */
const REPORT_SECTIONS: DocTreeNode[] = [
  { id: '审计意见段', label: '审计意见段' },
  { id: '形成审计意见的基础段', label: '形成审计意见的基础段' },
  { id: '强调事项段', label: '强调事项段' },
  { id: '关键审计事项段', label: '关键审计事项段' },
  { id: '其他信息段', label: '其他信息段' },
  { id: '其他事项段', label: '其他事项段' },
  { id: '管理层和治理层对财务报表的责任段', label: '管理层和治理层责任' },
  { id: '注册会计师对财务报表审计的责任段', label: '注册会计师责任' },
  { id: '签章段', label: '签章段' },
]

/** 财务报表：表级结构 */
const FINANCIAL_REPORT_TABLES: DocTreeNode[] = [
  { id: 'balance_sheet', label: '资产负债表' },
  { id: 'income_statement', label: '利润表' },
  { id: 'cash_flow_statement', label: '现金流量表' },
  { id: 'equity_change_statement', label: '所有者权益变动表' },
]

/** 附注：层级目录结构（需求 1.6 支持展开/折叠层级选择） */
const DISCLOSURE_NOTES_TREE: DocTreeNode[] = [
  {
    id: 'note_basic',
    label: '一、公司基本情况及编制基础',
    children: [
      { id: 'note_basic_company', label: '公司基本情况' },
      { id: 'note_basic_prepare', label: '财务报表编制基础' },
    ],
  },
  {
    id: 'note_policy',
    label: '二、重要会计政策及会计估计',
    children: [
      { id: 'note_policy_currency', label: '记账本位币' },
      { id: 'note_policy_revenue', label: '收入确认政策' },
    ],
  },
  {
    id: 'note_items',
    label: '三、财务报表主要项目注释',
    children: [
      { id: 'note_item_cash', label: '货币资金' },
      { id: 'note_item_ar', label: '应收账款' },
      { id: 'note_item_inventory', label: '存货' },
      { id: 'note_item_fixed_asset', label: '固定资产' },
    ],
  },
]

/**
 * 按文档类型构建结构树（需求 1.5）。
 * 未知类型回退为审计报告段落结构。
 */
export function buildDocStructure(docType: string): DocTreeNode[] {
  switch (docType) {
    case 'financial_report':
      return FINANCIAL_REPORT_TABLES.map((n) => ({ ...n }))
    case 'disclosure_notes':
      return DISCLOSURE_NOTES_TREE.map(cloneNode)
    case 'audit_report':
    default:
      return REPORT_SECTIONS.map((n) => ({ ...n }))
  }
}

function cloneNode(node: DocTreeNode): DocTreeNode {
  return {
    id: node.id,
    label: node.label,
    children: node.children?.map(cloneNode),
  }
}

/** 收集全部叶子节点 id（无 children 的节点）。 */
export function collectLeafIds(nodes: DocTreeNode[]): string[] {
  const out: string[] = []
  const walk = (list: DocTreeNode[]) => {
    for (const n of list) {
      if (n.children && n.children.length) walk(n.children)
      else out.push(n.id)
    }
  }
  walk(nodes)
  return out
}

/** 收集全部节点 id（含父节点）。 */
export function collectAllIds(nodes: DocTreeNode[]): string[] {
  const out: string[] = []
  const walk = (list: DocTreeNode[]) => {
    for (const n of list) {
      out.push(n.id)
      if (n.children && n.children.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/**
 * 默认选中键集合（需求 1.2 默认全选）。
 * 返回全部叶子节点 id —— el-tree 在 show-checkbox 下据此推导父节点全选态。
 */
export function defaultCheckedKeys(nodes: DocTreeNode[]): string[] {
  return collectLeafIds(nodes)
}

/** 在树中查找节点（深度优先）。 */
export function findNode(nodes: DocTreeNode[], id: string): DocTreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.children) {
      const hit = findNode(n.children, id)
      if (hit) return hit
    }
  }
  return null
}

/** 某节点（含自身）下的全部叶子 id。 */
function leavesOf(node: DocTreeNode): string[] {
  if (!node.children || !node.children.length) return [node.id]
  return collectLeafIds(node.children)
}

/**
 * 父子联动（需求 1.6）：勾选父节点 → 其全部子（叶）节点被选中；
 * 取消父节点 → 其全部子（叶）节点被取消。
 *
 * 入参/返回均以「已选叶子 id 集合」表达，纯函数无副作用。
 */
export function applyToggle(
  nodes: DocTreeNode[],
  checkedLeaves: ReadonlySet<string>,
  nodeId: string,
  checked: boolean,
): Set<string> {
  const next = new Set(checkedLeaves)
  const node = findNode(nodes, nodeId)
  if (!node) return next
  const affected = leavesOf(node)
  for (const leaf of affected) {
    if (checked) next.add(leaf)
    else next.delete(leaf)
  }
  return next
}

/**
 * 选择投影（需求 1.3 + 18.3）：传给导出引擎的章节集合 = 被勾选的叶子子集，
 * 既不遗漏勾选项，也不包含未勾选项。返回按结构树顺序排列的稳定数组。
 */
export function projectedSections(
  nodes: DocTreeNode[],
  checkedLeaves: ReadonlySet<string>,
): string[] {
  return collectLeafIds(nodes).filter((id) => checkedLeaves.has(id))
}
