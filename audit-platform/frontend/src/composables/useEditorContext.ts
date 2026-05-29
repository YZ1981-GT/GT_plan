/**
 * useEditorContext — 底稿编辑器 Shell 共享上下文契约（types + InjectionKey + mock helper）
 *
 * 契约层：仅定义 InjectionKey / TS interfaces / createMockEditorContext()，不实现 reactive state。
 * Shell 通过 provide(EDITOR_CONTEXT_KEY, ctx) 注入；子 SFC 通过 inject 读取（只读约定）。
 * 写操作走子 SFC emit 由 Shell 统一响应（详见 design §2.2）。
 *
 * @see .kiro/specs/workpaper-editor-shrink-phase2/design.md §3.1
 * Requirements: 1.4, 12.6
 */
import { ref, computed, type InjectionKey, type Ref, type ComputedRef } from 'vue'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import type { CycleTypeFlags } from './useCycleType'
import type { CycleDialogsAPI } from './useCycleDialogs'

// ─── 共享 reactive state（Shell provide → 子 SFC inject） ────────────────────

/**
 * Shell 通过 provide(EDITOR_CONTEXT_KEY, ctx) 暴露的响应式数据。
 * 子 SFC 通过 inject(EDITOR_CONTEXT_KEY) 获取，保持响应式。
 */
export interface EditorContextData {
  /** 当前项目 ID（路由派生） */
  projectId: ComputedRef<string>
  /** 当前底稿 ID（路由派生） */
  wpId: ComputedRef<string>
  /** 底稿详情（含 wp_code / parsed_data 等） */
  wpDetail: Ref<WorkpaperDetail | null>
  /** 是否可编辑（综合权限 + 归档 + 编辑锁判断） */
  canEdit: ComputedRef<boolean>
  /** 底稿组件类型（univer / d-form-table / c-note-table 等） */
  componentType: Ref<string>
  /** 循环类型 flags（isDCycle / isFCycle 等） */
  cycleType: CycleTypeFlags
  /** 循环弹窗状态集合 */
  cycleDialogs: CycleDialogsAPI
  /** 当前激活的 Sheet 导航 ID */
  sheetNavActiveId: ComputedRef<string>
}

/** Vue InjectionKey（Symbol，避免字符串 key 冲突） */
export const EDITOR_CONTEXT_KEY: InjectionKey<EditorContextData> = Symbol('EditorContext')

// ─── 测试 helper ────────────────────────────────────────────────────────────

/**
 * createMockEditorContext — vitest 中通过 `provide(EDITOR_CONTEXT_KEY, createMockEditorContext())` 独立 mount 子 SFC
 *
 * 默认返回空数据；overrides 用于按需替换部分字段（保持其余默认）。
 *
 * @example
 *   const ctx = createMockEditorContext({ canEdit: computed(() => true) })
 *   wrapper = mount(EditorStatusBar, {
 *     global: { provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx } },
 *     props: { ... },
 *   })
 */
export function createMockEditorContext(
  overrides: Partial<EditorContextData> = {},
): EditorContextData {
  const mockCycleType: CycleTypeFlags = {
    code: computed(() => ''),
    isBCycle: computed(() => false),
    isCCycle: computed(() => false),
    isDCycle: computed(() => false),
    isFCycle: computed(() => false),
    isGCycle: computed(() => false),
    isHCycle: computed(() => false),
    isICycle: computed(() => false),
    isKCycle: computed(() => false),
    isLCycle: computed(() => false),
    isMCycle: computed(() => false),
    isNCycle: computed(() => false),
  }

  const noop = () => { /* noop */ }
  const mockDialogEntry = {
    visible: ref(false),
    trigger: computed(() => false),
    onApplied: noop,
  }

  const mockCycleDialogs: CycleDialogsAPI = {
    stocktake: mockDialogEntry,
    valuation: { visible: ref(false), trigger: computed(() => false), loading: ref(false) },
    impairment: mockDialogEntry,
    hStocktake: mockDialogEntry,
    depreciationCalc: mockDialogEntry,
    assetImpairment: mockDialogEntry,
    goodwillImpairment: mockDialogEntry,
    capitalizationCheck: mockDialogEntry,
    amortizationCalc: { ...mockDialogEntry, section: computed(() => null) },
    fairValueTest: { ...mockDialogEntry, instrumentType: computed(() => '') },
    eclCalc: { ...mockDialogEntry, instrumentType: computed(() => '') },
    classificationCheck: mockDialogEntry,
    expenseAnalysis: mockDialogEntry,
    impairmentSummary: mockDialogEntry,
    interestCalc: mockDialogEntry,
    bondAmortization: mockDialogEntry,
    equityMovement: mockDialogEntry,
    incomeTaxCalc: mockDialogEntry,
  }

  const defaults: EditorContextData = {
    projectId: computed(() => ''),
    wpId: computed(() => ''),
    wpDetail: ref<WorkpaperDetail | null>(null),
    canEdit: computed(() => false),
    componentType: ref(''),
    cycleType: mockCycleType,
    cycleDialogs: mockCycleDialogs,
    sheetNavActiveId: computed(() => ''),
  }

  return { ...defaults, ...overrides }
}
