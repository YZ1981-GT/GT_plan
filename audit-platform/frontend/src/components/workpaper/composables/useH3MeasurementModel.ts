/**
 * useH3MeasurementModel — H3 投资性房地产计量模式状态 + 显隐逻辑
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.2
 * Requirements: 1.11-1.12, 16.5, 16.11
 *
 * 职责：
 * - measurementModel ref('cost' | 'fair_value') + 持久化到 checklist_responses
 * - visibleSheets computed（根据模式返回可见sheet编码列表）
 * - isSheetVisible(sheetCode) → boolean
 * - switchModel(target) → 幂等切换 + 不丢数据
 *
 * 设计要点：
 * - standalone，不导入其他H3 composable（避免循环依赖）
 * - 接收 saveImmediate / getValue 函数从父级注入
 * - 两套数据独立存储（item_id 前缀区分），切换仅改 measurementModel 状态
 * - 幂等：switchModel(target) 若当前 === target 则直接返回，不触发保存
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type MeasurementModelType = 'cost' | 'fair_value'

export interface UseH3MeasurementModelParams {
  /** 立即保存到 checklist_responses */
  saveImmediate: (itemId: string, value: any) => Promise<void>
  /** 从 allResponses Map 获取值 */
  getValue: (itemId: string) => any
}

export interface UseH3MeasurementModelReturn {
  /** 当前计量模式 */
  measurementModel: Ref<MeasurementModelType>
  /** 当前模式下可见的sheet编码列表 */
  visibleSheets: ComputedRef<string[]>
  /** 判断指定sheet编码是否可见 */
  isSheetVisible: (sheetCode: string) => boolean
  /** 幂等切换计量模式（不丢数据） */
  switchModel: (target: MeasurementModelType) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 持久化到 checklist_responses 的 item_id */
const ITEM_ID = 'H3-measurement-model'

/** 共用sheet（不受模式影响，两种模式都显示） */
const SHARED_SHEETS: string[] = [
  'H3-3', 'H3-4', 'H3-6', 'H3-8', 'H3-9', 'H3-12', 'H3-13', 'H3-14',
]

/** 成本模式专有sheet */
const COST_ONLY_SHEETS: string[] = [
  'H3-7', 'H3-10', 'H3-11',
]

/** 两种模式通用但有双版本的sheet（根据模式渲染不同子组件） */
const DUAL_VERSION_SHEETS: string[] = [
  'H3-1', 'H3-2', 'H3-5',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3MeasurementModel(
  params: UseH3MeasurementModelParams,
): UseH3MeasurementModelReturn {
  const { saveImmediate, getValue } = params

  // ─── 初始化：从持久化数据中恢复 ──────────────────────────────────────────
  const stored = getValue(ITEM_ID)
  const initial: MeasurementModelType =
    stored === 'fair_value' ? 'fair_value' : 'cost'

  const measurementModel = ref<MeasurementModelType>(initial)

  // ─── visibleSheets computed ────────────────────────────────────────────────

  /**
   * 根据当前计量模式，返回可见sheet编码列表。
   *
   * Cost mode: H3-1, H3-2, H3-5, H3-7, H3-10, H3-11 + shared
   * Fair value mode: H3-1, H3-2, H3-5, H3-8 + shared (minus H3-8 already in shared)
   *
   * 注意：H3-8 在 SHARED_SHEETS 中（两种模式都可用，公允模式更核心）
   *       H3-7/H3-10/H3-11 仅成本模式可见
   */
  const visibleSheets: ComputedRef<string[]> = computed(() => {
    const sheets = [...DUAL_VERSION_SHEETS, ...SHARED_SHEETS]

    if (measurementModel.value === 'cost') {
      sheets.push(...COST_ONLY_SHEETS)
    }
    // fair_value 模式不添加 COST_ONLY_SHEETS，这些sheet不可见

    return sheets
  })

  // ─── isSheetVisible ────────────────────────────────────────────────────────

  /**
   * 判断指定sheet编码是否在当前模式下可见。
   * 支持带编号的精确匹配（如 "H3-7"）。
   */
  function isSheetVisible(sheetCode: string): boolean {
    return visibleSheets.value.includes(sheetCode)
  }

  // ─── switchModel ───────────────────────────────────────────────────────────

  /**
   * 幂等切换计量模式。
   *
   * - 若 target === 当前模式，直接返回（幂等，不触发保存）
   * - 切换仅改变 measurementModel ref 并持久化
   * - 不删除、不迁移任何数据（两套数据通过 item_id 前缀独立存储）
   * - 前端各子组件通过 measurementModel ref 响应式地选择渲染哪个版本
   */
  async function switchModel(target: MeasurementModelType): Promise<void> {
    // 幂等：已是目标模式则不操作
    if (measurementModel.value === target) return

    // 更新本地 ref
    measurementModel.value = target

    // 持久化到 checklist_responses
    await saveImmediate(ITEM_ID, target)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    measurementModel,
    visibleSheets,
    isSheetVisible,
    switchModel,
  }
}

export default useH3MeasurementModel
