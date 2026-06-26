/**
 * useB30GroupAudit — B30 集团审计范围确定底稿 主 composable
 *
 * Spec: .kiro/specs/b30-group-audit/
 * Task: 2.2
 *
 * 职责：
 * - 集团结构树管理（treeData / CRUD / 拖拽）
 * - 组成部分表格（扁平列表 / 占比计算 / 集团合计 / 筛选）
 * - 分类自动建议（15%/5% 双阈值）
 * - 重要性分配（B15 联动 / 建议 / 约束校验）
 * - 审计范围确定（建议 / 警告 / allScopeDetermined）
 * - 组成部分审计师管理（独立性 / 胜任能力）
 * - 覆盖率热力图（加权算法 / 矩阵 / 警告）
 * - 范围仪表盘统计（dashboardStats）
 * - 联动面板（linkageInfo）
 * - EventBus 事件发布/监听
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse, SaveFn } from './useB30FormData'

// ─── Constants (exported for testing) ────────────────────────────────────────

/** 分类阈值 */
export const CLASSIFICATION_THRESHOLDS = {
  SIGNIFICANT: 0.15,
  NON_SIGNIFICANT: 0.05,
} as const

/** 覆盖率加权系数 */
export const COVERAGE_WEIGHTS: Record<ScopeType, number> = {
  '全面审计': 1.0,
  '特定项目审计': 0.5,
  '分析性程序': 0.25,
  '不执行程序': 0.0,
}

/** 重要性分配调整系数 */
export const MATERIALITY_ALLOCATION_COEFFICIENT = 0.75

/** 分配重要性上限（占集团重要性百分比） */
export const MATERIALITY_UPPER_BOUND = 0.85

/** 分配重要性下限（占集团重要性百分比） */
export const MATERIALITY_LOWER_BOUND = 0.15

/** 组成部分分类→颜色映射 */
export const CLASSIFICATION_COLORS: Record<ComponentClassification, { color: string; bg: string; label: string }> = {
  '重要组成部分': { color: '#ff4d4f', bg: '#fff2f0', label: '重要' },
  '非重要组成部分': { color: '#faad14', bg: '#fffbe6', label: '非重要' },
  '不重要组成部分': { color: '#bfbfbf', bg: '#fafafa', label: '不重要' },
}

/** 审计范围类型→颜色映射 */
export const SCOPE_COLORS: Record<ScopeType, { color: string; bg: string; label: string }> = {
  '全面审计': { color: '#52c41a', bg: '#f6ffed', label: '全面' },
  '特定项目审计': { color: '#95de64', bg: '#f0fff0', label: '特定' },
  '分析性程序': { color: '#1890ff', bg: '#e6f7ff', label: '分析' },
  '不执行程序': { color: '#d9d9d9', bg: '#fafafa', label: '不执行' },
}

/** 热力图覆盖率贡献→颜色映射 */
export const HEATMAP_COLORS: Record<CoverageCell['colorLevel'], string> = {
  high: '#389e0d',
  medium: '#95de64',
  low: '#f0f0f0',
  none: '#ffffff',
}

/** 覆盖率不足警告阈值 */
export const COVERAGE_WARNING_THRESHOLD = 0.60

/** 覆盖率进度条颜色阈值 */
export const COVERAGE_PROGRESS_THRESHOLDS = {
  GREEN: 0.80,
  YELLOW: 0.60,
} as const

// ─── Types ───────────────────────────────────────────────────────────────────

/** 组成部分类型 */
export type ComponentType = '子公司' | '分公司' | '合营企业' | '联营企业' | '分部'

/** 组成部分分类 */
export type ComponentClassification = '重要组成部分' | '非重要组成部分' | '不重要组成部分'

/** 审计范围类型 */
export type ScopeType = '全面审计' | '特定项目审计' | '分析性程序' | '不执行程序'

/** 独立性确认 */
export type IndependenceConfirmation = '已确认' | '未确认' | '不适用'

/** 胜任能力评估 */
export type CompetenceAssessment = '充分' | '需补充' | '不充分'

/** 分类筛选选项 */
export type ClassificationFilter = 'all' | 'significant' | 'non-significant' | 'insignificant'

/** 组成部分实体 */
export interface ComponentEntity {
  id: string
  name: string
  type: ComponentType | null
  shareholding: number | null
  parentId: string | null
  totalAssets: number | null
  revenue: number | null
  profit: number | null
  assetRatio: number
  revenueRatio: number
  profitRatio: number
  classification: ComponentClassification | null
  suggestedClassification: ComponentClassification | null
  classificationOverridden: boolean
  classificationOverrideReason: string
  scopeType: ScopeType | null
  suggestedScopeType: ScopeType | null
  scopeOverridden: boolean
  scopeOverrideReason: string
  scopeDescription: string
  allocatedMateriality: number | null
  suggestedMateriality: number | null
  materialityWarning: string | null
  auditorName: string
  independence: IndependenceConfirmation | null
  competence: CompetenceAssessment | null
  auditorRemark: string
  remark: string
}

/** 新增组成部分输入 */
export interface NewComponentInput {
  name: string
  type: ComponentType
  shareholding: number | null
}

/** 组成部分字段类型 */
export type ComponentField =
  | 'name' | 'type' | 'shareholding' | 'parentId'
  | 'totalAssets' | 'revenue' | 'profit'
  | 'classification' | 'classificationOverrideReason'
  | 'scopeType' | 'scopeOverrideReason' | 'scopeDescription'
  | 'allocatedMateriality'
  | 'auditorName' | 'independence' | 'competence' | 'auditorRemark'
  | 'remark'

/** 树节点 */
export interface TreeNode {
  id: string
  label: string
  type: ComponentType | null
  classification: ComponentClassification | null
  scopeType: ScopeType | null
  children: TreeNode[]
}

/** 财务合计 */
export interface FinancialTotals {
  totalAssets: number
  revenue: number
  profit: number
}

/** 分类状态 */
export interface ClassificationState {
  current: ComponentClassification | null
  suggested: ComponentClassification | null
  overridden: boolean
  overrideReason: string
}

/** 范围状态 */
export interface ScopeState {
  current: ScopeType | null
  suggested: ScopeType | null
  overridden: boolean
  overrideReason: string
  warning: string | null
}

/** 重要性校验结果 */
export interface MaterialityValidation {
  valid: boolean
  warning: string | null
  upperBound: number
  lowerBound: number
}

/** 审计师信息 */
export interface AuditorInfo {
  name: string
  independence: IndependenceConfirmation | null
  competence: CompetenceAssessment | null
  remark: string
}

/** 覆盖率矩阵单元格 */
export interface CoverageCell {
  componentId: string
  componentName: string
  indicator: 'totalAssets' | 'revenue' | 'profit'
  amount: number
  ratio: number
  scopeType: ScopeType | null
  weight: number
  contribution: number
  colorLevel: 'high' | 'medium' | 'low' | 'none'
}

/** 覆盖率矩阵 */
export interface CoverageMatrix {
  rows: string[]
  columns: ('totalAssets' | 'revenue' | 'profit')[]
  cells: Map<string, CoverageCell>
}

/** 覆盖率合计 */
export interface CoverageTotals {
  totalAssets: number
  revenue: number
  profit: number
}

/** 覆盖率警告 */
export interface CoverageWarning {
  indicator: 'totalAssets' | 'revenue' | 'profit'
  indicatorLabel: string
  coverageRate: number
  message: string
}

/** 范围仪表盘统计 */
export interface ScopeDashboardStats {
  componentCount: number
  treeNodeCount: number
  treeMaxDepth: number
  classificationDistribution: {
    significant: number
    nonSignificant: number
    insignificant: number
    unclassified: number
  }
  scopeDistribution: {
    fullAudit: number
    specificItems: number
    analyticalProcedures: number
    noWork: number
    undetermined: number
  }
  coverageTotals: CoverageTotals
  groupMateriality: number | null
  allocatedCount: number
  pendingCount: number
  pendingDetails: {
    unclassified: number
    undeterminedScope: number
    independenceUnconfirmed: number
  }
  competenceInsufficient: number
}

/** 联动信息 */
export interface LinkageInfo {
  b15Status: 'completed' | 'incomplete'
  b15Materiality: number | null
  b50Status: 'received' | 'not-received'
  significantComponents: { id: string; name: string; scopeType: ScopeType }[]
  overallCoverage: CoverageTotals
}

/** EventBus: group:scope-determined 载荷 */
export interface ScopeDeterminedPayload {
  significantComponents: { name: string; scopeType: ScopeType }[]
  componentScopes: { name: string; classification: ComponentClassification; scopeType: ScopeType }[]
  coverageTotals: CoverageTotals
}

/** EventBus: materiality:determined 载荷（来自 B15） */
export interface MaterialityPayload {
  groupMateriality: number
  performanceMateriality: number
  trivialThreshold: number
}

// ─── Pure Functions (exported for testing) ───────────────────────────────────

/**
 * 生成 B30 item_id
 */
export function generateB30ItemId(
  type: 'tree-structure' | 'comp-count' | 'comp' | 'group-materiality' | 'review-sign' | 'amend',
  compIndex?: number,
  field?: string,
  amendRound?: number
): string {
  switch (type) {
    case 'tree-structure':
      return 'B30-tree-structure'
    case 'comp-count':
      return 'B30-comp-count'
    case 'comp':
      return `B30-comp-${compIndex}-${field}`
    case 'group-materiality':
      return 'B30-group-materiality'
    case 'review-sign':
      return 'B30-review-sign'
    case 'amend':
      return `B30-amend-${amendRound}-${field}`
  }
}

/**
 * 基于占比阈值自动建议组成部分分类（15%/5% 双阈值）
 */
export function suggestClassification(
  assetRatio: number,
  revenueRatio: number,
  profitRatio: number
): ComponentClassification | null {
  const ratios = [assetRatio, revenueRatio, profitRatio]
  if (ratios.every(r => r === 0)) return null

  const maxRatio = Math.max(...ratios)

  if (maxRatio > CLASSIFICATION_THRESHOLDS.SIGNIFICANT) {
    return '重要组成部分'
  }
  if (maxRatio > CLASSIFICATION_THRESHOLDS.NON_SIGNIFICANT) {
    return '非重要组成部分'
  }
  return '不重要组成部分'
}

/**
 * 建议组成部分分配重要性金额
 */
export function suggestAllocatedMateriality(
  maxRatio: number,
  groupMateriality: number
): number {
  const raw = maxRatio * groupMateriality * MATERIALITY_ALLOCATION_COEFFICIENT
  const lower = groupMateriality * MATERIALITY_LOWER_BOUND
  const upper = groupMateriality * MATERIALITY_UPPER_BOUND
  return Math.max(lower, Math.min(upper, raw))
}

/**
 * 校验分配重要性是否在合理区间
 */
export function validateMaterialityBounds(
  allocated: number,
  groupMateriality: number
): MaterialityValidation {
  const upper = groupMateriality * MATERIALITY_UPPER_BOUND
  const lower = groupMateriality * MATERIALITY_LOWER_BOUND

  if (allocated > upper) {
    return { valid: false, warning: `超过集团重要性的 85%（上限 ${upper.toLocaleString()} 元）`, upperBound: upper, lowerBound: lower }
  }
  if (allocated < lower) {
    return { valid: false, warning: `低于集团重要性的 15%（下限 ${lower.toLocaleString()} 元）`, upperBound: upper, lowerBound: lower }
  }
  return { valid: true, warning: null, upperBound: upper, lowerBound: lower }
}

/**
 * 计算各指标的加权覆盖率
 */
export function calculateCoverageRate(
  components: ComponentEntity[],
  indicator: 'totalAssets' | 'revenue' | 'profit'
): number {
  let totalCoverage = 0

  for (const comp of components) {
    const ratio = indicator === 'totalAssets' ? comp.assetRatio
      : indicator === 'revenue' ? comp.revenueRatio
      : comp.profitRatio

    const weight = comp.scopeType ? COVERAGE_WEIGHTS[comp.scopeType] : 0
    totalCoverage += ratio * weight
  }

  return Math.min(1, Math.max(0, totalCoverage))
}

/**
 * 确定热力图单元格颜色等级
 */
export function getCoverageColorLevel(contribution: number): CoverageCell['colorLevel'] {
  if (contribution === 0) return 'none'
  if (contribution >= 0.15) return 'high'
  if (contribution >= 0.05) return 'medium'
  return 'low'
}

/**
 * 基于分类自动建议审计范围类型
 */
export function suggestScopeType(classification: ComponentClassification | null): ScopeType | null {
  if (!classification) return null
  switch (classification) {
    case '重要组成部分': return '全面审计'
    case '非重要组成部分': return '特定项目审计'
    case '不重要组成部分': return '不执行程序'
  }
}

// ─── Main Composable ─────────────────────────────────────────────────────────

export function useB30GroupAudit(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveImmediate: SaveFn
) {
  // ─── Helper: read/write response fields ──────────────────────────────────

  function getResponseValue(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }

  function setResponseLocal(itemId: string, conclusion: string | null, remark: string | null = null, wpRef: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark, wp_ref: wpRef }
    allResponses.value.set(itemId, item)
    return item
  }

  // ─── 集团结构树 ─────────────────────────────────────────────────────────

  function getComponentCount(): number {
    const id = generateB30ItemId('comp-count')
    const r = getResponseValue(id)
    const count = parseInt(r.remark || '0', 10)
    return isNaN(count) ? 0 : count
  }

  /** 从 allResponses 构建树数据 */
  const treeData: ComputedRef<TreeNode[]> = computed(() => {
    const count = getComponentCount()
    const nodes: { id: string; label: string; type: ComponentType | null; classification: ComponentClassification | null; scopeType: ScopeType | null; parentId: string | null }[] = []

    for (let n = 1; n <= count; n++) {
      const id = String(n)
      const name = getResponseValue(generateB30ItemId('comp', n, 'name')).remark || `组成部分${n}`
      const typeVal = getResponseValue(generateB30ItemId('comp', n, 'type')).conclusion as ComponentType | null
      const cls = getResponseValue(generateB30ItemId('comp', n, 'classification')).conclusion as ComponentClassification | null
      const scope = getResponseValue(generateB30ItemId('comp', n, 'scope')).conclusion as ScopeType | null
      const parent = getResponseValue(generateB30ItemId('comp', n, 'parent')).remark || null

      nodes.push({ id, label: name, type: typeVal, classification: cls, scopeType: scope, parentId: parent })
    }

    // Build tree structure
    function buildChildren(parentId: string | null): TreeNode[] {
      return nodes
        .filter(n => n.parentId === parentId)
        .map(n => ({
          id: n.id,
          label: n.label,
          type: n.type,
          classification: n.classification,
          scopeType: n.scopeType,
          children: buildChildren(n.id),
        }))
    }

    return buildChildren(null)
  })

  const treeNodeCount: ComputedRef<number> = computed(() => getComponentCount())

  function getTreeDepth(nodes: TreeNode[]): number {
    if (nodes.length === 0) return 0
    return 1 + Math.max(...nodes.map(n => getTreeDepth(n.children)))
  }

  const treeMaxDepth: ComputedRef<number> = computed(() => getTreeDepth(treeData.value))

  function addComponent(parentId: string | null, entity: NewComponentInput): void {
    const currentCount = getComponentCount()
    if (currentCount >= 50) return // Max 50 components

    const newIndex = currentCount + 1
    const items: ChecklistItem[] = [
      setResponseLocal(generateB30ItemId('comp-count'), null, String(newIndex)),
      setResponseLocal(generateB30ItemId('comp', newIndex, 'name'), null, entity.name),
      setResponseLocal(generateB30ItemId('comp', newIndex, 'type'), entity.type),
      setResponseLocal(generateB30ItemId('comp', newIndex, 'shareholding'), null, entity.shareholding != null ? String(entity.shareholding) : null),
      setResponseLocal(generateB30ItemId('comp', newIndex, 'parent'), null, parentId),
    ]
    saveImmediate(items)
  }

  function removeComponent(componentId: string): void {
    const index = parseInt(componentId, 10)
    const currentCount = getComponentCount()
    if (index < 1 || index > currentCount) return

    // Check if node has children
    for (let n = 1; n <= currentCount; n++) {
      if (n === index) continue
      const parent = getResponseValue(generateB30ItemId('comp', n, 'parent')).remark
      if (parent === componentId) return // Has children, refuse
    }

    // Shift all items after the removed index
    const items: ChecklistItem[] = []
    const fields = ['name', 'type', 'shareholding', 'parent', 'assets', 'revenue', 'profit',
      'classification', 'cls-override', 'scope', 'scope-override', 'scope-desc',
      'materiality', 'auditor-name', 'independence', 'competence', 'auditor-remark', 'remark']

    for (let m = index; m < currentCount; m++) {
      for (const field of fields) {
        const sourceId = generateB30ItemId('comp', m + 1, field)
        const targetId = generateB30ItemId('comp', m, field)
        const source = getResponseValue(sourceId)
        items.push(setResponseLocal(targetId, source.conclusion, source.remark, source.wp_ref))
      }
    }

    // Clear last slot
    for (const field of fields) {
      const lastId = generateB30ItemId('comp', currentCount, field)
      items.push(setResponseLocal(lastId, null, null))
    }

    // Update parent references for shifted components
    for (let n = 1; n < currentCount; n++) {
      const parentId = generateB30ItemId('comp', n, 'parent')
      const parentVal = getResponseValue(parentId).remark
      if (parentVal) {
        const parentIdx = parseInt(parentVal, 10)
        if (parentIdx === index) {
          // Should not happen (we checked above), but safety
          items.push(setResponseLocal(parentId, null, null))
        } else if (parentIdx > index) {
          items.push(setResponseLocal(parentId, null, String(parentIdx - 1)))
        }
      }
    }

    // Update count
    items.push(setResponseLocal(generateB30ItemId('comp-count'), null, String(currentCount - 1)))
    saveImmediate(items)
  }

  function moveComponent(componentId: string, newParentId: string): void {
    const index = parseInt(componentId, 10)
    const currentCount = getComponentCount()
    if (index < 1 || index > currentCount) return

    // Validate max depth (5 levels)
    function getDepthOf(nodeId: string, visited: Set<string> = new Set()): number {
      if (visited.has(nodeId)) return 0
      visited.add(nodeId)
      let depth = 0
      for (let n = 1; n <= currentCount; n++) {
        const parent = getResponseValue(generateB30ItemId('comp', n, 'parent')).remark
        if (parent === nodeId) {
          depth = Math.max(depth, 1 + getDepthOf(String(n), visited))
        }
      }
      return depth
    }

    function getAncestorDepth(nodeId: string): number {
      let depth = 0
      let current: string | null = nodeId
      const visited = new Set<string>()
      while (current) {
        if (visited.has(current)) break
        visited.add(current)
        const idx = parseInt(current, 10)
        if (idx < 1 || idx > currentCount) break
        const parent = getResponseValue(generateB30ItemId('comp', idx, 'parent')).remark
        if (parent) {
          depth++
          current = parent
        } else {
          break
        }
      }
      return depth
    }

    const subtreeDepth = getDepthOf(componentId)
    const newParentAncestorDepth = newParentId ? getAncestorDepth(newParentId) + 1 : 0
    if (newParentAncestorDepth + subtreeDepth + 1 > 5) return // Exceeds max depth

    const parentItemId = generateB30ItemId('comp', index, 'parent')
    const item = setResponseLocal(parentItemId, null, newParentId || null)
    saveImmediate([item])
  }

  function updateComponent(componentId: string, field: ComponentField, value: any): void {
    const index = parseInt(componentId, 10)
    const currentCount = getComponentCount()
    if (index < 1 || index > currentCount) return

    const fieldMap: Record<ComponentField, string> = {
      name: 'name', type: 'type', shareholding: 'shareholding', parentId: 'parent',
      totalAssets: 'assets', revenue: 'revenue', profit: 'profit',
      classification: 'classification', classificationOverrideReason: 'cls-override',
      scopeType: 'scope', scopeOverrideReason: 'scope-override', scopeDescription: 'scope-desc',
      allocatedMateriality: 'materiality',
      auditorName: 'auditor-name', independence: 'independence', competence: 'competence',
      auditorRemark: 'auditor-remark', remark: 'remark',
    }

    const storageField = fieldMap[field]
    const itemId = generateB30ItemId('comp', index, storageField)

    // Fields stored in conclusion vs remark
    const conclusionFields = ['type', 'classification', 'scope', 'independence', 'competence']
    let item: ChecklistItem

    if (conclusionFields.includes(storageField)) {
      item = setResponseLocal(itemId, value as string | null)
    } else if (storageField === 'cls-override' || storageField === 'scope-override') {
      // Override: conclusion='Y' if overridden, remark=reason
      if (value) {
        item = setResponseLocal(itemId, 'Y', value as string)
      } else {
        item = setResponseLocal(itemId, null, null)
      }
    } else {
      // Text/number fields → store in remark
      item = setResponseLocal(itemId, null, value != null ? String(value) : null)
    }

    saveImmediate([item])
  }

  // ─── 组成部分表格 ────────────────────────────────────────────────────────

  /** 集团合计 */
  const groupTotals: ComputedRef<FinancialTotals> = computed(() => {
    const count = getComponentCount()
    let totalAssets = 0
    let revenue = 0
    let profit = 0
    for (let n = 1; n <= count; n++) {
      totalAssets += parseFloat(getResponseValue(generateB30ItemId('comp', n, 'assets')).remark || '0') || 0
      revenue += parseFloat(getResponseValue(generateB30ItemId('comp', n, 'revenue')).remark || '0') || 0
      profit += parseFloat(getResponseValue(generateB30ItemId('comp', n, 'profit')).remark || '0') || 0
    }
    return { totalAssets, revenue, profit }
  })

  /** 扁平组成部分列表 */
  const components: ComputedRef<ComponentEntity[]> = computed(() => {
    const count = getComponentCount()
    const totals = groupTotals.value
    const gm = groupMateriality.value
    const result: ComponentEntity[] = []

    for (let n = 1; n <= count; n++) {
      const id = String(n)
      const name = getResponseValue(generateB30ItemId('comp', n, 'name')).remark || ''
      const typeVal = getResponseValue(generateB30ItemId('comp', n, 'type')).conclusion as ComponentType | null
      const shareholdingStr = getResponseValue(generateB30ItemId('comp', n, 'shareholding')).remark
      const shareholding = shareholdingStr ? parseFloat(shareholdingStr) : null
      const parentId = getResponseValue(generateB30ItemId('comp', n, 'parent')).remark || null

      const totalAssets = parseFloat(getResponseValue(generateB30ItemId('comp', n, 'assets')).remark || '0') || 0
      const revenueVal = parseFloat(getResponseValue(generateB30ItemId('comp', n, 'revenue')).remark || '0') || 0
      const profitVal = parseFloat(getResponseValue(generateB30ItemId('comp', n, 'profit')).remark || '0') || 0

      // Ratios use absolute values for denominator to handle negative profits
      const assetRatio = totals.totalAssets !== 0 ? Math.abs(totalAssets) / Math.abs(totals.totalAssets) : 0
      const revenueRatio = totals.revenue !== 0 ? Math.abs(revenueVal) / Math.abs(totals.revenue) : 0
      const profitRatio = totals.profit !== 0 ? Math.abs(profitVal) / Math.abs(totals.profit) : 0

      const classification = getResponseValue(generateB30ItemId('comp', n, 'classification')).conclusion as ComponentClassification | null
      const clsOverride = getResponseValue(generateB30ItemId('comp', n, 'cls-override'))
      const classificationOverridden = clsOverride.conclusion === 'Y'
      const classificationOverrideReason = clsOverride.remark || ''
      const suggested = suggestClassification(assetRatio, revenueRatio, profitRatio)

      const scopeTypeVal = getResponseValue(generateB30ItemId('comp', n, 'scope')).conclusion as ScopeType | null
      const scopeOverride = getResponseValue(generateB30ItemId('comp', n, 'scope-override'))
      const scopeOverridden = scopeOverride.conclusion === 'Y'
      const scopeOverrideReason = scopeOverride.remark || ''
      const scopeDescription = getResponseValue(generateB30ItemId('comp', n, 'scope-desc')).remark || ''
      const suggestedScope = suggestScopeType(classification)

      const materialityStr = getResponseValue(generateB30ItemId('comp', n, 'materiality')).remark
      const allocatedMateriality = materialityStr ? parseFloat(materialityStr) : null

      // Suggested materiality only for significant components
      let suggestedMat: number | null = null
      let matWarning: string | null = null
      if (classification === '重要组成部分' && gm) {
        const maxRatio = Math.max(assetRatio, revenueRatio, profitRatio)
        suggestedMat = suggestAllocatedMateriality(maxRatio, gm)
        if (allocatedMateriality != null) {
          const validation = validateMaterialityBounds(allocatedMateriality, gm)
          matWarning = validation.warning
        }
      }

      const auditorName = getResponseValue(generateB30ItemId('comp', n, 'auditor-name')).remark || ''
      const independence = getResponseValue(generateB30ItemId('comp', n, 'independence')).conclusion as IndependenceConfirmation | null
      const competence = getResponseValue(generateB30ItemId('comp', n, 'competence')).conclusion as CompetenceAssessment | null
      const auditorRemark = getResponseValue(generateB30ItemId('comp', n, 'auditor-remark')).remark || ''
      const remark = getResponseValue(generateB30ItemId('comp', n, 'remark')).remark || ''

      result.push({
        id, name, type: typeVal, shareholding, parentId,
        totalAssets, revenue: revenueVal, profit: profitVal,
        assetRatio, revenueRatio, profitRatio,
        classification, suggestedClassification: suggested,
        classificationOverridden, classificationOverrideReason,
        scopeType: scopeTypeVal, suggestedScopeType: suggestedScope,
        scopeOverridden, scopeOverrideReason, scopeDescription,
        allocatedMateriality, suggestedMateriality: suggestedMat, materialityWarning: matWarning,
        auditorName, independence, competence, auditorRemark, remark,
      })
    }

    return result
  })

  /** 按分类筛选 */
  function filteredComponents(filter: ClassificationFilter): ComputedRef<ComponentEntity[]> {
    return computed(() => {
      const all = components.value
      switch (filter) {
        case 'all': return all
        case 'significant': return all.filter(c => c.classification === '重要组成部分')
        case 'non-significant': return all.filter(c => c.classification === '非重要组成部分')
        case 'insignificant': return all.filter(c => c.classification === '不重要组成部分')
      }
    })
  }

  // ─── 分类建议 ────────────────────────────────────────────────────────────

  function setClassification(componentId: string, classification: ComponentClassification, overrideReason?: string): void {
    const index = parseInt(componentId, 10)
    const comp = components.value.find(c => c.id === componentId)
    if (!comp) return

    const isOverride = comp.suggestedClassification !== null && classification !== comp.suggestedClassification
    const items: ChecklistItem[] = [
      setResponseLocal(generateB30ItemId('comp', index, 'classification'), classification),
    ]

    if (isOverride && overrideReason) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'cls-override'), 'Y', overrideReason))
    } else if (!isOverride) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'cls-override'), null, null))
    }

    saveImmediate(items)
  }

  function getClassification(componentId: string): ComputedRef<ClassificationState> {
    return computed(() => {
      const comp = components.value.find(c => c.id === componentId)
      if (!comp) return { current: null, suggested: null, overridden: false, overrideReason: '' }
      return {
        current: comp.classification,
        suggested: comp.suggestedClassification,
        overridden: comp.classificationOverridden,
        overrideReason: comp.classificationOverrideReason,
      }
    })
  }

  // ─── 重要性分配 ──────────────────────────────────────────────────────────

  const groupMateriality = ref<number | null>(null)

  // Initialize from stored value
  const storedGM = computed(() => {
    const r = getResponseValue(generateB30ItemId('group-materiality'))
    return r.remark ? parseFloat(r.remark) : null
  })

  // Sync stored value to ref (initial load)
  const _gmSync = computed(() => {
    const stored = storedGM.value
    if (stored !== null && groupMateriality.value === null) {
      groupMateriality.value = stored
    }
    return stored
  })
  // Force evaluation
  void _gmSync.value

  function setAllocatedMateriality(componentId: string, amount: number): void {
    const index = parseInt(componentId, 10)
    const itemId = generateB30ItemId('comp', index, 'materiality')
    const item = setResponseLocal(itemId, null, String(amount))
    saveImmediate([item])
  }

  // ─── 审计范围确定 ────────────────────────────────────────────────────────

  function setScopeType(componentId: string, scopeType: ScopeType, overrideReason?: string): void {
    const index = parseInt(componentId, 10)
    const comp = components.value.find(c => c.id === componentId)
    if (!comp) return

    const suggested = suggestScopeType(comp.classification)
    const isOverride = suggested !== null && scopeType !== suggested

    const items: ChecklistItem[] = [
      setResponseLocal(generateB30ItemId('comp', index, 'scope'), scopeType),
    ]

    if (isOverride && overrideReason) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'scope-override'), 'Y', overrideReason))
    } else if (!isOverride) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'scope-override'), null, null))
    }

    // If scope is "不执行程序", clear auditor info
    if (scopeType === '不执行程序') {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'auditor-name'), null, null))
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'independence'), null, null))
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'competence'), null, null))
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'auditor-remark'), null, null))
    }

    saveImmediate(items)
  }

  function getScopeType(componentId: string): ComputedRef<ScopeState> {
    return computed(() => {
      const comp = components.value.find(c => c.id === componentId)
      if (!comp) return { current: null, suggested: null, overridden: false, overrideReason: '', warning: null }

      let warning: string | null = null
      if (comp.classification === '重要组成部分' && comp.scopeType && comp.scopeType !== '全面审计') {
        warning = '重要组成部分通常应执行全面审计'
      }

      return {
        current: comp.scopeType,
        suggested: comp.suggestedScopeType,
        overridden: comp.scopeOverridden,
        overrideReason: comp.scopeOverrideReason,
        warning,
      }
    })
  }

  const allScopeDetermined: ComputedRef<boolean> = computed(() => {
    const comps = components.value
    if (comps.length === 0) return false
    return comps.every(c => c.scopeType !== null)
  })

  // ─── 组成部分审计师 ──────────────────────────────────────────────────────

  function setAuditorInfo(componentId: string, info: Partial<AuditorInfo>): void {
    const index = parseInt(componentId, 10)
    const items: ChecklistItem[] = []

    if (info.name !== undefined) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'auditor-name'), null, info.name))
    }
    if (info.independence !== undefined) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'independence'), info.independence))
    }
    if (info.competence !== undefined) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'competence'), info.competence))
    }
    if (info.remark !== undefined) {
      items.push(setResponseLocal(generateB30ItemId('comp', index, 'auditor-remark'), null, info.remark))
    }

    if (items.length > 0) saveImmediate(items)
  }

  function getAuditorInfo(componentId: string): ComputedRef<AuditorInfo | null> {
    return computed(() => {
      const comp = components.value.find(c => c.id === componentId)
      if (!comp) return null
      if (comp.scopeType === '不执行程序') return null
      return {
        name: comp.auditorName,
        independence: comp.independence,
        competence: comp.competence,
        remark: comp.auditorRemark,
      }
    })
  }

  function clearAuditorInfo(componentId: string): void {
    const index = parseInt(componentId, 10)
    const items: ChecklistItem[] = [
      setResponseLocal(generateB30ItemId('comp', index, 'auditor-name'), null, null),
      setResponseLocal(generateB30ItemId('comp', index, 'independence'), null, null),
      setResponseLocal(generateB30ItemId('comp', index, 'competence'), null, null),
      setResponseLocal(generateB30ItemId('comp', index, 'auditor-remark'), null, null),
    ]
    saveImmediate(items)
  }

  // ─── 覆盖率热力图 ────────────────────────────────────────────────────────

  const coverageMatrix: ComputedRef<CoverageMatrix> = computed(() => {
    const comps = components.value
    const rows = comps.map(c => c.id)
    const columns: ('totalAssets' | 'revenue' | 'profit')[] = ['totalAssets', 'revenue', 'profit']
    const cells = new Map<string, CoverageCell>()

    for (const comp of comps) {
      for (const col of columns) {
        const ratio = col === 'totalAssets' ? comp.assetRatio
          : col === 'revenue' ? comp.revenueRatio
          : comp.profitRatio
        const amount = col === 'totalAssets' ? (comp.totalAssets || 0)
          : col === 'revenue' ? (comp.revenue || 0)
          : (comp.profit || 0)
        const weight = comp.scopeType ? COVERAGE_WEIGHTS[comp.scopeType] : 0
        const contribution = ratio * weight
        const colorLevel = getCoverageColorLevel(contribution)

        cells.set(`${comp.id}-${col}`, {
          componentId: comp.id,
          componentName: comp.name,
          indicator: col,
          amount,
          ratio,
          scopeType: comp.scopeType,
          weight,
          contribution,
          colorLevel,
        })
      }
    }

    return { rows, columns, cells }
  })

  const coverageTotals: ComputedRef<CoverageTotals> = computed(() => {
    const comps = components.value
    return {
      totalAssets: calculateCoverageRate(comps, 'totalAssets'),
      revenue: calculateCoverageRate(comps, 'revenue'),
      profit: calculateCoverageRate(comps, 'profit'),
    }
  })

  const INDICATOR_LABELS: Record<string, string> = {
    totalAssets: '总资产',
    revenue: '营业收入',
    profit: '利润',
  }

  const coverageWarnings: ComputedRef<CoverageWarning[]> = computed(() => {
    const totals = coverageTotals.value
    const warnings: CoverageWarning[] = []
    const indicators: ('totalAssets' | 'revenue' | 'profit')[] = ['totalAssets', 'revenue', 'profit']

    for (const ind of indicators) {
      if (totals[ind] < COVERAGE_WARNING_THRESHOLD) {
        warnings.push({
          indicator: ind,
          indicatorLabel: INDICATOR_LABELS[ind],
          coverageRate: totals[ind],
          message: '覆盖率不足，建议扩大审计范围',
        })
      }
    }

    return warnings
  })

  // ─── 范围仪表盘 ──────────────────────────────────────────────────────────

  const dashboardStats: ComputedRef<ScopeDashboardStats> = computed(() => {
    const comps = components.value
    const count = comps.length

    let significant = 0, nonSignificant = 0, insignificant = 0, unclassified = 0
    let fullAudit = 0, specificItems = 0, analyticalProcedures = 0, noWork = 0, undetermined = 0
    let allocatedCount = 0
    let undeterminedScope = 0, independenceUnconfirmed = 0
    let competenceInsufficient = 0

    for (const comp of comps) {
      // Classification distribution
      switch (comp.classification) {
        case '重要组成部分': significant++; break
        case '非重要组成部分': nonSignificant++; break
        case '不重要组成部分': insignificant++; break
        default: unclassified++; break
      }

      // Scope distribution
      switch (comp.scopeType) {
        case '全面审计': fullAudit++; break
        case '特定项目审计': specificItems++; break
        case '分析性程序': analyticalProcedures++; break
        case '不执行程序': noWork++; break
        default: undetermined++; break
      }

      // Materiality allocated
      if (comp.allocatedMateriality != null) allocatedCount++

      // Pending: scope undetermined
      if (!comp.scopeType) undeterminedScope++

      // Pending: independence unconfirmed for significant components
      if (comp.classification === '重要组成部分' && comp.independence !== '已确认' && comp.independence !== '不适用') {
        independenceUnconfirmed++
      }

      // Competence insufficient
      if (comp.competence === '不充分') competenceInsufficient++
    }

    const pendingCount = unclassified + undeterminedScope + independenceUnconfirmed

    return {
      componentCount: count,
      treeNodeCount: treeNodeCount.value,
      treeMaxDepth: treeMaxDepth.value,
      classificationDistribution: { significant, nonSignificant, insignificant, unclassified },
      scopeDistribution: { fullAudit, specificItems, analyticalProcedures, noWork, undetermined },
      coverageTotals: coverageTotals.value,
      groupMateriality: groupMateriality.value,
      allocatedCount,
      pendingCount,
      pendingDetails: { unclassified, undeterminedScope, independenceUnconfirmed },
      competenceInsufficient,
    }
  })

  // ─── 联动面板 ────────────────────────────────────────────────────────────

  const b50Received = ref(false)

  const linkageInfo: ComputedRef<LinkageInfo> = computed(() => {
    const gm = groupMateriality.value
    const comps = components.value
    const sigComps = comps
      .filter(c => c.classification === '重要组成部分' && c.scopeType)
      .map(c => ({ id: c.id, name: c.name, scopeType: c.scopeType! }))

    return {
      b15Status: gm ? 'completed' : 'incomplete',
      b15Materiality: gm,
      b50Status: b50Received.value ? 'received' : 'not-received',
      significantComponents: sigComps,
      overallCoverage: coverageTotals.value,
    }
  })

  // ─── EventBus ──────────────────────────────────────────────────────────

  function publishScopeDetermined(): void {
    if (!allScopeDetermined.value) return

    const comps = components.value
    const significantComponents = comps
      .filter(c => c.classification === '重要组成部分')
      .map(c => ({ name: c.name, scopeType: c.scopeType! }))

    const componentScopes = comps
      .filter(c => c.classification && c.scopeType)
      .map(c => ({ name: c.name, classification: c.classification!, scopeType: c.scopeType! }))

    const payload: ScopeDeterminedPayload = {
      significantComponents,
      componentScopes,
      coverageTotals: coverageTotals.value,
    }

    try {
      window.dispatchEvent(new CustomEvent('group:scope-determined', { detail: payload }))
      b50Received.value = true
    } catch {
      console.warn('[B30] EventBus publish group:scope-determined failed')
    }
  }

  function onMaterialityDetermined(payload: MaterialityPayload): void {
    groupMateriality.value = payload.groupMateriality
    // Persist to checklist_responses
    const item = setResponseLocal(generateB30ItemId('group-materiality'), null, String(payload.groupMateriality))
    saveImmediate([item])
  }

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    // 集团结构树
    treeData,
    treeNodeCount,
    treeMaxDepth,
    addComponent,
    removeComponent,
    moveComponent,
    updateComponent,
    // 组成部分表格
    components,
    groupTotals,
    filteredComponents,
    // 分类建议
    setClassification,
    getClassification,
    // 重要性分配
    groupMateriality,
    setAllocatedMateriality,
    // 审计范围确定
    setScopeType,
    getScopeType,
    allScopeDetermined,
    // 组成部分审计师
    setAuditorInfo,
    getAuditorInfo,
    clearAuditorInfo,
    // 覆盖率热力图
    coverageMatrix,
    coverageTotals,
    coverageWarnings,
    // 范围仪表盘
    dashboardStats,
    // 联动面板
    linkageInfo,
    // EventBus
    publishScopeDetermined,
    onMaterialityDetermined,
  }
}

export default useB30GroupAudit
