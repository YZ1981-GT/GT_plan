/**
 * useSimpleCycleEditor — 简单循环（K/L/M/N）通用编辑器工厂
 *
 * 重构动机（2026-05-28 复盘）：K/L/M/N 4 个 CycleEditor 共 ~330 行 100% 同构，
 * 仅在 cycle 字母 + dialog key 列表上有差异。本 generic 把同构部分抽出，
 * K/L/M/N 4 个 CycleEditor 退化为 4 行薄包装（保持向后兼容的 API 形状）。
 *
 * 设计要点：
 * 1. 接口形状与各专用 CycleEditor 一致（dialogs/triggers/handlers 三件套）
 * 2. 通过 config 注入差异：cycleLetter（'K'|'L'|'M'|'N'）+ dialogKeys（['expenseAnalysis', ...]）
 * 3. dialogs/triggers/handlers 字段名根据 dialogKeys 动态生成（如 expenseAnalysis →
 *    expenseAnalysisDialogVisible / showExpenseAnalysisTrigger / onExpenseAnalysisApplied）
 * 4. 不适用 D/E/F/G/H/I 循环（含 branch selector / 多参数 handler / 复杂 trigger 逻辑）
 *
 * @example
 *   // 替代原 useKCycleEditor 的实现
 *   const kCycle = useSimpleCycleEditor(wpDetail, cycleDialogs, {
 *     cycleLetter: 'K',
 *     dialogKeys: ['expenseAnalysis', 'impairmentSummary'],
 *   })
 *   // kCycle.dialogs.expenseAnalysisDialogVisible
 *   // kCycle.triggers.showExpenseAnalysisTrigger / isKCycle
 *   // kCycle.handlers.onExpenseAnalysisApplied
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { CycleDialogsAPI, CycleDialogEntry } from './useCycleDialogs'

// ─── 类型工具 ─────────────────────────────────────────────────────────────────

/** 把 dialog key（如 'expenseAnalysis'）转为大写首字母（'ExpenseAnalysis'） */
type Capitalize<S extends string> = S extends `${infer F}${infer R}`
  ? `${Uppercase<F>}${R}`
  : S

/** dialog 字段名：xxxDialogVisible */
type DialogField<K extends string> = `${K}DialogVisible`
/** trigger 字段名：showXxxTrigger */
type TriggerField<K extends string> = `show${Capitalize<K>}Trigger`
/** handler 字段名：onXxxApplied */
type HandlerField<K extends string> = `on${Capitalize<K>}Applied`

/** 给定 dialog key 列表 K[] 生成 dialogs 形状 */
type SimpleCycleDialogs<K extends string> = {
  [key in K as DialogField<key>]: Ref<boolean>
}
type SimpleCycleTriggers<K extends string, L extends string> = {
  [key in `is${Uppercase<L>}Cycle`]: ComputedRef<boolean>
} & {
  [key in K as TriggerField<key>]: ComputedRef<boolean>
}
type SimpleCycleHandlers<K extends string> = {
  [key in K as HandlerField<key>]: (sheet: string) => void
}

/** Simple cycle editor 的统一返回结构 */
export interface SimpleCycleEditorAPI<K extends string, L extends string> {
  dialogs: SimpleCycleDialogs<K>
  triggers: SimpleCycleTriggers<K, L>
  handlers: SimpleCycleHandlers<K>
}

// ─── 配置 ────────────────────────────────────────────────────────────────────

export interface SimpleCycleEditorConfig<K extends string, L extends string> {
  /** 循环字母（小写或大写都接受），用于生成 isXCycle 字段 + wpCode 前缀匹配 */
  cycleLetter: L
  /** 该循环的 dialog key 列表（必须存在于 useCycleDialogs API 中） */
  dialogKeys: readonly K[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function cap<S extends string>(s: S): Capitalize<S> {
  return (s.charAt(0).toUpperCase() + s.slice(1)) as Capitalize<S>
}

// ─── 工厂函数 ─────────────────────────────────────────────────────────────────

/**
 * 通用的简单循环编辑器工厂（适用于 K/L/M/N，无 branch selector）。
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 * @param config - cycle 字母 + dialog key 列表
 */
export function useSimpleCycleEditor<
  K extends keyof CycleDialogsAPI & string,
  L extends string,
>(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
  config: SimpleCycleEditorConfig<K, L>,
): SimpleCycleEditorAPI<K, L> {
  const upperLetter = config.cycleLetter.toUpperCase()
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  // ─── Dialogs：从 cycleDialogs 中按 key 透传 visible ──────────────────────────
  const dialogs = {} as SimpleCycleDialogs<K>
  for (const key of config.dialogKeys) {
    const entry = cycleDialogs[key] as CycleDialogEntry
    ;(dialogs as any)[`${key}DialogVisible`] = entry.visible
  }

  // ─── Triggers：isXCycle + showXxxTrigger ────────────────────────────────────
  const triggers = {} as SimpleCycleTriggers<K, L>
  ;(triggers as any)[`is${upperLetter}Cycle`] = computed(() =>
    new RegExp(`^${upperLetter}\\d`).test(wpCode.value),
  )
  for (const key of config.dialogKeys) {
    const entry = cycleDialogs[key] as CycleDialogEntry
    ;(triggers as any)[`show${cap(key)}Trigger`] = entry.trigger
  }

  // ─── Handlers：onXxxApplied 透传到 cycleDialogs.xxx.onApplied ────────────────
  const handlers = {} as SimpleCycleHandlers<K>
  for (const key of config.dialogKeys) {
    const entry = cycleDialogs[key] as CycleDialogEntry
    ;(handlers as any)[`on${cap(key)}Applied`] = (sheet: string) => entry.onApplied(sheet)
  }

  return { dialogs, triggers, handlers }
}
