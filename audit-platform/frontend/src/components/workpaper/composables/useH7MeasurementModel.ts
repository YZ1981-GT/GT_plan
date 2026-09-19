/**
 * useH7MeasurementModel — H7 生产性生物资产计量模式状态 + 显隐逻辑
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 1.3
 * Requirements: 1.11-1.14, 14.1-14.4
 *
 * 职责：
 * - measurementModel ref('cost' | 'fair_value') + 持久化到 checklist_responses
 * - visibleSheets computed（根据模式返回可见sheet编码列表）
 * - isSheetVisible(sheetCode) → boolean
 * - switchModel(target) → 幂等切换 + 不丢数据
 *
 * H7双计量模式sheet分组：
 * - 成本模式可见：H7-1(成本)/H7-2(成本)/H7-6(成本)/H7-7(成本)/H7-11/H7-12/H7-15/H7-16
 * - 公允模式可见：H7-1(公允)/H7-2(公允)/H7-6(公允)/H7-7(公允)/H7-13
 * - 共用sheet：H7-3/H7-4/H7-5/H7-8/H7-9/H7-10/H7-14/H7-17/附注
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type MeasurementModelType = 'cost' | 'fair_value'

export interface UseH7MeasurementModelParams {
  /** 立即保存到 checklist_responses */
  saveImmediate: (itemId: string, value: any) => Promise<void>
  /** 从 allResponses Map 获取值 */
  getValue: (itemId: string) => any
}

export interface UseH7MeasurementModelReturn {
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
const ITEM_ID = 'H7-measurement-model'

/** 共用sheet（不受模式影响，两种模式都显示） */
const SHARED_SHEETS: string[] = [
  'H7-3', 'H7-4', 'H7-5', 'H7-8', 'H7-9', 'H7-10', 'H7-14', 'H7-17',
]

/** 成本模式专有sheet（折旧/减值相关） */
const COST_ONLY_SHEETS: string[] = [
  'H7-11', 'H7-12', 'H7-15', 'H7-16',
]

/** 公允模式专有sheet（公允价值复核） */
const FAIR_ONLY_SHEETS: string[] = [
  'H7-13',
]

/** 两种模式都有但渲染不同子组件的sheet（H7-1/H7-2/H7-6/H7-7双版本） */
const DUAL_VERSION_SHEETS: string[] = [
  'H7-1', 'H7-2', 'H7-6', 'H7-7',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH7MeasurementModel(
  params: UseH7MeasurementModelParams,
): UseH7MeasurementModelReturn {
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
   * Cost mode: H7-1/2/6/7(双版本) + H7-11/12/15/16(成本专有) + 共用
   * Fair value mode: H7-1/2/6/7(双版本) + H7-13(公允专有) + 共用
   */
  const visibleSheets: ComputedRef<string[]> = computed(() => {
    const sheets = [...DUAL_VERSION_SHEETS, ...SHARED_SHEETS]

    if (measurementModel.value === 'cost') {
      sheets.push(...COST_ONLY_SHEETS)
    } else {
      sheets.push(...FAIR_ONLY_SHEETS)
    }

    return sheets
  })

  // ─── isSheetVisible ────────────────────────────────────────────────────────

  /**
   * 判断指定sheet编码是否在当前模式下可见。
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
   */
  async function switchModel(target: MeasurementModelType): Promise<void> {
    if (measurementModel.value === target) return

    measurementModel.value = target
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

export default useH7MeasurementModel
