/**
 * useInteractionBaseline.ts — 统一交互能力基线定义
 *
 * 定义函证模块 9 张表统一要求的交互能力集：
 * - 编辑 / 右键菜单 / 选区(useCellSelection) / 复制 / 粘贴 / 求和
 * - 增删行 / 保存 / 导入 / 导出 / 键盘导航 / 只读守卫
 *
 * 审计矩阵：各组件自检是否满足基线，不满足的报告缺失项。
 *
 * Sprint 3 Task 3.4b
 */

// ─── 能力枚举 ────────────────────────────────────────────────────────────────

export const INTERACTION_CAPABILITIES = [
  'edit',            // 单元格/字段编辑
  'contextMenu',    // 右键菜单
  'cellSelection',  // useCellSelection 选区
  'copy',           // 复制选中内容
  'paste',          // 粘贴内容
  'sum',            // 选区求和
  'addRow',         // 增行
  'deleteRow',      // 删行
  'save',           // 保存
  'import',         // 导入
  'export',         // 导出
  'keyboard',       // 键盘导航（Tab/Enter/Arrow）
  'readonlyGuard',  // 只读模式守卫
] as const

export type InteractionCapability = typeof INTERACTION_CAPABILITIES[number]

// ─── 组件基线声明 ────────────────────────────────────────────────────────────

export interface ComponentBaseline {
  /** 组件标识（如 D0-1 / D0-4b） */
  componentId: string
  /** 已实现的能力集 */
  capabilities: Set<InteractionCapability>
  /** 不适用的能力（如 D0-8 检查表无 cellSelection） */
  notApplicable?: InteractionCapability[]
}

/** 全量必备基线（所有含表格/子表/清单的组件） */
export const FULL_BASELINE: InteractionCapability[] = [
  'edit', 'contextMenu', 'cellSelection', 'copy', 'paste', 'sum',
  'addRow', 'deleteRow', 'save', 'import', 'export', 'keyboard', 'readonlyGuard',
]

/** 精简基线（检查表类如 D0-8，无网格选区但有基本编辑） */
export const CHECKLIST_BASELINE: InteractionCapability[] = [
  'edit', 'contextMenu', 'copy', 'save', 'import', 'export', 'keyboard', 'readonlyGuard',
]

// ─── 9 张表能力声明 ──────────────────────────────────────────────────────────

export const COMPONENT_BASELINES: ComponentBaseline[] = [
  {
    componentId: 'D0-1',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-2',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-3',
    capabilities: new Set([
      'edit', 'contextMenu', 'copy', 'save', 'export', 'keyboard', 'readonlyGuard',
    ]),
    notApplicable: ['cellSelection', 'sum', 'paste', 'addRow', 'deleteRow', 'import'],
  },
  {
    componentId: 'D0-4',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-4b',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-5',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-6',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-7',
    capabilities: new Set(FULL_BASELINE),
  },
  {
    componentId: 'D0-8',
    capabilities: new Set(CHECKLIST_BASELINE),
    notApplicable: ['cellSelection', 'sum', 'paste', 'addRow', 'deleteRow'],
  },
]

// ─── 基线审计工具 ────────────────────────────────────────────────────────────

export interface BaselineAuditResult {
  componentId: string
  passed: boolean
  missing: InteractionCapability[]
  extra: InteractionCapability[]
}

/**
 * 审计单个组件的交互能力是否满足基线
 */
export function auditBaseline(
  componentId: string,
  implemented: InteractionCapability[]
): BaselineAuditResult {
  const baseline = COMPONENT_BASELINES.find(b => b.componentId === componentId)
  if (!baseline) {
    return { componentId, passed: false, missing: [...FULL_BASELINE], extra: [] }
  }

  const implSet = new Set(implemented)
  const required = [...baseline.capabilities]
  const notApplicable = new Set(baseline.notApplicable ?? [])

  const missing = required.filter(cap => !implSet.has(cap) && !notApplicable.has(cap))
  const extra = implemented.filter(cap => !baseline.capabilities.has(cap))

  return {
    componentId,
    passed: missing.length === 0,
    missing,
    extra,
  }
}

/**
 * 批量审计所有 9 组件
 */
export function auditAllBaselines(
  implementations: Record<string, InteractionCapability[]>
): BaselineAuditResult[] {
  return COMPONENT_BASELINES.map(baseline => {
    const impl = implementations[baseline.componentId] ?? []
    return auditBaseline(baseline.componentId, impl)
  })
}

// ─── 键盘导航配置 ────────────────────────────────────────────────────────────

export interface KeyboardNavConfig {
  /** Tab: 下一个可编辑单元格 */
  tab: boolean
  /** Enter: 确认编辑并移到下一行 */
  enter: boolean
  /** Arrow Keys: 方向键导航 */
  arrows: boolean
  /** Escape: 取消编辑 */
  escape: boolean
  /** Ctrl+C: 复制 */
  ctrlC: boolean
  /** Ctrl+V: 粘贴 */
  ctrlV: boolean
  /** Ctrl+S: 保存 */
  ctrlS: boolean
  /** Delete: 删除选中行 */
  delete: boolean
}

/** 默认键盘导航配置（全功能） */
export const DEFAULT_KEYBOARD_NAV: KeyboardNavConfig = {
  tab: true,
  enter: true,
  arrows: true,
  escape: true,
  ctrlC: true,
  ctrlV: true,
  ctrlS: true,
  delete: true,
}

/** 只读模式键盘配置（仅复制和导航） */
export const READONLY_KEYBOARD_NAV: KeyboardNavConfig = {
  tab: true,
  enter: false,
  arrows: true,
  escape: true,
  ctrlC: true,
  ctrlV: false,
  ctrlS: false,
  delete: false,
}
