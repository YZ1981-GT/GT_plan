/**
 * eventBus — 全局事件总线（mitt）
 *
 * 替代 CustomEvent + document/window.dispatchEvent，提供：
 * - 类型安全（Events 映射表 → IDE 自动补全）
 * - 自动清理（onUnmounted 中 off 即可，无需 removeEventListener）
 * - 零 _redispatched 补丁
 *
 * @see design.md D1
 */
import mitt from 'mitt'
import type { SSEEventType } from '@/types/sse'

// Re-export SSEEventType for convenience
export type { SSEEventType } from '@/types/sse'

// ─── 事件载荷类型 ─────────────────────────────────────────────────────────────

/** 公式保存/应用 */
export interface FormulaChangedPayload {
  action: 'saved' | 'applied'
}

/** 准则切换 */
export interface StandardChangePayload {
  standard: 'soe' | 'listed'
}

/** 四栏切换 */
export interface FourColSwitchPayload {
  tab?: string
}

/** 打开公式管理器 */
export interface OpenFormulaManagerPayload {
  nodeKey?: string
}

/** 合并树节点选择 */
export interface ConsolTreeSelectPayload {
  companyCode?: string
  label?: string
  isReport?: boolean
  reportType?: string
  isDiff?: boolean
  switchTab?: string
}

/** 四栏 catalog 选择 */
export interface ConsolCatalogSelectPayload {
  type: string
  reportType?: string
  sectionId?: string
  title?: string
  standard?: string
  label?: string
}

/** 合并主体刷新 */
export interface ConsolRefreshEntityPayload {
  companyCode: string
  companyName: string
  types: string[]
}

/** 合并一键刷新完成（通知各 tab 刷新缓存） */
export interface ConsolRefreshDonePayload {
  projectId: string
  year: number
}

/** 合并树汇总 */
export interface ConsolTreeAggregatePayload {
  mode: 'direct' | 'custom'
  companyCode: string
  companyName: string
}

/** 附注全审 */
export interface ConsolNoteAuditAllPayload {
  standard: string
}

/** 模板应用（新增表样后触发地址注册表刷新） */
export interface TemplateAppliedPayload {
  configType: string
  projectId?: string
}

/** SSE 同步状态事件 */
export interface SyncEventPayload {
  event_type: SSEEventType
  project_id?: string
  year?: number
  account_codes?: string[]
  /** 编辑锁强抢事件常带字段 */
  wp_id?: string
  new_holder_id?: string
  new_holder_name?: string
  previous_holder_id?: string
  extra?: {
    source_event?: string
    handler?: string
    error?: string
    [key: string]: any
  }
  /** 允许其他事件类型携带自有顶层字段（弱约束 escape hatch） */
  [key: string]: any
}

/** 底稿解析完成（上传→解析→试算表联动） */
export interface WorkpaperParsedPayload {
  projectId: string
  wpId: string
}

/** 底稿保存完成（触发附注自动同步） */
export interface WorkpaperSavedPayload {
  projectId: string
  wpId: string
  year?: number
}

/** 重要性水平变更（触发试算表 exceeds_materiality 刷新） */
export interface MaterialityChangedPayload {
  projectId: string
  year?: number
}

/** 年度切换（R8-S1-04：全局年度上下文） */
export interface YearChangedPayload {
  projectId: string
  year: number
}

/** 审计上下文变更（Req 5：useAuditContext 检测到任一字段变化） */
export interface AuditContextChangedPayload {
  projectId: string
  year: number
  applicableStandard: 'soe' | 'listed'
  before: { projectId: string; year: number; applicableStandard: 'soe' | 'listed' }
}

/** 底稿单元格定位（R8-S2-02：自检失败项 → Univer 定位 / wp-locate-foundation: 穿透定位） */
export interface WorkpaperLocateCellPayload {
  wpId: string
  sheetName?: string
  cellRef: string
  /** wp-locate-foundation 扩展字段：componentType 辅助定位策略选择 */
  componentType?: string
  /** 目标值（辅助定位） */
  value?: string
  /** 人类可读标签 */
  label?: string
  /** 底稿编码（如 D2-1） */
  wpCode?: string
}

/** 复核标记变更（Foundation Task 2.9：触发循环徽章刷新） */
export interface ReviewMarkChangedPayload {
  projectId: string
  wpId: string
}

// ─── E1 Sprint 2 新增事件类型 ───────────────────────────────────────────────

/** 试算表变更（E1 Sprint 2 Task 2.33: 触发 prefill 重取） */
export interface TrialBalanceUpdatedPayload {
  projectId: string
  year?: number
}

/** 调整分录变更（触发 AJE/RJE 重取） */
export interface AdjustmentSavedPayload {
  projectId: string
  year?: number
  adjustmentId?: string
}

/** 项目信息变更（触发表头重填） */
export interface ProjectUpdatedPayload {
  projectId: string
  changedFields?: string[]
}

/** 函证回函（E1-3 标记已函证） */
export interface ConfirmationReceivedPayload {
  projectId: string
  confirmationId?: string
  accountCode?: string
}

/** 上年数据导入（PREV 公式重取） */
export interface PriorYearImportedPayload {
  projectId: string
  year: number
}

/** 复核记录已解决（E1 Sprint 2 Task 2.13） */
export interface ReviewRecordResolvedPayload {
  projectId?: string
  reviewRecordId: string
  wpId?: string
}

/** 签字已创建（E1 Sprint 2 Task 2.29） */
export interface SignatureCreatedPayload {
  projectId?: string
  objectType: string
  objectId: string
  signerId: string
}

/** 程序状态变更（E1 Sprint 2 Task 2.13） */
export interface ProcedureStatusChangedPayload {
  projectId: string
  wpId: string
  sheetKey: string
  row: string
  status: string
}

/** 跨底稿引用更新（D 销售循环 F6: D0→D2 反向回填 / H-F8: H9→H8 租赁回填） */
export interface CrossRefUpdatedPayload {
  projectId: string
  targetWpCode?: string
  sourceWpCode?: string
  refId?: string
}

// ─── 四栏附注联动事件 ──────────────────────────────────────────────────────────

/** 四栏目录附注章节点击（FourColumnCatalog → DisclosureEditor） */
export interface CatalogNoteSelectPayload {
  noteSection: string
}

/** 附注编辑器章节变更反向通知（DisclosureEditor → FourColumnCatalog） */
export interface NoteSectionChangedPayload {
  noteSection: string
}

// ─── C2~C15 控制测试结论联动（c-control-test-refresh Task 5.1） ──────────────

/**
 * C2~C15 控制测试循环结论变更（GtCControlTest → B50 风险评估订阅）。
 * 铁律：仅在结论实际变更（新旧值不同）时发布（Requirement 7.2/7.3）。
 */
export interface ControlTestConcludedPayload {
  /** 底稿编码 C2~C15 */
  wpCode: string
  /** 循环名称（如"销售与收款循环"） */
  cycleName: string
  /** 新结论值 */
  conclusion: string
  /** 缺陷摘要（有缺陷时为描述，否则为空） */
  defectSummary: string
}

// ─── C1 企业层面控制结论 / 缺陷联动（c1-entity-level-control Task 7.3） ──────────

/**
 * C1 企业层面控制整体结论变更（GtC1EntityControl → B50 风险评估订阅）。
 * 铁律：仅在结论实际变更（新旧值不同）时发布（Requirement 11.1/11.4）。
 */
export interface C1EntityControlConclusionPayload {
  projectId: string
  wpId: string
  wpCode?: string
  /** 新的整体结论（有效/部分有效/无效，或清空为 ''） */
  conclusion: string
  /** 变更前的整体结论（供订阅方判断迁移方向） */
  previousConclusion: string
}

/**
 * C1 识别出企业层面控制缺陷 → 一键跳转 A14 缺陷评价并带入缺陷摘要（Requirement 11.2）。
 * GtIndexChip 跳转 A14 时同时发布，供 A14 缺陷评价底稿预填缺陷摘要。
 */
export interface C1DefectToA14Payload {
  projectId: string
  wpId: string
  wpCode?: string
  /** 缺陷摘要文本 */
  defectSummary: string
  /** 来源缺陷 item_id（C1-defect-{d}-summary） */
  itemId: string
}

// ─── 事件映射表 ───────────────────────────────────────────────────────────────

export type Events = {
  // 布局 & 公式
  'formula-changed': FormulaChangedPayload
  'standard-change': StandardChangePayload
  'four-col-switch': FourColSwitchPayload
  'open-formula-manager': OpenFormulaManagerPayload

  // 合并模块通信
  'consol-tree-select': ConsolTreeSelectPayload
  'consol-catalog-select': ConsolCatalogSelectPayload
  'consol-refresh-entity': ConsolRefreshEntityPayload
  'consol-refresh-done': ConsolRefreshDonePayload
  'consol-tree-aggregate': ConsolTreeAggregatePayload
  'consol-note-audit-all': ConsolNoteAuditAllPayload

  // 模板 & 地址注册表
  'template-applied': TemplateAppliedPayload

  // SSE 同步状态
  'sse:sync-event': SyncEventPayload
  'sse:sync-failed': SyncEventPayload
  'sse:connected': void
  'sse:disconnected': void

  // 底稿生命周期
  'workpaper:parsed': WorkpaperParsedPayload
  'workpaper:saved': WorkpaperSavedPayload
  'workpaper:locate-cell': WorkpaperLocateCellPayload

  // 复核标记变更（Foundation Task 2.9）
  'review-mark:changed': ReviewMarkChangedPayload

  // 重要性水平
  'materiality:changed': MaterialityChangedPayload

  // 联动总线 stale 事件（Sprint 4 Task 4.7）
  'linkage:stale-changed': { project_id: string; affected_modules: string[]; total_affected: number }

  // D~N 实质性程序审定数变更（Adjudication → TB回写 + 附注刷新）
  'substantive:adjudicated': {
    accountCode: string
    auditedAmount: number
    wpCode: string
    timestamp: number
  }

  // useStaleSummaryFull 订阅的细粒度事件（payload 不强约束，由 SSE bridge / 业务方按需 emit）
  'adjustment:created': void
  'adjustment:updated': void
  'adjustment:deleted': void
  'dataset:activated': void

  // 编辑锁强抢通知（useEditingLock → SSE force_acquired 反射）
  'editing-lock:taken-over': {
    wp_id: string
    new_holder_id: string
    new_holder_name: string
    previous_holder_id?: string
  }

  // 全局打开自定义查询（Dashboard 快捷操作 / 侧栏 / 模板页 → ThreeColumnLayout 打开弹窗）
  'open-custom-query': { tab?: 'basic' | 'advanced'; source?: string; project_id?: string } | undefined

  // 年度切换（R8-S1-04）
  'year:changed': YearChangedPayload

  // 审计上下文变更（Req 5）
  'audit-context:changed': AuditContextChangedPayload

  // E1 Sprint 2 Task 2.33: 数据刷新 6 种事件
  'trial-balance:updated': TrialBalanceUpdatedPayload
  'adjustment:saved': AdjustmentSavedPayload
  'project:updated': ProjectUpdatedPayload
  'confirmation:received': ConfirmationReceivedPayload
  'prior-year:imported': PriorYearImportedPayload
  'manual-refresh': { projectId?: string; wpId?: string }

  // E1 Sprint 2 Task 2.13/2.29: 程序状态联动
  'review-record:resolved': ReviewRecordResolvedPayload
  'signature:created': SignatureCreatedPayload
  'procedure-status:changed': ProcedureStatusChangedPayload

  // D 销售循环 F6: 跨底稿引用更新（D0→D2 反向回填）
  'cross-ref:updated': CrossRefUpdatedPayload

  // 四栏附注联动（four-panel-note-linkage）
  'catalog:note-select': CatalogNoteSelectPayload
  'note:section-changed': NoteSectionChangedPayload

  // C2~C15 控制测试结论联动（c-control-test-refresh Task 5.1）
  'control:test-concluded': ControlTestConcludedPayload

  // C1 企业层面控制结论 / 缺陷联动（c1-entity-level-control Task 7.3）
  'c1:entity-control-conclusion': C1EntityControlConclusionPayload
  'c1:defect-identified': C1DefectToA14Payload

  // L1 短期借款利息测算联动 L2/L8（l1-short-term-loans Task 3.2）
  'l1:interest-calculated': {
    wpCode: string
    totalInterest: number
    financialExpenseInterest: number
    byContract: Array<{ contractNo: string; interest: number }>
    timestamp: number
  }

  // consol-phase1-arch-lock 需求 4.3: 后端返回 423 合并锁定 → 刷新前端锁定态
  'consol-lock:detected': { projectId?: string }

  // A1 Dashboard 子底稿依赖联动
  'a17-audit-summary-completed': { projectId?: string }
  'a1-11-signing-completed': { projectId?: string }

  // A17-2-1 KAM 更新（联动 A17-1 第十二章）
  'kam:updated': { count: number; summaries: { index: number; basic: string }[] }

  // 快捷键（shortcuts.ts 发出）
  'shortcut:save': void
  'shortcut:undo': void
  'shortcut:redo': void
  'shortcut:search': void
  'shortcut:goto': void
  'shortcut:export': void
  'shortcut:submit': void
  'shortcut:escape': void
  'shortcut:refresh': void
  'shortcut:help': void
  'shortcut:tab-focus': void
  'shortcut:list-up': void
  'shortcut:list-down': void
}

// ─── 导出单例 ─────────────────────────────────────────────────────────────────

export const eventBus = mitt<Events>()
